from __future__ import annotations

import inspect
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Literal

from .contract import SOURCE_API_VERSION, Source, SourceCapabilities, SourceFetcher
from .engine import build_source_fetcher

SourceStatus = Literal["ok", "rejected"]


@dataclass(frozen=True, slots=True)
class SourceRegistration:
    name: str
    display_name: str
    status: SourceStatus
    source: Source | None = None
    rejection_reason: str | None = None


class SourceRegistry:
    def __init__(self, sources: Iterable[Source] = ()):
        self._sources: dict[str, Source] = {}
        self._registrations: dict[str, SourceRegistration] = {}
        for source in sources:
            self.register(source)

    def register(self, source: Source) -> None:
        name = _source_attr(source, "name")
        display_name = _source_attr(source, "display_name", name)
        if name in self._registrations:
            raise ValueError(f"Source already registered: {name}")
        api_version = getattr(source, "api_version", None)
        if api_version != SOURCE_API_VERSION:
            self._reject(
                name,
                display_name,
                f"Version de API incompatible: fuente={api_version}, app={SOURCE_API_VERSION}",
            )
            return
        if not isinstance(source, Source):
            self._reject(name, display_name, "La fuente no cumple el contrato Source")
            return
        self._sources[name] = source
        self._registrations[name] = SourceRegistration(
            name=name,
            display_name=display_name,
            status="ok",
            source=source,
        )

    def reject(self, name: str, display_name: str, reason: str) -> None:
        if name in self._registrations:
            raise ValueError(f"Source already registered: {name}")
        self._reject(name, display_name, reason)

    def get(self, name: str) -> Source:
        try:
            return self._sources[name]
        except KeyError as error:
            raise KeyError(f"Unknown source: {name}") from error

    def all(self) -> list[Source]:
        return list(self._sources.values())

    def status(self, name: str) -> SourceRegistration:
        try:
            return self._registrations[name]
        except KeyError as error:
            raise KeyError(f"Unknown source: {name}") from error

    def registrations(self) -> list[SourceRegistration]:
        return list(self._registrations.values())

    def _reject(self, name: str, display_name: str, reason: str) -> None:
        self._registrations[name] = SourceRegistration(
            name=name,
            display_name=display_name,
            status="rejected",
            rejection_reason=reason,
        )


def build_source_registry(
    *,
    fetcher: SourceFetcher | None = None,
    library_folders: Iterable[Mapping[str, Any] | str] = (),
    sources: Iterable[Callable[..., Source]] | None = None,
) -> SourceRegistry:
    if sources is None:
        from . import SOURCES

        sources = SOURCES

    registry = SourceRegistry()
    for source_factory in sources:
        try:
            source_fetcher = fetcher or build_source_fetcher(_source_capabilities(source_factory))
            source = _instantiate_source(source_factory, source_fetcher, library_folders)
            _inject_fetcher(source, source_fetcher)
        except Exception as error:
            name = _source_attr(source_factory, "name", source_factory.__name__)
            display_name = _source_attr(source_factory, "display_name", name)
            registry.reject(name, display_name, f"No se pudo cargar la fuente: {error}")
            continue
        registry.register(source)
    return registry


def _instantiate_source(
    source_factory: Callable[..., Source],
    fetcher: SourceFetcher | None,
    library_folders: Iterable[Mapping[str, Any] | str],
) -> Source:
    parameters = inspect.signature(source_factory).parameters
    if "library_folders" in parameters:
        return source_factory(fetcher=fetcher, library_folders=library_folders)
    if "fetcher" in parameters:
        return source_factory(fetcher=fetcher)
    if len(parameters) >= 2:
        return source_factory(fetcher, library_folders)
    if len(parameters) == 1:
        return source_factory(fetcher)
    return source_factory()


def _source_attr(source: object, name: str, default: str | None = None) -> str:
    value = getattr(source, name, default)
    if value is None:
        raise AttributeError(f"Source missing {name}")
    return str(value)


def _source_capabilities(source: object) -> SourceCapabilities:
    capabilities = getattr(source, "capabilities", None)
    if isinstance(capabilities, SourceCapabilities):
        return capabilities
    return SourceCapabilities()


def _inject_fetcher(source: Source, fetcher: SourceFetcher) -> None:
    try:
        setattr(source, "fetcher", fetcher)
    except (AttributeError, TypeError):
        return
