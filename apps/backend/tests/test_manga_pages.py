from __future__ import annotations

import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient
from starlette.routing import Mount

from nyanko_api.config import Settings
from nyanko_api.main import _page_url, app
from nyanko_api.sources import LocalArchiveSource, SourceRegistry
from nyanko_api.sources.local_archive import ARCHIVE_MEMBER_SEPARATOR

PAGINA_CARPETA = b"pagina-suelta-distinta"
PAGINA_CBZ = b"pagina-cbz-distinta"
SECRETO = b"contenido-que-el-endpoint-jamas-debe-servir"


class _Fetcher:
    async def request(self, _metodo: str, _url: str, **_opciones):
        return None


@contextmanager
def _installed_registry(registry: SourceRegistry):
    ausente = object()
    anterior = getattr(app.state, "source_registry", ausente)
    app.state.source_registry = registry
    try:
        yield
    finally:
        if anterior is ausente:
            try:
                delattr(app.state, "source_registry")
            except AttributeError:
                pass
        else:
            app.state.source_registry = anterior


@contextmanager
def _cliente_local(raiz: Path) -> Iterator[TestClient]:
    registro = SourceRegistry(
        [LocalArchiveSource(_Fetcher(), [{"id": "0", "path": str(raiz)}])]
    )
    with _installed_registry(registro):
        cliente = TestClient(app)
        try:
            yield cliente
        finally:
            cliente.close()


@pytest.fixture
def biblioteca_local(tmp_path: Path) -> tuple[Path, Path, Path]:
    raiz = tmp_path / "biblioteca"
    raiz.mkdir()
    capitulo = raiz / "Cap 1"
    capitulo.mkdir()
    (capitulo / "1.jpg").write_bytes(PAGINA_CARPETA)
    (capitulo / "2.jpg").write_bytes(b"pagina-dos")
    (capitulo / "10.jpg").write_bytes(b"pagina-diez")

    archivo_cbz = raiz / "Cap 2.cbz"
    with zipfile.ZipFile(archivo_cbz, "w") as archivo:
        archivo.writestr("1.jpg", PAGINA_CBZ)
        archivo.writestr("2.jpg", b"pagina-dos-cbz")

    (raiz / "Cap 3.cbr").write_bytes(b"rar-no-soportado")
    secreto = raiz.parent / "secreto.txt"
    secreto.write_bytes(SECRETO)
    return raiz, archivo_cbz, secreto


def test_la_ruta_de_paginas_esta_antes_del_mount_de_assets():
    rutas = app.router.routes
    indice_pagina = next(
        indice
        for indice, ruta in enumerate(rutas)
        if getattr(ruta, "path", None) == "/assets/pages/{page_id:path}"
    )
    indice_mount = next(
        indice
        for indice, ruta in enumerate(rutas)
        if isinstance(ruta, Mount) and ruta.path == "/assets"
    )

    assert indice_pagina < indice_mount


def test_sirve_una_pagina_suelta_con_sus_bytes_exactos(biblioteca_local):
    raiz, _archivo_cbz, _secreto = biblioteca_local

    with _cliente_local(raiz) as cliente:
        respuesta = cliente.get(_page_url("0:Cap 1/1.jpg"))

    assert respuesta.status_code == 200
    assert respuesta.headers["content-type"] == "image/jpeg"
    assert respuesta.headers["cache-control"] == "private, max-age=3600"
    assert respuesta.content == PAGINA_CARPETA


def test_transmite_un_miembro_cbz_y_cierra_el_archivo(biblioteca_local):
    raiz, archivo_cbz, _secreto = biblioteca_local
    pagina = f"0:Cap 2.cbz{ARCHIVE_MEMBER_SEPARATOR}1.jpg"

    with _cliente_local(raiz) as cliente:
        respuesta = cliente.get(_page_url(pagina))

    assert respuesta.status_code == 200
    assert respuesta.headers["content-type"] == "image/jpeg"
    assert respuesta.headers["cache-control"] == "private, max-age=3600"
    assert respuesta.content == PAGINA_CBZ

    movido = archivo_cbz.with_suffix(".movido")
    archivo_cbz.replace(movido)
    movido.replace(archivo_cbz)


@pytest.mark.parametrize(
    "ruta",
    [
        _page_url("0:../secreto.txt"),
        _page_url("0:../../etc/passwd"),
        "/assets/pages/0:%2E%2E%2F%2E%2E%2Fetc%2Fpasswd",
        _page_url("C:/Windows/win.ini"),
        _page_url("/etc/passwd"),
        _page_url("raiz-no-registrada:x.jpg"),
        _page_url("0:Cap 2.cbz!../../../secreto.txt"),
        _page_url("0:Cap 2.cbz!miembro-que-no-existe.jpg"),
    ],
)
def test_el_endpoint_rechaza_traversal_sin_filtrar_rutas(ruta, biblioteca_local):
    raiz, _archivo_cbz, secreto = biblioteca_local

    with _cliente_local(raiz) as cliente:
        respuesta = cliente.get(ruta)

    assert respuesta.status_code == 404
    assert SECRETO not in respuesta.content
    detalle = respuesta.json()["detail"]
    assert str(raiz) not in detalle
    assert str(secreto) not in detalle


def test_los_errores_de_pagina_son_tipados_y_no_exponen_paths(biblioteca_local):
    raiz, _archivo_cbz, secreto = biblioteca_local
    pagina_cbr = f"0:Cap 3.cbr{ARCHIVE_MEMBER_SEPARATOR}1.jpg"

    with _cliente_local(raiz) as cliente:
        cbr = cliente.get(_page_url(pagina_cbr))
        ausente = cliente.get(_page_url("0:Cap 1/no-existe.jpg"))
        fuente_desconocida = cliente.get(
            _page_url("0:Cap 1/1.jpg"),
            params={"source": "no_registrada"},
        )

    assert cbr.status_code == 415
    assert "CBZ" in cbr.json()["detail"]
    assert ausente.status_code == 404
    assert fuente_desconocida.status_code == 404
    for respuesta in (cbr, ausente, fuente_desconocida):
        detalle = respuesta.json()["detail"]
        assert str(raiz) not in detalle
        assert str(secreto) not in detalle


def test_la_url_de_pagina_es_relativa_y_codifica_el_id_opaco():
    url = _page_url("raiz:Serie/Capitulo/pagina.jpg")

    assert url == "/assets/pages/raiz%3ASerie%2FCapitulo%2Fpagina.jpg"
    assert url.startswith("/assets/pages/")
    assert "http" not in url
    assert "127.0.0.1" not in url
    assert ":8765" not in url


def test_el_mount_de_assets_sigue_sirviendo_ficheros(tmp_path, monkeypatch):
    mount = next(
        ruta
        for ruta in app.router.routes
        if isinstance(ruta, Mount) and ruta.path == "/assets"
    )
    static_files = mount.app
    assert isinstance(static_files, StaticFiles)
    ajustes = Settings(data_dir=tmp_path)
    ajustes.assets_dir.mkdir()
    monkeypatch.setattr(static_files, "directory", str(ajustes.assets_dir))
    monkeypatch.setattr(static_files, "all_directories", [str(ajustes.assets_dir)])

    contenido = b"asset-estatico"
    (ajustes.assets_dir / "otra-cosa.png").write_bytes(contenido)
    cliente = TestClient(app)
    try:
        respuesta = cliente.get("/assets/otra-cosa.png")
    finally:
        cliente.close()

    assert respuesta.status_code == 200
    assert respuesta.content == contenido
