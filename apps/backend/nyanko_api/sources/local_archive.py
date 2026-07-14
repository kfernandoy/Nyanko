from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .contract import (
    SOURCE_API_VERSION,
    SourceCapabilities,
    SourceChapter,
    SourceFetcher,
    SourcePage,
    SourceSeries,
)
from .errors import SourceNotFoundError, SourceParseError, SourceUnsupportedError

IMAGE_EXTENSIONS = frozenset(".jpg .jpeg .png .webp .gif .avif".split())

_DIGITS = re.compile(r"(\d+)")


def _natural_key(name: str) -> tuple[object, ...]:
    """Ordena '2.jpg' antes que '10.jpg': el orden de cadena rompe la paginacion."""
    return tuple(
        int(part) if part.isdigit() else part.lower() for part in _DIGITS.split(name)
    )


@dataclass(frozen=True, slots=True)
class _Root:
    key: str
    path: Path


class LocalArchiveSource:
    name = "local_archive"
    display_name = "Archivo local"
    api_version = SOURCE_API_VERSION
    capabilities = SourceCapabilities(search=False, headers={}, requests_per_minute=1)

    def __init__(
        self,
        fetcher: SourceFetcher | None = None,
        library_folders: Iterable[Mapping[str, Any] | str] = (),
    ):
        self.fetcher = fetcher
        self._roots = self._load_roots(library_folders)

    async def search(self, query: str, limit: int = 20) -> list[SourceSeries]:
        raise SourceUnsupportedError("La fuente local no soporta busqueda")

    async def chapters(self, series: SourceSeries | str) -> list[SourceChapter]:
        series_id = series.source_id if isinstance(series, SourceSeries) else series
        root_key, root, series_path = self._resolve_id(series_id)
        if not series_path.is_dir():
            raise SourceNotFoundError("Serie local no encontrada")
        try:
            chapter_paths = sorted(
                (path for path in series_path.iterdir() if path.is_dir()),
                key=lambda path: _natural_key(path.name),
            )
        except OSError as error:
            raise SourceParseError("No se pudo listar la serie local") from error
        if not chapter_paths:
            raise SourceParseError("La serie local no tiene capitulos")
        return [
            SourceChapter(
                source_id=self._make_id(root_key, root, path),
                title=path.name,
                series_id=self._make_id(root_key, root, series_path),
                source_name=self.name,
            )
            for path in chapter_paths
        ]

    async def pages(self, chapter: SourceChapter | str) -> list[SourcePage]:
        chapter_id = chapter.source_id if isinstance(chapter, SourceChapter) else chapter
        root_key, root, chapter_path = self._resolve_id(chapter_id)
        if not chapter_path.is_dir():
            raise SourceNotFoundError("Capitulo local no encontrado")
        try:
            page_paths = sorted(
                (
                    path
                    for path in chapter_path.iterdir()
                    if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
                ),
                key=lambda path: _natural_key(path.name),
            )
        except OSError as error:
            raise SourceParseError("No se pudo listar el capitulo local") from error
        if not page_paths:
            raise SourceParseError("El capitulo local no tiene paginas")
        return [
            SourcePage(
                source_id=self._make_id(root_key, root, path),
                chapter_id=self._make_id(root_key, root, chapter_path),
                index=index,
                filename=path.name,
                source_name=self.name,
            )
            for index, path in enumerate(page_paths, start=1)
        ]

    def _load_roots(self, library_folders: Iterable[Mapping[str, Any] | str]) -> dict[str, Path]:
        roots: dict[str, Path] = {}
        for index, folder in enumerate(library_folders):
            if isinstance(folder, Mapping):
                raw_path = folder.get("path")
                raw_key = folder.get("id", index)
            else:
                raw_path = folder
                raw_key = index
            if not raw_path:
                continue
            path = Path(str(raw_path)).resolve()
            if path.is_dir():
                roots[str(raw_key)] = path
        return roots

    def _resolve_id(self, source_id: str) -> tuple[str, Path, Path]:
        root_key, relative = self._split_id(source_id)
        try:
            root = self._roots[root_key]
        except KeyError as error:
            raise SourceNotFoundError("Raiz local no registrada") from error

        candidate = (root / (relative or ".")).resolve()
        try:
            candidate.relative_to(root)
        except ValueError as error:
            raise SourceNotFoundError("Identificador local fuera de la biblioteca") from error
        return root_key, root, candidate

    def _split_id(self, source_id: str) -> tuple[str, str]:
        if ":" in source_id:
            root_key, relative = source_id.split(":", 1)
            return root_key, relative or "."
        if len(self._roots) == 1:
            root_key = next(iter(self._roots))
            return root_key, source_id or "."
        raise SourceNotFoundError("Identificador local ambiguo")

    def _make_id(self, root_key: str, root: Path, path: Path) -> str:
        return f"{root_key}:{path.relative_to(root).as_posix()}"
