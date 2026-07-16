from __future__ import annotations

import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from nyanko_api.database import Database
from nyanko_api.main import app, get_database
from nyanko_api.sources import (
    LocalArchiveSource,
    SourceNetworkError,
    SourceParseError,
    SourceRateLimitError,
    SourceRegistry,
    build_source_registry,
)
from nyanko_api.sources.contract import (
    SOURCE_API_VERSION,
    SourceCapabilities,
    SourceChapter,
    SourcePage,
    SourcePageContent,
    SourceSeries,
)
from tests.test_persisted_urls import assert_no_persisted_urls


class _Fetcher:
    async def request(self, _metodo: str, _url: str, **_opciones):
        return None


class _FuenteConError:
    name = "fuente_con_error"
    display_name = "Fuente con error"
    api_version = SOURCE_API_VERSION
    capabilities = SourceCapabilities()

    def __init__(self, error: Exception | None = None):
        self.error = error

    async def search(self, _consulta: str, _limite: int = 20) -> list[SourceSeries]:
        raise self.error

    async def chapters(self, serie: SourceSeries | str) -> list[SourceChapter]:
        if self.error is not None:
            raise self.error
        series_id = serie.source_id if isinstance(serie, SourceSeries) else serie
        return [SourceChapter(source_id="c1", title="1", series_id=series_id)]

    async def pages(self, _capitulo: SourceChapter | str) -> list[SourcePage]:
        raise self.error

    async def page_bytes(self, _pagina: SourcePage | str) -> SourcePageContent:
        raise self.error


@contextmanager
def _cliente(base_de_datos: Database, registro: SourceRegistry) -> Iterator[TestClient]:
    ausente = object()
    registry_anterior = getattr(app.state, "source_registry", ausente)
    dependencia_anterior = app.dependency_overrides.get(get_database, ausente)
    app.state.source_registry = registro
    app.dependency_overrides[get_database] = lambda: base_de_datos
    cliente = TestClient(app)
    try:
        yield cliente
    finally:
        cliente.close()
        if registry_anterior is ausente:
            try:
                delattr(app.state, "source_registry")
            except AttributeError:
                pass
        else:
            app.state.source_registry = registry_anterior
        if dependencia_anterior is ausente:
            app.dependency_overrides.pop(get_database, None)
        else:
            app.dependency_overrides[get_database] = dependencia_anterior


def _base_de_datos(tmp_path: Path) -> Database:
    base_de_datos = Database(tmp_path / "nyanko.sqlite3")
    base_de_datos.initialize()
    return base_de_datos


def _registro_local(raiz: Path) -> SourceRegistry:
    return SourceRegistry(
        [LocalArchiveSource(_Fetcher(), [{"id": "0", "path": str(raiz)}])]
    )


@pytest.fixture
def biblioteca(tmp_path: Path) -> Path:
    raiz = tmp_path / "biblioteca"
    capitulo = raiz / "Serie" / "Cap 1"
    capitulo.mkdir(parents=True)
    for nombre in ("10.jpg", "2.jpg", "1.jpg"):
        (capitulo / nombre).write_bytes(nombre.encode())

    with zipfile.ZipFile(raiz / "Serie" / "Cap 003.cbz", "w") as archivo:
        archivo.writestr("2.jpg", b"dos")
        archivo.writestr("1.jpg", b"uno")
        archivo.writestr(
            "ComicInfo.xml",
            "<ComicInfo><Title>Interludio</Title><Number>12.5</Number></ComicInfo>",
        )
    (raiz / "Serie" / "Cap 004.cbr").write_bytes(b"rar-no-soportado")
    return raiz


def test_un_endpoint_navega_series_y_capitulos_con_comicinfo(tmp_path, biblioteca):
    base_de_datos = _base_de_datos(tmp_path)

    with _cliente(base_de_datos, _registro_local(biblioteca)) as cliente:
        raiz = cliente.get("/api/manga/chapters", params={"series_id": "0:."})
        capitulos = cliente.get(
            "/api/manga/chapters", params={"series_id": "0:Serie"}
        )

    assert raiz.status_code == 200
    assert raiz.json() == [
        {
            "source_id": "0:Serie",
            "title": "Serie",
            "series_id": "0:.",
            "number": None,
            "is_chapter": False,
        }
    ]
    assert capitulos.status_code == 200
    datos = capitulos.json()
    assert next(item for item in datos if item["source_id"].endswith("Cap 1"))[
        "is_chapter"
    ] is True
    comicinfo = next(item for item in datos if item["title"] == "Interludio")
    assert comicinfo["number"] == 12.5
    assert comicinfo["is_chapter"] is True


def test_paginas_salen_en_orden_natural_con_urls_relativas_y_errores_tipados(
    tmp_path, biblioteca
):
    base_de_datos = _base_de_datos(tmp_path)

    with _cliente(base_de_datos, _registro_local(biblioteca)) as cliente:
        paginas = cliente.get(
            "/api/manga/pages", params={"chapter_id": "0:Serie/Cap 1"}
        )
        cbr = cliente.get(
            "/api/manga/pages", params={"chapter_id": "0:Serie/Cap 004.cbr"}
        )
        ausente = cliente.get(
            "/api/manga/pages", params={"chapter_id": "0:Serie/Ausente"}
        )
        fuente_desconocida = cliente.get(
            "/api/manga/pages",
            params={"source": "desconocida", "chapter_id": "0:Serie/Cap 1"},
        )

    assert paginas.status_code == 200
    datos = paginas.json()
    assert [item["filename"] for item in datos] == ["1.jpg", "2.jpg", "10.jpg"]
    assert [item["index"] for item in datos] == [1, 2, 3]
    assert all(item["url"].startswith("/assets/pages/") for item in datos)
    assert all(
        marker not in item["url"]
        for item in datos
        for marker in ("http", "127.0.0.1", ":8765")
    )
    assert cbr.status_code == 415
    assert ausente.status_code == 404
    assert fuente_desconocida.status_code == 404


@pytest.mark.parametrize(
    ("error", "estado"),
    [
        pytest.param(SourceRateLimitError("espera", retry_after=7), 429, id="limite"),
        pytest.param(SourceParseError("respuesta invalida"), 502, id="parseo"),
        pytest.param(SourceNetworkError("sin red"), 503, id="red"),
    ],
)
def test_los_endpoints_de_fuente_no_convierten_errores_tipados_en_500(
    tmp_path, error, estado
):
    base_de_datos = _base_de_datos(tmp_path)
    registro = SourceRegistry([_FuenteConError(error)])

    with _cliente(base_de_datos, registro) as cliente:
        respuesta = cliente.get(
            "/api/manga/pages",
            params={"source": "fuente_con_error", "chapter_id": "capitulo"},
        )

    assert respuesta.status_code == estado


def test_dos_peticiones_sirven_el_cache_cuando_la_fuente_falla(tmp_path):
    """El cache vive entre peticiones: dos GET comparten el mismo SourceEngine."""
    base_de_datos = _base_de_datos(tmp_path)
    fuente = _FuenteConError()
    parametros = {"source": "fuente_con_error", "series_id": "serie"}

    with _cliente(base_de_datos, SourceRegistry([fuente])) as cliente:
        primera = cliente.get("/api/manga/chapters", params=parametros)
        fuente.error = SourceParseError("Cloudflare devolvio HTML")
        segunda = cliente.get("/api/manga/chapters", params=parametros)

    assert primera.status_code == 200
    assert segunda.status_code == 200
    assert segunda.json() == primera.json()


def test_un_429_por_la_api_no_devuelve_cache(tmp_path):
    """Guardian de la costura CR-03 + WR-03: el cache resucitado no puede tragarse un 429."""
    base_de_datos = _base_de_datos(tmp_path)
    fuente = _FuenteConError()
    parametros = {"source": "fuente_con_error", "series_id": "serie"}

    with _cliente(base_de_datos, SourceRegistry([fuente])) as cliente:
        primera = cliente.get("/api/manga/chapters", params=parametros)
        fuente.error = SourceRateLimitError("limitado", retry_after=3)
        segunda = cliente.get("/api/manga/chapters", params=parametros)

    assert primera.status_code == 200
    assert segunda.status_code == 429


def test_preferencias_progreso_y_evento_hacen_round_trip_sin_persistir_urls(tmp_path):
    base_de_datos = _base_de_datos(tmp_path)

    with _cliente(base_de_datos, _registro_local(tmp_path)) as cliente:
        solo = cliente.put(
            "/api/manga/prefs",
            params={"series_id": "0:SoloLeveling"},
            json={"mode": "vertical"},
        )
        berserk_vacio = cliente.get(
            "/api/manga/prefs", params={"series_id": "0:Berserk"}
        )
        cliente.put(
            "/api/manga/prefs",
            params={"series_id": "0:Berserk"},
            json={"double_page": True, "double_page_offset": 1},
        )
        berserk = cliente.put(
            "/api/manga/prefs",
            params={"series_id": "0:Berserk"},
            json={"mode": "ltr"},
        )
        progreso_vacio = cliente.get(
            "/api/manga/progress", params={"chapter_id": "0:Berserk/Cap 12"}
        )
        progreso_guardado = cliente.put(
            "/api/manga/progress",
            params={"chapter_id": "0:Berserk/Cap 12"},
            json={"page": 47},
        )
        progreso = cliente.get(
            "/api/manga/progress", params={"chapter_id": "0:Berserk/Cap 12"}
        )
        evento = cliente.post(
            "/api/manga/reading-events",
            params={
                "series_id": "0:Berserk",
                "chapter_id": "0:Berserk/Cap 12",
            },
            json={"chapter": 12.5},
        )

    assert solo.status_code == 200
    assert solo.json()["mode"] == "vertical"
    assert berserk_vacio.status_code == 200
    assert berserk_vacio.json() is None
    assert berserk.status_code == 200
    assert berserk.json()["mode"] == "ltr"
    assert berserk.json()["double_page"] is True
    assert berserk.json()["double_page_offset"] == 1
    assert progreso_vacio.status_code == 200
    assert progreso_vacio.json() is None
    assert progreso_guardado.status_code == 204
    assert progreso_guardado.content == b""
    assert progreso.status_code == 200
    assert progreso.json()["page"] == 47
    assert evento.status_code == 200

    with base_de_datos.connect() as connection:
        row = connection.execute(
            "SELECT id, chapter FROM reading_events WHERE id = ?",
            (evento.json()["id"],),
        ).fetchone()
        assert row["chapter"] == 12.5
        assert_no_persisted_urls(connection)


def test_alta_y_baja_de_carpeta_refrescan_el_registry_sin_reiniciar(tmp_path):
    base_de_datos = _base_de_datos(tmp_path)
    raiz = tmp_path / "nueva-biblioteca"
    capitulo = raiz / "Cap 1"
    capitulo.mkdir(parents=True)
    (capitulo / "1.jpg").write_bytes(b"pagina")
    registro_vacio = build_source_registry(library_folders=[])

    with _cliente(base_de_datos, registro_vacio) as cliente:
        alta = cliente.post(
            "/api/library/folders",
            json={"path": str(raiz), "recursive": True},
        )
        id_carpeta = alta.json()["id"]
        visible = cliente.get(
            "/api/manga/chapters", params={"series_id": f"{id_carpeta}:."}
        )
        baja = cliente.delete(f"/api/library/folders/{id_carpeta}")
        invisible = cliente.get(
            "/api/manga/chapters", params={"series_id": f"{id_carpeta}:."}
        )

    assert alta.status_code == 200
    assert visible.status_code == 200
    assert visible.json()[0]["title"] == "Cap 1"
    assert visible.json()[0]["is_chapter"] is True
    assert baja.status_code == 204
    assert invisible.status_code == 404
