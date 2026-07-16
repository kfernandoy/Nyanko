from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

SOURCE_API_VERSION = 2


@dataclass(frozen=True, slots=True)
class SourceCapabilities:
    search: bool = True
    headers: Mapping[str, str] = field(default_factory=dict)
    requests_per_minute: int = 60


@dataclass(frozen=True, slots=True)
class SourceSeries:
    source_id: str
    title: str
    source_name: str = ""


@dataclass(frozen=True, slots=True)
class SourceChapter:
    source_id: str
    title: str
    series_id: str
    source_name: str = ""
    number: float | None = None
    is_chapter: bool = True


@dataclass(frozen=True, slots=True)
class SourcePage:
    source_id: str
    chapter_id: str
    index: int
    filename: str
    source_name: str = ""


@dataclass(frozen=True, slots=True)
class SourcePageContent:
    """Contenido de pagina: exactamente uno de ``path`` o ``chunks`` no es ``None``.

    ``path`` permite servir un fichero de disco sin copiarlo a memoria; ``chunks``
    cubre contenido que no es un fichero suelto, como un miembro ZIP o un CDN.
    """

    media_type: str
    path: Path | None = None
    chunks: Iterator[bytes] | None = None


class SourceFetcher(Protocol):
    async def request(self, method: str, url: str, **kwargs: Any) -> Any: ...


@runtime_checkable
class Source(Protocol):
    name: str
    display_name: str
    api_version: int
    capabilities: SourceCapabilities

    async def search(self, query: str, limit: int = 20) -> list[SourceSeries]: ...

    async def chapters(self, series: SourceSeries | str) -> list[SourceChapter]: ...

    async def pages(self, chapter: SourceChapter | str) -> list[SourcePage]: ...

    async def page_bytes(self, page: SourcePage | str) -> SourcePageContent: ...
