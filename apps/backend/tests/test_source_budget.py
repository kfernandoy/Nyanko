from __future__ import annotations

import asyncio

import pytest

from nyanko_api.http import RateLimitedClient
from nyanko_api.sources.contract import (
    SOURCE_API_VERSION,
    SourceCapabilities,
    SourceChapter,
    SourcePage,
    SourceSeries,
)
from nyanko_api.sources.engine import (
    DefaultSourceFetcher,
    SOURCE_RATE_LIMIT_CEILING,
    SOURCE_READ_PRIORITY,
)
from nyanko_api.sources.registry import build_source_registry

_real_sleep = asyncio.sleep


class _FakeResponse:
    headers: dict[str, str] = {}

    def raise_for_status(self):
        return None


class _FuenteConFetch:
    name = "budget"
    display_name = "Budget"
    api_version = SOURCE_API_VERSION
    capabilities = SourceCapabilities(
        headers={"Referer": "https://source.test/", "User-Agent": "NyankoSourceTest"},
        requests_per_minute=600,
    )

    def __init__(self, fetcher):
        self.fetcher = fetcher

    async def search(self, query: str, limit: int = 20) -> list[SourceSeries]:
        return [SourceSeries(source_id=query, title=query)]

    async def chapters(self, series: SourceSeries | str) -> list[SourceChapter]:
        series_id = series.source_id if isinstance(series, SourceSeries) else series
        return [SourceChapter(source_id="c1", title="1", series_id=series_id)]

    async def pages(self, chapter: SourceChapter | str) -> list[SourcePage]:
        chapter_id = chapter.source_id if isinstance(chapter, SourceChapter) else chapter
        return [SourcePage(source_id="p1", chapter_id=chapter_id, index=1, filename="1.jpg")]


def test_registry_builds_one_rate_limited_fetcher_per_source():
    registry = build_source_registry(sources=[_FuenteConFetch])
    source = registry.get("budget")

    assert isinstance(source.fetcher, DefaultSourceFetcher)
    assert source.fetcher.client.budget == SOURCE_RATE_LIMIT_CEILING


@pytest.mark.asyncio
async def test_source_fetcher_applies_declared_headers(monkeypatch):
    seen: list[dict] = []

    class FakeClient:
        async def request(self, *args, **kwargs):
            seen.append(kwargs)
            return _FakeResponse()

    monkeypatch.setattr(
        "nyanko_api.http.httpx.AsyncClient", lambda **kwargs: FakeClient()
    )
    registry = build_source_registry(sources=[_FuenteConFetch])
    source = registry.get("budget")

    await source.fetcher.get("https://source.test/manga")

    assert seen[0]["headers"] == {
        "Referer": "https://source.test/",
        "User-Agent": "NyankoSourceTest",
    }


@pytest.mark.asyncio
async def test_consumers_share_one_source_bucket(monkeypatch, real_rate_limit_sleep):
    class FakeClient:
        async def request(self, *args, **kwargs):
            return _FakeResponse()

    monkeypatch.setattr(
        "nyanko_api.http.httpx.AsyncClient", lambda **kwargs: FakeClient()
    )
    registry = build_source_registry(
        sources=[
            type(
                "FuenteLenta",
                (_FuenteConFetch,),
                {
                    "name": "lenta",
                    "capabilities": SourceCapabilities(requests_per_minute=60),
                },
            )
        ]
    )
    fetcher = registry.get("lenta").fetcher

    await asyncio.gather(
        *(fetcher.get(f"https://source.test/reader/{i}") for i in range(2)),
        *(fetcher.get(f"https://source.test/download/{i}", priority=0) for i in range(2)),
    )

    assert real_rate_limit_sleep == pytest.approx([0.0, 1.0, 2.0, 3.0], abs=0.01)
    assert len(set(real_rate_limit_sleep)) == len(real_rate_limit_sleep)


@pytest.mark.asyncio
async def test_read_priority_overtakes_queued_downloads(monkeypatch):
    # Este es el unico test de ritmo que necesita reloj REAL: con el sleep falseado nunca
    # llega a formarse cola (cada peticion se auto-concede el hueco y sale), y sin cola no
    # hay prioridad que medir. 1200/min = 50 ms por hueco: la cola se forma de verdad y el
    # test entero cuesta ~200 ms.
    monkeypatch.setattr("nyanko_api.http.asyncio.sleep", _real_sleep)
    salidas: list[str] = []

    class FakeClient:
        async def request(self, _method, url, **kwargs):
            salidas.append(url)
            return _FakeResponse()

    monkeypatch.setattr(
        "nyanko_api.http.httpx.AsyncClient", lambda **kwargs: FakeClient()
    )
    client = RateLimitedClient(requests_per_minute=1200, max_concurrency=10)

    downloads = [
        asyncio.create_task(
            client.get(f"https://source.test/download/{index}", priority=0),
            name=f"download-{index}",
        )
        for index in range(6)
    ]

    # Esperar a que una descarga haya SALIDO de verdad: a partir de ahi el reparto ya
    # ocurrio, que es lo que hace honesto al test. Meter la lectura antes la colaba dentro
    # de la ventana de agrupacion de 1 ms — el caso facil, y el motivo de que el test
    # anterior pasara con el bug puesto.
    while not salidas:
        await _real_sleep(0)

    # La lectura llega TARDE, con la cola de descargas ya andando: el reader interactivo
    # sobre descargas en curso. Con el heap repartido en bloque, las 6 descargas ya eran
    # duenas de sus huecos y la lectura solo podia ponerse la ULTIMA.
    read = asyncio.create_task(
        client.get("https://source.test/read", priority=SOURCE_READ_PRIORITY),
        name="read",
    )

    await asyncio.gather(*downloads, read)

    adelantadas = len(salidas) - 1 - salidas.index("https://source.test/read")
    assert adelantadas >= 2, f"la lectura no adelanto a las descargas en cola: {salidas}"


def test_sources_package_does_not_reimplement_rate_limiting():
    # El test de shell del plan usa rg; esta asercion deja el mismo diente en la suite.
    import pathlib

    sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in pathlib.Path("nyanko_api/sources").glob("*.py")
    )

    assert "class RateLimited" not in sources
    assert "next_slot" not in sources
    assert "Semaphore" not in sources
