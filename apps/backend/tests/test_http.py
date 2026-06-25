import asyncio

import httpx
import pytest
from fastapi import HTTPException

from nyanko_api.http import RateLimitedClient, retry_with_backoff
from nyanko_api.main import raise_provider_auth_error
from nyanko_api.secrets import get_anilist_token, set_anilist_token


async def _noop_sleep(*args, **kwargs):
    return None


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
async def test_rate_limited_client_enforces_concurrency_limit(monkeypatch):
    client = RateLimitedClient(requests_per_minute=1)
    active = 0
    max_active = 0

    class Response:
        def raise_for_status(self):
            return None

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def request(self, *args, **kwargs):
            nonlocal active, max_active
            active += 1
            max_active = max(max_active, active)
            await asyncio.sleep(0)
            active -= 1
            return Response()

    monkeypatch.setattr("nyanko_api.http.httpx.AsyncClient", lambda **kwargs: FakeClient())
    monkeypatch.setattr("nyanko_api.http.asyncio.sleep", _noop_sleep)

    await asyncio.gather(
        client.get("https://example.test/1"),
        client.get("https://example.test/2"),
        client.get("https://example.test/3"),
    )

    assert max_active <= 1


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
