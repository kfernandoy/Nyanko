from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

import httpx

from nyanko_api.http import RateLimitedClient

from .contract import (
    SourceCapabilities,
    SourceChapter,
    SourcePage,
    SourcePageContent,
    SourceSeries,
)
from .errors import (
    SourceError,
    SourceNetworkError,
    SourceNotFoundError,
    SourceParseError,
    SourceRateLimitError,
    source_error_action,
)

if TYPE_CHECKING:
    from .registry import SourceRegistry

SOURCE_RATE_LIMIT_CEILING = 120
SOURCE_MAX_CONCURRENCY = 8
SOURCE_READ_PRIORITY = 10
SOURCE_DOWNLOAD_PRIORITY = 0


class DefaultSourceFetcher:
    def __init__(
        self,
        client: RateLimitedClient,
        headers: Mapping[str, str] | None = None,
    ):
        self.client = client
        self.headers = dict(headers or {})

    async def request(
        self,
        method: str,
        url: str,
        *,
        priority: int = SOURCE_READ_PRIORITY,
        headers: Mapping[str, str] | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        merged_headers = {**self.headers, **dict(headers or {})}
        if merged_headers:
            kwargs["headers"] = merged_headers
        return await self.client.request(method, url, priority=priority, **kwargs)

    async def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("POST", url, **kwargs)


def build_source_fetcher(capabilities: SourceCapabilities) -> DefaultSourceFetcher:
    budget = _bounded_requests_per_minute(capabilities.requests_per_minute)
    client = RateLimitedClient(
        requests_per_minute=budget,
        max_concurrency=SOURCE_MAX_CONCURRENCY,
    )
    return DefaultSourceFetcher(client, capabilities.headers)


class SourceEngine:
    def __init__(self, registry: SourceRegistry):
        self._registry = registry
        # ponytail: dict de proceso sin TTL/LRU; persistencia diferida a Fase 8.
        self._chapters: dict[tuple[str, str], list[SourceChapter]] = {}

    async def search(
        self, source_name: str, query: str, limit: int = 20
    ) -> list[SourceSeries]:
        source = self._registry.get(source_name)
        return await self._call_source(lambda: source.search(query, limit))

    async def chapters(
        self, source_name: str, series: SourceSeries | str
    ) -> list[SourceChapter]:
        source = self._registry.get(source_name)
        series_id = series.source_id if isinstance(series, SourceSeries) else series
        key = (source_name, series_id)
        try:
            fresh = await self._call_source(lambda: source.chapters(series))
            if not fresh:
                raise SourceParseError("La fuente no devolvio capitulos")
        except SourceError as error:
            # Un 429 es back-pressure: la fuente esta PIDIENDO que paremos. Servir cache
            # lo silencia y seguimos machacandola, que es justo lo que la fuente intenta
            # evitar. Quien decide es la taxonomia, no un isinstance nuevo: si mañana otro
            # error mapea a "esperar", esta rama se entera sola.
            if source_error_action(error) == "esperar":
                raise
            if key in self._chapters:
                return list(self._chapters[key])
            raise
        self._chapters[key] = list(fresh)
        return list(fresh)

    async def pages(self, source_name: str, chapter: SourceChapter | str) -> list[SourcePage]:
        source = self._registry.get(source_name)
        pages = await self._call_source(lambda: source.pages(chapter))
        if not pages:
            raise SourceParseError("La fuente no devolvio paginas")
        return pages

    async def page_bytes(
        self, source_name: str, page: SourcePage | str
    ) -> SourcePageContent:
        source = self._registry.get(source_name)
        return await self._call_source(lambda: source.page_bytes(page))

    async def _call_source(self, call):
        # El contrato es que el caller solo tiene que atrapar SourceError. Nada de lo que
        # lance una fuente — httpx exotico o un IndexError parseando HTML ajeno — puede
        # escapar de aqui sin tipar, o el caller se come un 500.
        try:
            return await call()
        except SourceError:
            raise
        except httpx.HTTPStatusError as error:
            raise _source_error_from_http_status(error) from error
        except httpx.HTTPError as error:
            raise SourceNetworkError("No se pudo conectar con la fuente") from error
        except Exception as error:
            raise SourceParseError("La fuente devolvio algo que no se pudo interpretar") from error


def _bounded_requests_per_minute(value: int) -> int:
    try:
        requested = int(value)
    except (TypeError, ValueError):
        requested = SOURCE_RATE_LIMIT_CEILING
    return min(max(1, requested), SOURCE_RATE_LIMIT_CEILING)


def _source_error_from_http_status(error: httpx.HTTPStatusError) -> SourceError:
    status = error.response.status_code
    if status == 429:
        return SourceRateLimitError(
            "La fuente limito las peticiones",
            retry_after=_retry_after_seconds(error.response),
        )
    if status == 404:
        return SourceNotFoundError("La fuente no encontro el recurso")
    return SourceNetworkError(f"La fuente respondio HTTP {status}")


def _retry_after_seconds(response: httpx.Response) -> float | None:
    value = response.headers.get("Retry-After")
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None
