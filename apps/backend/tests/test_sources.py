from __future__ import annotations

import ast
import inspect
import sys
import tempfile
import types
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import fields, is_dataclass
from pathlib import Path

import pytest

from nyanko_api.sources import SOURCES, LocalArchiveSource, build_source_registry
from nyanko_api.sources.contract import (
    SOURCE_API_VERSION,
    Source,
    SourceCapabilities,
    SourceChapter,
    SourcePage,
    SourceSeries,
)
from nyanko_api.sources.errors import (
    SourceError,
    SourceNetworkError,
    SourceNotFoundError,
    SourceParseError,
    SourceRateLimitError,
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


def test_source_api_version_is_exact_integer():
    contract = Path("nyanko_api/sources/contract.py").read_text(encoding="utf-8")

    assert SOURCE_API_VERSION == 1
    assert "SOURCE_API_VERSION = 1" in contract


def test_source_protocol_is_runtime_checkable_and_minimal():
    methods = {
        name
        for name, value in Source.__dict__.items()
        if inspect.isfunction(value) and not name.startswith("_")
    }

    assert getattr(Source, "_is_runtime_protocol")
    assert methods == {"search", "chapters", "pages"}

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


def test_source_domain_types_are_not_tracker_models():
    for domain_type in (SourceSeries, SourceChapter, SourcePage):
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
    class FuenteV2(_FuenteOk):
        name = "v2"
        api_version = SOURCE_API_VERSION + 1

    registry = SourceRegistry()
    registry.register(FuenteV2())
    registration = registry.status("v2")

    assert registration.status == "rejected"
    assert registration.rejection_reason
    assert str(SOURCE_API_VERSION + 1) in registration.rejection_reason
    assert registry.all() == []


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


@pytest.mark.asyncio
async def test_local_archive_lists_chapters_with_opaque_ids():
    with _workdir("chapters") as root:
        (root / "Cap 1").mkdir()
        (root / "Cap 2").mkdir()
        source = LocalArchiveSource(_Fetcher(), [{"id": "0", "path": str(root)}])

        chapters = await source.chapters(SourceSeries(source_id="0:.", title="Biblioteca"))

        assert [chapter.title for chapter in chapters] == ["Cap 1", "Cap 2"]
        assert all(str(root) not in chapter.source_id for chapter in chapters)
        assert all(not Path(chapter.source_id).is_absolute() for chapter in chapters)


@pytest.mark.asyncio
async def test_local_archive_lists_only_images_in_lexicographic_order():
    with _workdir("pages") as root:
        chapter_dir = root / "Cap 1"
        chapter_dir.mkdir()
        for name in ["2.jpg", "10.jpg", "1.jpg", "ComicInfo.xml", "extra.cbz", "nota.txt"]:
            (chapter_dir / name).write_text("x", encoding="utf-8")
        source = LocalArchiveSource(_Fetcher(), [{"id": "0", "path": str(root)}])

        pages = await source.pages("0:Cap 1")

        assert [page.filename for page in pages] == ["1.jpg", "10.jpg", "2.jpg"]


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
