from __future__ import annotations

import inspect
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from fastapi.testclient import TestClient

import nyanko_api.database as database_module
import nyanko_api.main as main_module
from nyanko_api.config import Settings
from nyanko_api.database import Database
from nyanko_api.main import app
from nyanko_api.sources import LocalArchiveSource
from nyanko_api.sources.contract import (
    SOURCE_API_VERSION,
    SourceCapabilities,
    SourceChapter,
    SourcePage,
    SourcePageContent,
    SourceSeries,
)
from nyanko_api.sources.errors import SourceParseError
from nyanko_api.sources.registry import SourceRegistry
from tests.test_persisted_urls import assert_no_persisted_urls

BACKEND_DIR = Path(__file__).resolve().parents[1]
SOURCE_IDENTITY_FIELDS = ("source_name", "source_id")


class _Fetcher:
    async def request(self, _method: str, _url: str, **_kwargs):
        return None


class _AlwaysFailSource:
    name = "always_fail"
    display_name = "Always Fail"
    api_version = SOURCE_API_VERSION
    capabilities = SourceCapabilities(
        headers={"Referer": "https://source.test/"},
        requests_per_minute=30,
    )

    async def search(self, query: str, limit: int = 20) -> list[SourceSeries]:
        raise SourceParseError("fallo de uso que no debe salir por /api/sources")

    async def chapters(self, series: SourceSeries | str) -> list[SourceChapter]:
        raise SourceParseError("fallo de uso que no debe salir por /api/sources")

    async def pages(self, chapter: SourceChapter | str) -> list[SourcePage]:
        raise SourceParseError("fallo de uso que no debe salir por /api/sources")

    async def page_bytes(self, page: SourcePage | str) -> SourcePageContent:
        return SourcePageContent(
            media_type="image/jpeg",
            chunks=(chunk for chunk in (b"pagina",)),
        )


class _WrongVersionSource(_AlwaysFailSource):
    name = "wrong_version"
    display_name = "Wrong Version"
    api_version = SOURCE_API_VERSION + 1


@contextmanager
def _installed_registry(registry: SourceRegistry):
    missing = object()
    previous = getattr(app.state, "source_registry", missing)
    app.state.source_registry = registry
    try:
        yield
    finally:
        if previous is missing:
            try:
                delattr(app.state, "source_registry")
            except AttributeError:
                pass
        else:
            app.state.source_registry = previous


def test_sources_endpoint_reports_ok_and_rejected_sources(tmp_path):
    registry = SourceRegistry(
        [
            LocalArchiveSource(_Fetcher(), [{"id": "0", "path": str(tmp_path)}]),
            _WrongVersionSource(),
            _AlwaysFailSource(),
        ]
    )

    with _installed_registry(registry):
        response = TestClient(app).get("/api/sources")

    assert response.status_code == 200
    payload = {item["name"]: item for item in response.json()}

    assert payload["local_archive"]["status"] == "ok"
    assert payload["local_archive"]["capabilities"]["search"] is False
    assert payload["wrong_version"]["status"] == "rejected"
    assert payload["wrong_version"]["rejection_reason"]
    assert payload["wrong_version"]["capabilities"] is None
    assert payload["always_fail"]["status"] == "ok"
    assert payload["always_fail"]["capabilities"]["headers"] == {
        "Referer": "https://source.test/"
    }
    assert "fallo de uso" not in response.text


def test_sources_endpoint_uses_live_registry_without_rebuilding(monkeypatch):
    registry = SourceRegistry([_AlwaysFailSource()])

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("GET /api/sources no debe reconstruir el registry")

    monkeypatch.setattr(main_module, "build_source_registry", fail_if_called)

    with _installed_registry(registry):
        client = TestClient(app)
        first = client.get("/api/sources")
        second = client.get("/api/sources")

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()


def test_lifespan_builds_source_registry_once(monkeypatch, tmp_path):
    registry = SourceRegistry([_AlwaysFailSource()])
    calls: list[dict] = []
    settings = Settings(data_dir=tmp_path / "data", api_port=0)
    missing = object()
    previous = getattr(app.state, "source_registry", missing)

    def build_once(**kwargs):
        calls.append(kwargs)
        return registry

    monkeypatch.setattr(main_module, "get_settings", lambda: settings)
    monkeypatch.setattr(main_module, "build_source_registry", build_once)

    try:
        with TestClient(app) as client:
            assert app.state.source_registry is registry
            assert client.get("/api/sources").status_code == 200
            assert client.get("/api/sources").status_code == 200
    finally:
        if previous is missing:
            try:
                delattr(app.state, "source_registry")
            except AttributeError:
                pass
        else:
            app.state.source_registry = previous

    assert len(calls) == 1
    assert calls[0] == {"library_folders": []}


def test_sources_endpoint_is_flat_and_handler_does_not_build_registry():
    main_source = (BACKEND_DIR / "nyanko_api" / "main.py").read_text(encoding="utf-8")
    handler_source = inspect.getsource(main_module.list_sources)

    assert "@app.get(\"/api/sources\"" in main_source
    assert "APIRouter" not in main_source
    assert "include_router" not in main_source
    assert "build_source_registry(" not in handler_source


def test_phase_2_does_not_add_source_persistence_columns(tmp_path):
    database = Database(tmp_path / "nyanko.sqlite3")
    database.initialize()

    with database.connect() as connection:
        columns = _columns(connection)
        assert_no_persisted_urls(connection)

    names = {column for _table, column in columns}
    assert "source_name" not in names
    assert "source_id" not in names
    assert "source_url" not in names
    assert "source_path" not in names
    assert "source_local" not in names
    assert set(SOURCE_IDENTITY_FIELDS) == {"source_name", "source_id"}
    assert all(
        "url" not in field and "path" not in field and "_local" not in field
        for field in SOURCE_IDENTITY_FIELDS
    )
    assert "source_name" not in database_module.SCHEMA
    assert "source_id" not in database_module.SCHEMA


def _columns(connection: sqlite3.Connection) -> list[tuple[str, str]]:
    tables = [
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    ]
    return [
        (table, row[1])
        for table in tables
        for row in connection.execute(f'PRAGMA table_info("{table}")')
    ]
