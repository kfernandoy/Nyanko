from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

SOURCE_API_VERSION = 1


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


@dataclass(frozen=True, slots=True)
class SourcePage:
    source_id: str
    chapter_id: str
    index: int
    filename: str
    source_name: str = ""


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
