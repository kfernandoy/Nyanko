from __future__ import annotations

import asyncio
import contextlib
import functools
from collections.abc import Awaitable, Callable
from typing import Any, ParamSpec, TypeVar

import httpx


ReturnT = TypeVar("ReturnT")
ParamT = ParamSpec("ParamT")


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
                        delay = min(base_delay * (2**attempt), max_delay)
                        await asyncio.sleep(delay)
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
        # Cliente compartido y perezoso: crear un AsyncClient por request construía
        # un contexto SSL (~100-200 ms de CPU) y un handshake TLS nuevos cada vez.
        # Se re-crea si cambia el event loop (los tests usan un loop por test).
        self._client: httpx.AsyncClient | None = None
        self._client_loop: asyncio.AbstractEventLoop | None = None

    @retry_with_backoff(max_retries=3, base_delay=1.0, max_delay=30.0)
    async def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        async with (
            self._semaphore
            if self._semaphore is not None
            else contextlib.nullcontext()
        ):
            loop = asyncio.get_running_loop()
            # getattr: los tests sustituyen AsyncClient por fakes sin is_closed.
            if (
                self._client is None
                or self._client_loop is not loop
                or getattr(self._client, "is_closed", False)
            ):
                self._client = httpx.AsyncClient(timeout=self._timeout)
                self._client_loop = loop
            response = await self._client.request(method, url, **kwargs)
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
