from __future__ import annotations

import mimetypes
import re
import zipfile
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from .contract import (
    SOURCE_API_VERSION,
    SourceCapabilities,
    SourceChapter,
    SourceFetcher,
    SourcePage,
    SourcePageContent,
    SourceSeries,
)
from .errors import SourceNotFoundError, SourceParseError, SourceUnsupportedError

IMAGE_EXTENSIONS = frozenset(".jpg .jpeg .png .webp .gif .avif".split())
ARCHIVE_EXTENSIONS = frozenset((".cbz", ".zip"))
UNSUPPORTED_ARCHIVE_EXTENSIONS = frozenset((".cbr", ".rar"))
ARCHIVE_MEMBER_SEPARATOR = "!"
COMIC_INFO_MAX_BYTES = 1024 * 1024

# La frontera archivo/miembro se DERIVA de los datos: el separador solo es estructural
# cuando sigue a una extension de archivo, porque en un nombre de serie (`Yotsuba&!`,
# `Bakuman!`, `Oh My Goddess!`) el `!` es un caracter legal y corriente. Partir por el
# primero convertia esas bibliotecas enteras en 404.
# IGNORECASE casa `.CBZ!` SIN transformar la cadena, asi que los indices del match caen
# sobre el id original; pasarlo por `.lower()` podria alargarlo ('İ'.lower() son DOS
# caracteres) y desplazar el corte. ASCII impide que esa misma 'İ' case con la `i` de
# `.zip`. El patron se construye desde las constantes de arriba (sorted() para que sea
# estable entre procesos): una lista escrita a mano es una lista que un dia no se
# actualiza. Las no soportadas van incluidas a proposito: sin `.cbr!` el id no parte y
# el error deja de ser el 415 "conviertelo a CBZ" para pasar a un 404 enganoso.
# ponytail: un directorio llamado literalmente `Foo.zip!bar` daria un falso positivo;
# fuera de alcance hasta que exista.
_ARCHIVE_MEMBER_BOUNDARY = re.compile(
    "("
    + "|".join(
        re.escape(extension)
        for extension in sorted(ARCHIVE_EXTENSIONS | UNSUPPORTED_ARCHIVE_EXTENSIONS)
    )
    + ")"
    + re.escape(ARCHIVE_MEMBER_SEPARATOR),
    re.IGNORECASE | re.ASCII,
)

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
                (
                    path
                    for path in series_path.iterdir()
                    if path.is_dir()
                    or path.suffix.lower()
                    in ARCHIVE_EXTENSIONS | UNSUPPORTED_ARCHIVE_EXTENSIONS
                ),
                key=lambda path: _natural_key(path.name),
            )
        except OSError as error:
            raise SourceParseError("No se pudo listar la serie local") from error
        if not chapter_paths:
            raise SourceParseError("La serie local no tiene capitulos")
        chapters: list[SourceChapter] = []
        for path in chapter_paths:
            comic_info = self._comic_info(path)
            number_text = comic_info.get("Number")
            try:
                is_directory = path.is_dir()
                has_images = is_directory and any(
                    child.is_file() and child.suffix.lower() in IMAGE_EXTENSIONS
                    for child in path.iterdir()
                )
            except OSError as error:
                raise SourceParseError("No se pudo listar el capitulo local") from error
            chapters.append(
                SourceChapter(
                    source_id=self._make_id(root_key, root, path),
                    title=comic_info.get("Title") or path.name,
                    series_id=self._make_id(root_key, root, series_path),
                    source_name=self.name,
                    number=(
                        self._chapter_number(number_text)
                        if number_text is not None
                        else self._chapter_number(path.name)
                    ),
                    is_chapter=not is_directory or has_images,
                )
            )
        return chapters

    async def pages(self, chapter: SourceChapter | str) -> list[SourcePage]:
        chapter_id = chapter.source_id if isinstance(chapter, SourceChapter) else chapter
        root_key, root, chapter_path = self._resolve_id(chapter_id)
        if chapter_path.is_dir():
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

        if not chapter_path.is_file():
            raise SourceNotFoundError("Capitulo local no encontrado")
        suffix = chapter_path.suffix.lower()
        if suffix in UNSUPPORTED_ARCHIVE_EXTENSIONS:
            raise SourceUnsupportedError("Formato no soportado: conviertelo a CBZ")
        if suffix not in ARCHIVE_EXTENSIONS:
            raise SourceNotFoundError("Capitulo local no encontrado")
        try:
            with zipfile.ZipFile(chapter_path) as archive:
                members = sorted(
                    (
                        member
                        for member in archive.namelist()
                        if not member.endswith("/")
                        and Path(member).suffix.lower() in IMAGE_EXTENSIONS
                    ),
                    key=_natural_key,
                )
        except (OSError, zipfile.BadZipFile) as error:
            raise SourceParseError("No se pudo leer el archivo del capitulo") from error
        if not members:
            raise SourceParseError("El capitulo local no tiene paginas")
        opaque_chapter_id = self._make_id(root_key, root, chapter_path)
        return [
            SourcePage(
                source_id=(
                    f"{opaque_chapter_id}{ARCHIVE_MEMBER_SEPARATOR}{member}"
                ),
                chapter_id=opaque_chapter_id,
                index=index,
                filename=Path(member).name,
                source_name=self.name,
            )
            for index, member in enumerate(members, start=1)
        ]

    async def page_bytes(self, page: SourcePage | str) -> SourcePageContent:
        page_id = page.source_id if isinstance(page, SourcePage) else page
        # search() devuelve la coincidencia mas a la IZQUIERDA: la frontera es la primera
        # extension seguida del separador; lo que venga despues es miembro, `!` incluido.
        match = _ARCHIVE_MEMBER_BOUNDARY.search(page_id)
        archive_id = page_id[: match.end(1)] if match else page_id
        member = page_id[match.end() :] if match else None
        _, _, candidate = self._resolve_id(archive_id)

        if member is None:
            if not candidate.is_file() or candidate.suffix.lower() not in IMAGE_EXTENSIONS:
                raise SourceNotFoundError("Pagina local no encontrada")
            media_type = mimetypes.guess_type(candidate.name)[0]
            return SourcePageContent(
                media_type=media_type or "application/octet-stream",
                path=candidate,
            )

        suffix = candidate.suffix.lower()
        if suffix in UNSUPPORTED_ARCHIVE_EXTENSIONS:
            raise SourceUnsupportedError("Formato no soportado: conviertelo a CBZ")
        if not candidate.is_file() or suffix not in ARCHIVE_EXTENSIONS:
            raise SourceNotFoundError("Archivo local no encontrado")
        try:
            with zipfile.ZipFile(candidate) as archive:
                if member not in archive.namelist():
                    raise SourceNotFoundError("Pagina local no encontrada")
        except (OSError, zipfile.BadZipFile) as error:
            raise SourceParseError("No se pudo leer el archivo del capitulo") from error

        def chunks() -> Iterator[bytes]:
            # Abrir ambos recursos dentro del generador evita servir desde un fichero ya
            # cerrado y tambien filtrar el descriptor si el consumidor corta la respuesta.
            with zipfile.ZipFile(candidate) as archive:
                with archive.open(member) as content:
                    while block := content.read(64 * 1024):
                        yield block

        media_type = mimetypes.guess_type(member)[0]
        return SourcePageContent(
            media_type=media_type or "application/octet-stream",
            chunks=chunks(),
        )

    def _chapter_number(self, name: str) -> float | None:
        match = re.search(r"\d+(?:\.\d+)?", name)
        return float(match.group()) if match else None

    def _comic_info(self, chapter_path: Path) -> dict[str, str]:
        raw: bytes
        try:
            if chapter_path.is_dir():
                comic_info_path = chapter_path / "ComicInfo.xml"
                if not comic_info_path.is_file():
                    return {}
                if comic_info_path.stat().st_size > COMIC_INFO_MAX_BYTES:
                    return {}
                raw = comic_info_path.read_bytes()
            elif chapter_path.suffix.lower() in ARCHIVE_EXTENSIONS:
                with zipfile.ZipFile(chapter_path) as archive:
                    member_name = next(
                        (
                            name
                            for name in archive.namelist()
                            if name.lower() == "comicinfo.xml"
                        ),
                        None,
                    )
                    if member_name is None:
                        return {}
                    member = archive.getinfo(member_name)
                    if member.file_size > COMIC_INFO_MAX_BYTES:
                        return {}
                    raw = archive.read(member_name)
            else:
                return {}
        except (OSError, KeyError, zipfile.BadZipFile):
            return {}

        upper = raw.upper().replace(b"\x00", b"")
        if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
            return {}
        try:
            root = ElementTree.fromstring(raw)
        except ElementTree.ParseError:
            return {}
        metadata: dict[str, str] = {}
        for name in ("Number", "Title", "Series", "PageCount"):
            element = root.find(name)
            if element is not None and element.text and element.text.strip():
                metadata[name] = element.text.strip()
        return metadata

    def _load_roots(self, library_folders: Iterable[Mapping[str, Any] | str]) -> dict[str, Path]:
        """Único camino a las raíces de manga (los 3 build_source_registry pasan por
        aquí), así que el filtro por tipo vive aquí y no en los llamantes. Sin tipo ⇒
        ambas — mismo criterio que la migración; una carpeta que llega como `str` no
        lleva tipo y se acepta."""
        roots: dict[str, Path] = {}
        for index, folder in enumerate(library_folders):
            if isinstance(folder, Mapping):
                if (folder.get("kind") or "ambas") not in ("manga", "ambas"):
                    continue
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
