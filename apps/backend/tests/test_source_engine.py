from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from nyanko_api.sources.contract import (
    SOURCE_API_VERSION,
    SourceCapabilities,
    SourceChapter,
    SourcePage,
    SourceSeries,
)
from nyanko_api.sources.engine import SourceEngine
from nyanko_api.sources.errors import (
    SourceError,
    SourceNetworkError,
    SourceNotFoundError,
    SourceParseError,
    SourceRateLimitError,
)
from nyanko_api.sources.registry import SourceRegistry


class _FuenteCache:
    name = "cache"
    display_name = "Cache"
    api_version = SOURCE_API_VERSION
    capabilities = SourceCapabilities()

    def __init__(self):
        self.fail = False

    async def search(self, query: str, limit: int = 20) -> list[SourceSeries]:
        return [SourceSeries(source_id=query, title=query)]

    async def chapters(self, series: SourceSeries | str) -> list[SourceChapter]:
        if self.fail:
            raise SourceParseError("Cloudflare devolvio HTML")
        series_id = series.source_id if isinstance(series, SourceSeries) else series
        return [SourceChapter(source_id="c1", title="1", series_id=series_id)]

    async def pages(self, chapter: SourceChapter | str) -> list[SourcePage]:
        chapter_id = chapter.source_id if isinstance(chapter, SourceChapter) else chapter
        return [SourcePage(source_id="p1", chapter_id=chapter_id, index=1, filename="1.jpg")]


class _FuenteVacia(_FuenteCache):
    name = "vacia"

    async def chapters(self, series: SourceSeries | str) -> list[SourceChapter]:
        return []


class _FuenteHttp(_FuenteCache):
    name = "http"

    def __init__(self, error: BaseException):
        self.error = error

    async def chapters(self, series: SourceSeries | str) -> list[SourceChapter]:
        raise self.error


@pytest.mark.asyncio
async def test_chapters_returns_good_cache_after_source_parse_error():
    source = _FuenteCache()
    engine = SourceEngine(SourceRegistry([source]))

    cached = await engine.chapters("cache", "serie")
    source.fail = True

    assert await engine.chapters("cache", "serie") == cached


@pytest.mark.asyncio
async def test_chapters_rethrows_parse_error_without_cache():
    source = _FuenteCache()
    source.fail = True
    engine = SourceEngine(SourceRegistry([source]))

    with pytest.raises(SourceParseError):
        await engine.chapters("cache", "serie")


@pytest.mark.asyncio
async def test_empty_chapters_are_parse_error_and_do_not_cache_empty_list():
    engine = SourceEngine(SourceRegistry([_FuenteVacia()]))

    with pytest.raises(SourceParseError):
        await engine.chapters("vacia", "serie")

    assert engine._chapters == {}


@pytest.mark.asyncio
async def test_source_engine_translates_http_errors():
    request = httpx.Request("GET", "https://source.test/manga")

    rate_limited = httpx.HTTPStatusError(
        "rate limited",
        request=request,
        response=httpx.Response(429, headers={"Retry-After": "3"}, request=request),
    )
    not_found = httpx.HTTPStatusError(
        "missing",
        request=request,
        response=httpx.Response(404, request=request),
    )

    with pytest.raises(SourceRateLimitError) as limited:
        await SourceEngine(SourceRegistry([_FuenteHttp(rate_limited)])).chapters("http", "serie")
    assert limited.value.retry_after == 3

    with pytest.raises(SourceNotFoundError):
        await SourceEngine(SourceRegistry([_FuenteHttp(not_found)])).chapters("http", "serie")

    with pytest.raises(SourceNetworkError):
        await SourceEngine(
            SourceRegistry([_FuenteHttp(httpx.ConnectError("offline", request=request))])
        ).chapters("http", "serie")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        httpx.RemoteProtocolError("el servidor colgo a media respuesta"),
        httpx.ProxyError("proxy caido"),
        httpx.TooManyRedirects("bucle de redirecciones"),
        httpx.DecodingError("gzip corrupto"),
        IndexError("el parser de la fuente se salio de rango"),
        ValueError("json ajeno malformado"),
    ],
)
async def test_every_source_failure_reaches_the_caller_as_source_error(error):
    """El caller solo atrapa SourceError; nada puede escaparse sin tipar."""
    engine = SourceEngine(SourceRegistry([_FuenteHttp(error)]))

    with pytest.raises(SourceError):
        await engine.chapters("http", "serie")


def test_source_engine_cache_stays_in_memory_only():
    source = Path("nyanko_api/sources/engine.py").read_text(encoding="utf-8")

    assert "set_cache" not in source
    assert "sqlite" not in source.lower()
