from __future__ import annotations

import asyncio
import functools
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, ParamSpec, TypeVar

import httpx


ReturnT = TypeVar("ReturnT")
ParamT = ParamSpec("ParamT")

# El proveedor anuncia aquí su presupuesto real. AniList bajó de 90 a 30 req/min sin más
# aviso que esta cabecera: el número del constructor es el punto de partida, no la verdad.
RATE_LIMIT_HEADER = "X-RateLimit-Limit"


def _retry_after_seconds(response: httpx.Response) -> float | None:
    value = response.headers.get("Retry-After")
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None  # formato fecha HTTP: raro en AniList, caemos al backoff


def retry_with_backoff(
    *,
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    retryable_statuses: frozenset[int] = frozenset({429, 502, 503, 504}),
) -> Callable[[Callable[ParamT, Awaitable[ReturnT]]], Callable[ParamT, Awaitable[ReturnT]]]:
    def decorator(
        func: Callable[ParamT, Awaitable[ReturnT]],
    ) -> Callable[ParamT, Awaitable[ReturnT]]:
        @functools.wraps(func)
        async def wrapper(*args: ParamT.args, **kwargs: ParamT.kwargs) -> ReturnT:
            last_exception: BaseException | None = None
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except httpx.HTTPStatusError as error:
                    last_exception = error
                    if (
                        attempt < max_retries
                        and error.response.status_code in retryable_statuses
                    ):
                        # Respetar Retry-After (AniList lo envía en 429): esperar lo que
                        # pide en vez de un backoff ciego evita quemar reintentos y volver
                        # a chocar con el límite. Cae al backoff exponencial si no viene.
                        retry_after = _retry_after_seconds(error.response)
                        delay = (
                            retry_after
                            if retry_after is not None
                            else base_delay * (2**attempt)
                        )
                        await asyncio.sleep(min(delay, max_delay))
                        continue
                    raise
                except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError) as error:
                    last_exception = error
                    if attempt < max_retries:
                        delay = min(base_delay * (2**attempt), max_delay)
                        await asyncio.sleep(delay)
                        continue
                    raise
            if isinstance(last_exception, BaseException):
                raise last_exception
            raise RuntimeError("Unexpected end of retry loop")

        return wrapper

    return decorator


@dataclass(slots=True)
class _LoopState:
    """Estado del limitador ATADO a un event loop concreto.

    `lock` serializa el reparto de huecos, `semaphore` topa las peticiones en vuelo y
    `next_slot` es el reloj de salidas (en la escala de `loop.time()`)."""

    lock: asyncio.Lock
    semaphore: asyncio.Semaphore
    next_slot: float = 0.0


class RateLimitedClient:
    def __init__(
        self,
        *,
        requests_per_minute: int = 90,
        max_concurrency: int = 8,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
        timeout: float = 15.0,
    ):
        # requests_per_minute es el valor INICIAL y el TECHO — ya no "el presupuesto".
        # El presupuesto efectivo lo anuncia el proveedor en cada respuesta (ver
        # _observe_budget); hornearlo aquí es lo que hizo que siguiéramos pegándole a
        # AniList a 90 req/min mucho después de que bajara a 30.
        self._ceiling = requests_per_minute
        self._budget = requests_per_minute
        self._interval = 60.0 / requests_per_minute if requests_per_minute > 0 else 0.0
        # ponytail: 8 en vuelo sobra para el ritmo más rápido que permite el techo
        # (90/min ≈ 1,5 req/s). Súbelo solo si algo llega a saturarlo de verdad.
        self._max_concurrency = max(1, max_concurrency)
        self._max_retries = max_retries
        self._base_delay = base_delay
        self._max_delay = max_delay
        self._timeout = timeout
        # Cliente perezoso POR event loop: crear un AsyncClient por request construía
        # un contexto SSL (~100-200 ms de CPU) y un handshake TLS nuevos cada vez, y
        # un único cliente compartido no es seguro con varios loops vivos (el
        # MutationWorker corre asyncio.run() en otro hilo: reemplazar el cliente del
        # loop principal podía cerrarlo con requests en vuelo). Las entradas de loops
        # cerrados se podan en el siguiente acceso; sus conexiones mueren con el loop
        # y el GC finaliza el resto.
        self._clients: dict[asyncio.AbstractEventLoop, httpx.AsyncClient] = {}
        # Gemelo de _clients, y por exactamente el mismo motivo: un asyncio.Semaphore o un
        # asyncio.Lock se atan al primer loop en el que tienen que ESPERAR, y este cliente
        # es un singleton de módulo que el MutationWorker usa desde un asyncio.run() en
        # otro hilo (un loop nuevo por mutación, cada 3 s). Construir los primitivos en
        # __init__ los ataba al loop del import: en cuanto hubiera contención real desde el
        # segundo loop, RuntimeError o cuelgue. Sobrevivía solo porque un Semaphore(90) no
        # llega a esperar nunca — el bug estaba armado, no ausente. Ahora se crean DENTRO
        # del loop que los usa, y las entradas de loops cerrados se podan en el siguiente
        # acceso (si no, este dict crece sin límite: uno por mutación).
        self._loop_state: dict[asyncio.AbstractEventLoop, _LoopState] = {}

    @property
    def budget(self) -> int:
        """Presupuesto efectivo (req/min): el último que anunció el proveedor, acotado al techo."""
        return self._budget

    def _state_for(self, loop: asyncio.AbstractEventLoop) -> _LoopState:
        # list(): el otro hilo puede estar insertando su loop mientras iteramos aquí.
        for stale in [known for known in list(self._loop_state) if known.is_closed()]:
            self._loop_state.pop(stale, None)
        state = self._loop_state.get(loop)
        if state is None:
            state = _LoopState(
                lock=asyncio.Lock(),
                semaphore=asyncio.Semaphore(self._max_concurrency),
            )
            self._loop_state[loop] = state
        return state

    def _observe_budget(self, response: httpx.Response) -> None:
        """Ajusta el ritmo al presupuesto que ACABA de anunciar el proveedor."""
        if self._ceiling <= 0:
            return
        # getattr: los fakes de la suite no traen cabeceras (mismo motivo que el getattr
        # de _client_for, tres líneas más abajo).
        raw = getattr(response, "headers", {}).get(RATE_LIMIT_HEADER)
        if raw is None:
            return
        try:
            announced = int(str(raw).strip())
        except ValueError:
            return  # vacía o no numérica: el presupuesto no se toca
        if announced <= 0:
            return
        # ponytail: el techo es deliberado. Un proveedor roto, comprometido o un MITM que
        # anuncie 999999 NO puede desactivar el limitador y ganarnos un baneo. Si un
        # proveedor sube su límite de verdad, se sube el techo aquí, a mano.
        budget = min(announced, self._ceiling)
        if budget != self._budget:
            self._budget = budget
            self._interval = 60.0 / budget

    def _client_for(self, loop: asyncio.AbstractEventLoop) -> httpx.AsyncClient:
        for stale in [known for known in list(self._clients) if known.is_closed()]:
            self._clients.pop(stale, None)
        client = self._clients.get(loop)
        # getattr: los tests sustituyen AsyncClient por fakes sin is_closed.
        if client is None or getattr(client, "is_closed", False):
            client = httpx.AsyncClient(timeout=self._timeout)
            self._clients[loop] = client
        return client

    @retry_with_backoff(max_retries=3, base_delay=1.0, max_delay=30.0)
    async def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        loop = asyncio.get_running_loop()
        state = self._state_for(loop)

        if self._interval:
            # Reloj de salidas: cada petición reserva SU hueco bajo el lock y luego duerme
            # hasta él FUERA de todo. Dormir con el semáforo en la mano (lo que se hacía
            # antes) no limitaba nada: las N corrutinas entraban a la vez, pedían todas el
            # mismo intervalo, despertaban en el mismo tick y salían en ráfaga.
            async with state.lock:
                deadline = max(loop.time(), state.next_slot)
                state.next_slot = deadline + self._interval
            await asyncio.sleep(deadline - loop.time())

        async with state.semaphore:  # tope de peticiones EN VUELO, no mecanismo de ritmo
            response = await self._client_for(loop).request(method, url, **kwargs)
            # ANTES de raise_for_status: el 429 es justo la respuesta que trae el
            # presupuesto degradado, y raise_for_status la haría estallar sin leerla — el
            # único caso que importa sería el único que nunca vemos.
            self._observe_budget(response)
            response.raise_for_status()
            return response

    async def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("POST", url, **kwargs)

    async def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("GET", url, **kwargs)

    async def patch(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("PATCH", url, **kwargs)

    async def delete(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("DELETE", url, **kwargs)
