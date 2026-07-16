from __future__ import annotations

import ast
import inspect
import sys
import tempfile
import types
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import fields, is_dataclass
from pathlib import Path

import pytest

from nyanko_api.sources import (
    SOURCES,
    LocalArchiveSource,
    SourceEngine,
    build_source_registry,
)
from nyanko_api.sources.contract import (
    SOURCE_API_VERSION,
    Source,
    SourceCapabilities,
    SourceChapter,
    SourcePage,
    SourcePageContent,
    SourceSeries,
)
from nyanko_api.sources.errors import (
    SourceError,
    SourceNetworkError,
    SourceNotFoundError,
    SourceParseError,
    SourceRateLimitError,
    SourceUnsupportedError,
    source_error_action,
)
from nyanko_api.sources.registry import SourceRegistry

_NETWORK_IMPORTS = {"httpx", "requests", "urllib", "aiohttp"}


class _Fetcher:
    async def request(self, _method: str, _url: str, **_kwargs):
        return None


class _FuenteOk:
    name = "ok"
    display_name = "OK"
    api_version = SOURCE_API_VERSION
    capabilities = SourceCapabilities()

    async def search(self, query: str, limit: int = 20) -> list[SourceSeries]:
        return [SourceSeries(source_id=query, title=query)][:limit]

    async def chapters(self, series: SourceSeries | str) -> list[SourceChapter]:
        series_id = series.source_id if isinstance(series, SourceSeries) else series
        return [SourceChapter(source_id="c1", title="1", series_id=series_id)]

    async def pages(self, chapter: SourceChapter | str) -> list[SourcePage]:
        chapter_id = chapter.source_id if isinstance(chapter, SourceChapter) else chapter
        return [SourcePage(source_id="p1", chapter_id=chapter_id, index=1, filename="1.jpg")]

    async def page_bytes(self, page: SourcePage | str) -> SourcePageContent:
        return SourcePageContent(
            media_type="image/jpeg",
            chunks=(chunk for chunk in (b"pagina",)),
        )


def test_source_api_version_is_exact_integer():
    contract = Path("nyanko_api/sources/contract.py").read_text(encoding="utf-8")

    # page_bytes hizo incompatible el contrato (D-16). Como el registro exige una
    # coincidencia exacta, la version 2 separa extensiones viejas de fallos silenciosos.
    assert SOURCE_API_VERSION == 2
    assert "SOURCE_API_VERSION = 2" in contract


def test_source_protocol_is_runtime_checkable_and_minimal():
    methods = {
        name
        for name, value in Source.__dict__.items()
        if inspect.isfunction(value) and not name.startswith("_")
    }

    assert getattr(Source, "_is_runtime_protocol")
    assert methods == {"search", "chapters", "pages", "page_bytes"}

    contract = Path("nyanko_api/sources/contract.py").read_text(encoding="utf-8")
    assert "popular" not in contract
    assert "latest" not in contract
    assert "series_detail" not in contract


def test_source_capabilities_are_data():
    names = {field.name for field in fields(SourceCapabilities)}

    assert is_dataclass(SourceCapabilities)
    assert SourceCapabilities.__dataclass_params__.frozen
    assert hasattr(SourceCapabilities, "__slots__")
    assert {"headers", "requests_per_minute"} <= names


def test_source_page_content_is_frozen_data():
    assert is_dataclass(SourcePageContent)
    assert SourcePageContent.__dataclass_params__.frozen
    assert hasattr(SourcePageContent, "__slots__")
    assert [field.name for field in fields(SourcePageContent)] == [
        "media_type",
        "path",
        "chunks",
    ]


def test_source_domain_types_are_not_tracker_models():
    for domain_type in (SourceSeries, SourceChapter, SourcePage, SourcePageContent):
        assert domain_type.__module__ == "nyanko_api.sources.contract"

    contract = Path("nyanko_api/sources/contract.py").read_text(encoding="utf-8")
    assert "nyanko_api.models" not in contract


@pytest.mark.asyncio
async def test_zero_parse_results_raise_source_parse_error():
    class FuenteVacia:
        async def search(self, _query: str) -> list[SourceSeries]:
            resultados: list[SourceSeries] = []
            if not resultados:
                raise SourceParseError("sin resultados")
            return resultados

    with pytest.raises(SourceParseError):
        await FuenteVacia().search("berserk")


def test_source_error_action_depends_on_type_not_message():
    assert source_error_action(SourceNetworkError("mismo mensaje")) == "reintentar"
    assert source_error_action(SourceParseError("mismo mensaje")) == "actualizar_la_fuente"
    assert source_error_action(SourceRateLimitError("mismo mensaje")) == "esperar"


@pytest.mark.parametrize("source_class", SOURCES, ids=lambda source_class: source_class.name)
def test_real_sources_match_protocol(source_class):
    with _workdir(f"protocol-{source_class.name}") as root:
        source = source_class(_Fetcher(), [{"id": "0", "path": str(root)}])

        assert isinstance(source, Source)
        _assert_source_signature(source, "search", ("query", "limit"))
        _assert_source_signature(source, "chapters", ("series",))
        _assert_source_signature(source, "pages", ("chapter",))
        _assert_source_signature(source, "page_bytes", ("page",))


def test_source_engine_is_part_of_the_public_package():
    assert SourceEngine.__module__ == "nyanko_api.sources.engine"


def test_sources_init_uses_explicit_list():
    package = Path("nyanko_api/sources/__init__.py").read_text(encoding="utf-8")

    assert "from .local_archive import LocalArchiveSource" in package
    assert "SOURCES = [LocalArchiveSource]" in package


def test_sources_do_not_use_runtime_autodiscovery():
    for path in Path("nyanko_api/sources").glob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert "pkgutil" not in source
        assert "importlib" not in source
        assert "__subclasses__" not in source


def test_registry_keeps_wrong_api_version_visible():
    class FuenteV1(_FuenteOk):
        name = "v1"
        api_version = 1

    registry = SourceRegistry()
    registry.register(FuenteV1())
    registry.register(_FuenteOk())
    registration = registry.status("v1")

    assert registration.status == "rejected"
    assert registration.rejection_reason
    assert "1" in registration.rejection_reason
    assert "2" in registration.rejection_reason
    assert registry.status("ok").status == "ok"
    assert [source.name for source in registry.all()] == ["ok"]


def test_registry_keeps_loading_errors_visible():
    class FuenteRota:
        name = "rota"
        display_name = "Rota"

        def __init__(self, fetcher, library_folders):
            raise RuntimeError("boom")

    registry = build_source_registry(
        fetcher=_Fetcher(),
        library_folders=[],
        sources=[FuenteRota],
    )
    registration = registry.status("rota")

    assert registration.status == "rejected"
    assert registration.rejection_reason
    assert "boom" in registration.rejection_reason


def test_registry_rejects_duplicate_source_names():
    with pytest.raises(ValueError, match="Source already registered: ok"):
        SourceRegistry([_FuenteOk(), _FuenteOk()])


def test_registry_rejects_source_with_invalid_capabilities():
    class _FuenteCapabilidadesBasura(_FuenteOk):
        name = "basura"
        capabilities = 42

    registry = SourceRegistry([_FuenteCapabilidadesBasura()])

    assert registry.status("basura").status == "rejected"
    assert registry.all() == []


def test_a_broken_source_never_takes_down_the_sidecar():
    class _FuenteQueRevienta(_FuenteOk):
        name = "revienta"

        def __init__(self, *_args, **_kwargs):
            raise RuntimeError("boom en el constructor")

    class _FuenteSinNombre(_FuenteOk):
        name = None

    # Nombre duplicado: register() lanza ValueError. Antes escapaba de
    # build_source_registry y el sidecar no arrancaba.
    registry = build_source_registry(
        fetcher=_Fetcher(),
        sources=[_FuenteOk, _FuenteOk, _FuenteQueRevienta, _FuenteSinNombre],
    )

    assert registry.status("ok").status == "ok"
    assert registry.status("revienta").status == "rejected"
    assert [source.name for source in registry.all()] == ["ok"]


@pytest.mark.asyncio
async def test_local_archive_lists_chapters_with_opaque_ids():
    with _workdir("chapters") as root:
        (root / "Cap 1").mkdir()
        (root / "Cap 2").mkdir()
        (root / "Cap 1" / "1.jpg").write_bytes(b"pagina")
        source = LocalArchiveSource(_Fetcher(), [{"id": "0", "path": str(root)}])

        chapters = await source.chapters(SourceSeries(source_id="0:.", title="Biblioteca"))

        assert [chapter.title for chapter in chapters] == ["Cap 1", "Cap 2"]
        assert [chapter.number for chapter in chapters] == [1.0, 2.0]
        assert [chapter.is_chapter for chapter in chapters] == [True, False]
        assert all(str(root) not in chapter.source_id for chapter in chapters)
        assert all(not Path(chapter.source_id).is_absolute() for chapter in chapters)


@pytest.mark.asyncio
async def test_local_archive_lists_only_images_in_natural_order():
    with _workdir("pages") as root:
        chapter_dir = root / "Cap 1"
        chapter_dir.mkdir()
        for name in ["2.jpg", "10.jpg", "1.jpg", "ComicInfo.xml", "extra.cbz", "nota.txt"]:
            (chapter_dir / name).write_text("x", encoding="utf-8")
        source = LocalArchiveSource(_Fetcher(), [{"id": "0", "path": str(root)}])

        pages = await source.pages("0:Cap 1")

        assert [page.filename for page in pages] == ["1.jpg", "2.jpg", "10.jpg"]
        assert [page.index for page in pages] == [1, 2, 3]


@pytest.mark.asyncio
async def test_archivo_local_iguala_zip_y_carpeta_en_orden_natural(tmp_path):
    chapter_dir = tmp_path / "Cap 1"
    chapter_dir.mkdir()
    for name in ("2.jpg", "10.jpg", "1.jpg"):
        (chapter_dir / name).write_bytes(name.encode())
    archive_path = tmp_path / "Cap 2.cbz"
    with zipfile.ZipFile(archive_path, "w") as archive:
        for name in ("2.jpg", "10.jpg", "1.jpg"):
            archive.writestr(name, name.encode())
        archive.writestr("nota.txt", b"ignorada")

    source = LocalArchiveSource(_Fetcher(), [{"id": "0", "path": str(tmp_path)}])
    directory_pages = await source.pages("0:Cap 1")
    archive_pages = await source.pages("0:Cap 2.cbz")

    assert [(page.filename, page.index) for page in directory_pages] == [
        (page.filename, page.index) for page in archive_pages
    ] == [("1.jpg", 1), ("2.jpg", 2), ("10.jpg", 3)]
    assert all("!" not in page.source_id for page in directory_pages)
    assert all("!" in page.source_id for page in archive_pages)
    assert all(str(tmp_path) not in page.source_id for page in archive_pages)
    assert all(not Path(page.source_id).is_absolute() for page in archive_pages)


@pytest.mark.asyncio
async def test_comic_info_del_cbz_manda_sobre_el_nombre(tmp_path):
    archive_path = tmp_path / "Cap 003.cbz"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("1.jpg", b"pagina")
        archive.writestr(
            "comicinfo.XML",
            "<ComicInfo><Number>12.5</Number><Title>El eclipse</Title></ComicInfo>",
        )
    source = LocalArchiveSource(_Fetcher(), [{"id": "0", "path": str(tmp_path)}])

    chapter = (await source.chapters("0:."))[0]

    assert chapter.number == 12.5
    assert isinstance(chapter.number, float)
    assert chapter.title == "El eclipse"

    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("1.jpg", b"pagina")

    chapter_without_metadata = (await source.chapters("0:."))[0]
    assert chapter_without_metadata.number == 3.0
    assert chapter_without_metadata.title == "Cap 003.cbz"


@pytest.mark.asyncio
async def test_comic_info_malformado_degrada_al_nombre(tmp_path):
    archive_path = tmp_path / "Cap 004.cbz"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("1.jpg", b"pagina")
        archive.writestr("ComicInfo.xml", b"<ComicInfo><Number>99")
    source = LocalArchiveSource(_Fetcher(), [{"id": "0", "path": str(tmp_path)}])

    chapter = (await source.chapters("0:."))[0]

    assert chapter.number == 4.0
    assert chapter.title == "Cap 004.cbz"


@pytest.mark.asyncio
async def test_comic_info_peligroso_o_desmedido_no_se_parsea(tmp_path, monkeypatch):
    entity_archive = tmp_path / "Cap 005.cbz"
    with zipfile.ZipFile(entity_archive, "w") as archive:
        archive.writestr("1.jpg", b"pagina")
        archive.writestr(
            "ComicInfo.xml",
            b'<!DOCTYPE comic [<!ENTITY x "boom">]>'
            b"<ComicInfo><Number>&x;</Number></ComicInfo>",
        )
    huge_archive = tmp_path / "Cap 006.cbz"
    with zipfile.ZipFile(huge_archive, "w") as archive:
        archive.writestr("1.jpg", b"pagina")
        archive.writestr("ComicInfo.xml", b" " * (1024 * 1024 + 1))
    utf16_archive = tmp_path / "Cap 007.cbz"
    with zipfile.ZipFile(utf16_archive, "w") as archive:
        archive.writestr("1.jpg", b"pagina")
        archive.writestr(
            "ComicInfo.xml",
            '<!DOCTYPE comic [<!ENTITY x "boom">]>'
            "<ComicInfo><Number>&x;</Number></ComicInfo>".encode("utf-16"),
        )

    def fail_if_called(_raw):
        raise AssertionError("El XML peligroso se descarto antes de parsearlo")

    monkeypatch.setattr(
        "nyanko_api.sources.local_archive.ElementTree.fromstring", fail_if_called
    )
    source = LocalArchiveSource(_Fetcher(), [{"id": "0", "path": str(tmp_path)}])

    chapters = await source.chapters("0:.")

    assert [chapter.number for chapter in chapters] == [5.0, 6.0, 7.0]


@pytest.mark.asyncio
async def test_cbr_se_rechaza_sin_intentar_abrirlo(tmp_path):
    (tmp_path / "Cap 7.cbr").write_bytes(b"esto no es un archivo")
    source = LocalArchiveSource(_Fetcher(), [{"id": "0", "path": str(tmp_path)}])

    with pytest.raises(SourceUnsupportedError, match="CBZ"):
        await source.pages("0:Cap 7.cbr")


@pytest.mark.asyncio
async def test_page_bytes_devuelve_path_para_imagen_suelta(tmp_path):
    image_path = tmp_path / "pagina.jpg"
    image_path.write_bytes(b"jpeg")
    source = LocalArchiveSource(_Fetcher(), [{"id": "0", "path": str(tmp_path)}])

    content = await source.page_bytes("0:pagina.jpg")

    assert content.path == image_path
    assert content.chunks is None
    assert content.media_type == "image/jpeg"


@pytest.mark.asyncio
async def test_page_bytes_transmite_el_miembro_cbz_exacto(tmp_path):
    expected = b"bytes exactos del zip"
    archive_path = tmp_path / "Cap 8.cbz"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("carpeta/pagina.jpg", expected)
    source = LocalArchiveSource(_Fetcher(), [{"id": "0", "path": str(tmp_path)}])
    page = (await source.pages("0:Cap 8.cbz"))[0]

    content = await source.page_bytes(page)

    assert content.path is None
    assert content.chunks is not None
    assert content.media_type == "image/jpeg"
    assert b"".join(content.chunks) == expected


@pytest.mark.asyncio
async def test_page_bytes_rechaza_ids_fuera_de_la_biblioteca(tmp_path):
    archive_path = tmp_path / "Cap1.cbz"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("1.jpg", b"pagina")
    source = LocalArchiveSource(_Fetcher(), [{"id": "0", "path": str(tmp_path)}])

    for page_id in (
        "0:../../etc/passwd",
        "0:Cap1.cbz!../../../etc/passwd",
        "raiz-no-registrada:x.jpg",
    ):
        with pytest.raises(SourceError):
            await source.page_bytes(page_id)


@pytest.mark.asyncio
async def test_zip_corrupto_o_sin_imagenes_es_error_de_parseo(tmp_path):
    (tmp_path / "corrupto.cbz").write_bytes(b"no es zip")
    with zipfile.ZipFile(tmp_path / "vacio.cbz", "w") as archive:
        archive.writestr("nota.txt", b"sin paginas")
    source = LocalArchiveSource(_Fetcher(), [{"id": "0", "path": str(tmp_path)}])

    for chapter_id in ("0:corrupto.cbz", "0:vacio.cbz"):
        with pytest.raises(SourceParseError):
            await source.pages(chapter_id)


@pytest.mark.asyncio
async def test_local_archive_lists_chapters_in_natural_order():
    with _workdir("chapter-order") as root:
        for name in ["Cap 2", "Cap 10", "Cap 1"]:
            (root / name).mkdir()
        source = LocalArchiveSource(_Fetcher(), [{"id": "0", "path": str(root)}])

        chapters = await source.chapters(SourceSeries(source_id="0:.", title="Biblioteca"))

        assert [chapter.title for chapter in chapters] == ["Cap 1", "Cap 2", "Cap 10"]


@pytest.mark.asyncio
async def test_local_archive_rejects_traversal_ids():
    with _workdir("traversal") as root:
        outside = root.parent / "outside"
        outside.mkdir(exist_ok=True)
        source = LocalArchiveSource(_Fetcher(), [{"id": "0", "path": str(root)}])

        with pytest.raises(SourceError):
            await source.pages("0:../outside")

        with pytest.raises(SourceNotFoundError):
            await source.pages("missing:.")


def test_registered_source_modules_do_not_import_network_clients():
    with _workdir("import-guard") as root:
        registry = build_source_registry(
            fetcher=_Fetcher(),
            library_folders=[{"id": "0", "path": str(root)}],
        )

        for source in registry.all():
            assert _network_imports_for_source(source) == set()


def test_network_import_guard_fails_for_registered_source_with_httpx():
    module_name = "fuente_con_red_test"
    with _workdir("bad-import") as root:
        module_path = root / f"{module_name}.py"
        module_path.write_text(
            "import httpx\n\nclass FuenteConRed:\n    pass\n",
            encoding="utf-8",
        )
        module = types.ModuleType(module_name)
        module.__file__ = str(module_path)
        sys.modules[module_name] = module
        try:
            source = module_path.read_text(encoding="utf-8")
            exec(compile(source, str(module_path), "exec"), module.__dict__)
            assert _network_imports_for_source(module.FuenteConRed()) == {"httpx"}
        finally:
            sys.modules.pop(module_name, None)


def _assert_source_signature(source: Source, name: str, parameters: tuple[str, ...]) -> None:
    assert inspect.iscoroutinefunction(getattr(type(source), name))
    assert tuple(inspect.signature(getattr(source, name)).parameters) == parameters


def _network_imports_for_source(source: Source) -> set[str]:
    source_file = inspect.getsourcefile(type(source))
    assert source_file is not None
    tree = ast.parse(Path(source_file).read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".", 1)[0])
    return imports & _NETWORK_IMPORTS


@contextmanager
def _workdir(name: str) -> Iterator[Path]:
    with tempfile.TemporaryDirectory(prefix=f"nyanko-{name}-") as path:
        yield Path(path)
