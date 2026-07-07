from __future__ import annotations

import asyncio
import contextlib
import functools
from collections.abc import Awaitable, Callable
from typing import Any, ParamSpec, TypeVar

import httpx


ReturnT = TypeVar("ReturnT")
ParamT = ParamSpec("ParamT")


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


class RateLimitedClient:
    def __init__(
        self,
        *,
        requests_per_minute: int = 90,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
        timeout: float = 15.0,
    ):
        if requests_per_minute > 0:
            self._semaphore = asyncio.Semaphore(requests_per_minute)
            self._interval = 60.0 / requests_per_minute
        else:
            self._semaphore = None
            self._interval = 0.0
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

    def _client_for(self, loop: asyncio.AbstractEventLoop) -> httpx.AsyncClient:
        for stale in [known for known in self._clients if known.is_closed()]:
            del self._clients[stale]
        client = self._clients.get(loop)
        # getattr: los tests sustituyen AsyncClient por fakes sin is_closed.
        if client is None or getattr(client, "is_closed", False):
            client = httpx.AsyncClient(timeout=self._timeout)
            self._clients[loop] = client
        return client

    @retry_with_backoff(max_retries=3, base_delay=1.0, max_delay=30.0)
    async def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        async with (
            self._semaphore
            if self._semaphore is not None
            else contextlib.nullcontext()
        ):
            loop = asyncio.get_running_loop()
            response = await self._client_for(loop).request(method, url, **kwargs)
            response.raise_for_status()
            if self._interval:
                await asyncio.sleep(self._interval)
            return response

    async def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("POST", url, **kwargs)

    async def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("GET", url, **kwargs)

    async def patch(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("PATCH", url, **kwargs)

    async def delete(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("DELETE", url, **kwargs)
