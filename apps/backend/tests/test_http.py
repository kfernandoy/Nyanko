import asyncio
import threading

import httpx
import pytest
from fastapi import HTTPException

from nyanko_api.http import RATE_LIMIT_HEADER, RateLimitedClient, retry_with_backoff
from nyanko_api.main import raise_provider_auth_error
from nyanko_api.secrets import get_anilist_token, set_anilist_token


async def _noop_sleep(*args, **kwargs):
    return None


# Los fixtures parchean `nyanko_api.http.asyncio.sleep`, que ES `asyncio.sleep` (el módulo
# es el mismo objeto). Los fakes que necesitan ceder el control de verdad usan esta
# referencia capturada en el import, antes de que nadie la parchee.
_real_sleep = asyncio.sleep


class _FakeResponse:
    """Respuesta fake del proveedor.

    Sin `headers` cuando no se le pasan: es el fake incompleto que la suite ya usaba, y
    mantenerlo así obliga a que `_observe_budget` lea las cabeceras a la defensiva."""

    def __init__(self, headers: dict[str, str] | None = None):
        if headers is not None:
            self.headers = headers

    def raise_for_status(self):
        return None


def _install_fake_provider(monkeypatch, headers: dict[str, str] | None = None) -> None:
    class FakeClient:
        async def request(self, *args, **kwargs):
            return _FakeResponse(headers)

    monkeypatch.setattr(
        "nyanko_api.http.httpx.AsyncClient", lambda **kwargs: FakeClient()
    )


@pytest.mark.asyncio
async def test_retry_with_backoff_retries_429_and_eventually_succeeds(monkeypatch):
    attempts = 0

    @retry_with_backoff(max_retries=2, base_delay=0.0, max_delay=0.0)
    async def flaky() -> dict:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            response = httpx.Response(429, text="rate limited")
            raise httpx.HTTPStatusError(
                "rate limited", request=None, response=response
            )
        return {"ok": True}

    monkeypatch.setattr("nyanko_api.http.asyncio.sleep", _noop_sleep)

    result = await flaky()

    assert result == {"ok": True}
    assert attempts == 3


@pytest.mark.asyncio
async def test_retry_with_backoff_gives_up_on_client_error():
    attempts = 0

    @retry_with_backoff(max_retries=2, base_delay=0.0, max_delay=0.0)
    async def failing() -> dict:
        nonlocal attempts
        attempts += 1
        response = httpx.Response(400, text="bad request")
        raise httpx.HTTPStatusError("bad request", request=None, response=response)

    with pytest.raises(httpx.HTTPStatusError):
        await failing()

    assert attempts == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("budget", [120, 45, 12])
async def test_pacing_follows_provider_header(monkeypatch, real_rate_limit_sleep, budget):
    # El techo (200) no coincide con NINGÚN presupuesto probado: si el ritmo saliera del
    # constructor en vez de la cabecera, el calendario no cuadraría para ninguno.
    client = RateLimitedClient(requests_per_minute=200, max_concurrency=50)
    _install_fake_provider(monkeypatch, headers={RATE_LIMIT_HEADER: str(budget)})

    # Calentamiento: la PRIMERA respuesta es la que anuncia el presupuesto, así que su
    # propia salida se programó todavía con el intervalo inicial. Reiniciamos el reloj de
    # salidas para medir el calendario limpio que produce el presupuesto ya anunciado.
    await client.get("https://example.test/warmup")
    assert client.budget == budget
    client._loop_state[asyncio.get_running_loop()].next_slot = 0.0
    real_rate_limit_sleep.clear()

    requests = 5
    await asyncio.gather(
        *(client.get(f"https://example.test/{i}") for i in range(requests))
    )

    interval = 60.0 / budget
    # Calendario ACUMULATIVO, no "cada sleep vale el intervalo": esa segunda forma sería
    # verde para el bug (N corrutinas durmiendo lo mismo y saliendo todas en el mismo
    # tick). La tolerancia es obligatoria: loop.time() avanza microsegundos entre que se
    # calcula el deadline y se pide el sleep.
    assert real_rate_limit_sleep == pytest.approx(
        [i * interval for i in range(requests)], abs=0.01
    )


@pytest.mark.asyncio
async def test_concurrent_requests_get_distinct_deadlines(
    monkeypatch, real_rate_limit_sleep
):
    client = RateLimitedClient(requests_per_minute=90)
    _install_fake_provider(monkeypatch)

    requests = 10
    await asyncio.gather(
        *(client.get(f"https://example.test/{i}") for i in range(requests))
    )

    # Contra el bug (un `await asyncio.sleep(self._interval)` por corrutina) los N valores
    # grabados son el MISMO → len(set(...)) == 1. Cada petición espera a SU turno.
    assert len(real_rate_limit_sleep) == requests
    assert len(set(real_rate_limit_sleep)) == requests


@pytest.mark.asyncio
async def test_max_concurrency_caps_requests_in_flight(monkeypatch):
    # El ritmo no puede ser quien limite aquí (el sleep está anulado por el fixture
    # autouse): el único tope en juego es el semáforo de peticiones en vuelo.
    client = RateLimitedClient(requests_per_minute=600, max_concurrency=2)
    active = 0
    max_active = 0

    class FakeClient:
        async def request(self, *args, **kwargs):
            nonlocal active, max_active
            active += 1
            max_active = max(max_active, active)
            await _real_sleep(0)  # cede el control: deja entrar a las que quepan
            active -= 1
            return _FakeResponse()

    monkeypatch.setattr(
        "nyanko_api.http.httpx.AsyncClient", lambda **kwargs: FakeClient()
    )

    await asyncio.gather(*(client.get(f"https://example.test/{i}") for i in range(6)))

    assert max_active == 2


@pytest.mark.asyncio
async def test_budget_degrades_and_recovers(monkeypatch):
    client = RateLimitedClient(requests_per_minute=90)
    seen_budgets: list[int] = []
    request = httpx.Request("GET", "https://example.test/1")

    class FakeClient:
        calls = 0

        async def request(self, *args, **kwargs):
            FakeClient.calls += 1
            seen_budgets.append(client.budget)
            if FakeClient.calls == 1:
                # El 429 de AniList ES la respuesta que anuncia el presupuesto degradado:
                # si se observara después de raise_for_status, nunca se leería.
                return httpx.Response(
                    429, headers={RATE_LIMIT_HEADER: "30"}, request=request
                )
            return httpx.Response(
                200, headers={RATE_LIMIT_HEADER: "90"}, request=request
            )

    monkeypatch.setattr(
        "nyanko_api.http.httpx.AsyncClient", lambda **kwargs: FakeClient()
    )

    await client.get("https://example.test/1")

    # El reintento vio ya el presupuesto degradado → se leyó ANTES de raise_for_status.
    assert seen_budgets == [90, 30]
    # Y cuando el proveedor anuncia la recuperación, la seguimos.
    assert client.budget == 90
    assert client._interval == pytest.approx(60.0 / 90)


@pytest.mark.parametrize("hostile", ["999999", "0", "-5", "", "abc", "30.5"])
def test_hostile_budget_header_is_clamped(hostile):
    client = RateLimitedClient(requests_per_minute=90)
    client._observe_budget(_FakeResponse({RATE_LIMIT_HEADER: "30"}))
    assert client.budget == 30

    client._observe_budget(_FakeResponse({RATE_LIMIT_HEADER: hostile}))

    # 999999 sube como mucho AL TECHO — jamás desactiva el limitador (T-01-02).
    # El resto (0, negativo, vacío, no entero) no cambia nada.
    expected = 90 if hostile == "999999" else 30
    assert client.budget == expected
    assert client._interval == pytest.approx(60.0 / expected)


def test_missing_budget_header_keeps_constructor_budget():
    # Kitsu y MAL no mandan X-RateLimit-Limit: se comportan exactamente como hoy.
    client = RateLimitedClient(requests_per_minute=50)

    client._observe_budget(_FakeResponse())  # fake sin cabeceras, como los de la suite

    assert client.budget == 50
    assert client._interval == pytest.approx(60.0 / 50)


@pytest.mark.asyncio
async def test_burst_from_two_event_loops(monkeypatch):
    client = RateLimitedClient(requests_per_minute=90, max_concurrency=8)

    class FakeClient:
        async def request(self, *args, **kwargs):
            # Cede el control con la petición EN VUELO: con 50 corrutinas y un tope de 8,
            # el semáforo tiene que ESPERAR de verdad — y es al esperar cuando un
            # primitivo de asyncio se ata a un loop. Un fake que no cede nunca contiende,
            # y un semáforo que nunca contiende nunca revienta: justo por eso el bug
            # llevaba aquí desde siempre sin dar la cara.
            await _real_sleep(0)
            return _FakeResponse()

    monkeypatch.setattr(
        "nyanko_api.http.httpx.AsyncClient", lambda **kwargs: FakeClient()
    )

    async def _burst():
        await asyncio.gather(
            *(client.get(f"https://example.test/{i}") for i in range(50))
        )

    errors: list[BaseException] = []

    def _other_loop():
        # La forma exacta de MutationWorker._drain: hilo + asyncio.run() → loop NUEVO.
        try:
            asyncio.run(_burst())
        except BaseException as error:  # noqa: BLE001 - un Thread se las traga en silencio
            errors.append(error)

    thread = threading.Thread(target=_other_loop)
    thread.start()
    await _burst()
    thread.join(timeout=10)

    assert not thread.is_alive(), "el limitador se colgó en el segundo event loop"
    assert errors == []


@pytest.mark.asyncio
async def test_loop_state_prunes_closed_loops(monkeypatch):
    client = RateLimitedClient(requests_per_minute=90)
    _install_fake_provider(monkeypatch)

    def _one_shot():
        asyncio.run(client.get("https://example.test/1"))

    thread = threading.Thread(target=_one_shot)
    thread.start()
    thread.join(timeout=10)
    assert not thread.is_alive()
    assert len(client._loop_state) == 1  # el estado del loop muerto sigue ahí...

    await client.get("https://example.test/2")  # ...hasta el siguiente acceso, que lo poda

    assert list(client._loop_state) == [asyncio.get_running_loop()]


def test_anilist_401_is_reported_as_expired_session():
    set_anilist_token("expired", "error-test")
    request = httpx.Request("POST", "https://graphql.anilist.co")
    response = httpx.Response(401, request=request)
    error = httpx.HTTPStatusError("unauthorized", request=request, response=response)

    with pytest.raises(HTTPException) as caught:
        raise_provider_auth_error(error, "anilist", "error-test")

    assert caught.value.status_code == 401
    assert "vuelve a conectar" in caught.value.detail
    assert get_anilist_token("error-test") is None


def test_anilist_network_error_is_reported_as_unavailable():
    request = httpx.Request("POST", "https://graphql.anilist.co")

    with pytest.raises(HTTPException) as caught:
        raise_provider_auth_error(
            httpx.ConnectError("offline", request=request), "anilist", "default"
        )

    assert caught.value.status_code == 503
    assert "no está disponible" in caught.value.detail


def test_anilist_internal_error_does_not_leak_details():
    with pytest.raises(HTTPException) as caught:
        raise_provider_auth_error(
            RuntimeError("secret payload from httpx internals"), "anilist", "default"
        )

    assert caught.value.status_code == 502
    assert caught.value.detail == "No se pudo completar la solicitud a AniList."
