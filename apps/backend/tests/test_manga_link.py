from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from nyanko_api.database import Database
from nyanko_api.linking import UnlinkedSeriesError, require_link
from nyanko_api.main import app, get_database
from nyanko_api.models import MediaItem
from nyanko_api.sources import LocalArchiveSource, SourceRegistry


def _database(tmp_path: Path, *, flat: bool = False) -> tuple[Database, SourceRegistry]:
    database = Database(tmp_path / "nyanko.sqlite3")
    database.initialize()

    root = tmp_path / ("Berserk" if flat else "manga")
    series = root if flat else root / "Berserk"
    chapter = series / "Cap 12"
    chapter.mkdir(parents=True)
    (chapter / "1.jpg").write_bytes(b"pagina")
    (series / "Cap 13.cbz").write_bytes(b"archivo")
    with database.connect() as connection:
        connection.execute(
            "INSERT INTO library_folders(id, path, recursive, kind) VALUES (0, ?, 1, 'manga')",
            (str(root),),
        )

    registry = SourceRegistry([LocalArchiveSource(library_folders=database.get_library_folders())])
    return database, registry


def _sembrar_media(
    database: Database,
    title: str,
    external_id: int,
    *,
    media_type: str = "MANGA",
) -> int:
    # Reserva el 41 para que el primer id canónico sea 42 y sea distinto del externo.
    with database.connect() as connection:
        connection.execute("INSERT OR IGNORE INTO media(id, media_type) VALUES (41, 'ANIME')")
    item = MediaItem(
        id=external_id,
        title=title,
        status="CURRENT",
        progress=11,
        episodes=24 if media_type == "ANIME" else None,
        chapters=364 if media_type == "MANGA" else None,
        media_type=media_type,
    )
    mapping = database.sync_provider_library(
        "anilist",
        "AniList",
        [item],
        media_type=media_type,
    )
    return mapping[str(external_id)]


@contextmanager
def _client(
    database: Database,
    registry: SourceRegistry,
    *,
    raise_server_exceptions: bool = True,
) -> Iterator[TestClient]:
    absent = object()
    previous_registry = getattr(app.state, "source_registry", absent)
    previous_engine = getattr(app.state, "source_engine", absent)
    previous_dependency = app.dependency_overrides.get(get_database, absent)
    app.state.source_registry = registry
    if previous_engine is not absent:
        delattr(app.state, "source_engine")
    app.dependency_overrides[get_database] = lambda: database
    client = TestClient(app, raise_server_exceptions=raise_server_exceptions)
    try:
        yield client
    finally:
        client.close()
        if previous_registry is absent:
            delattr(app.state, "source_registry")
        else:
            app.state.source_registry = previous_registry
        if previous_engine is absent:
            if hasattr(app.state, "source_engine"):
                delattr(app.state, "source_engine")
        else:
            app.state.source_engine = previous_engine
        if previous_dependency is absent:
            app.dependency_overrides.pop(get_database, None)
        else:
            app.dependency_overrides[get_database] = previous_dependency


def _count(database: Database, table: str) -> int:
    with database.connect() as connection:
        return connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def test_match_propone_con_score_sin_persistir_ni_duplicar_sugerencias(tmp_path):
    database, registry = _database(tmp_path)
    canonical_id = _sembrar_media(database, "Berserk", 105398)
    for index in range(1, 7):
        _sembrar_media(database, f"Berserk {index}", 105398 + index)

    with _client(database, registry) as client:
        response = client.post("/api/manga/link/match", params={"series_id": "0:Berserk"})

    assert response.status_code == 200
    data = response.json()
    assert canonical_id == 42
    assert data["series_title"] == "Berserk"
    assert data["match"]["id"] == 42
    assert data["match"]["title"] == "Berserk"
    assert data["match_score"] >= 0.99
    assert len(data["suggestions"]) <= 5
    assert 42 not in {item["id"] for item in data["suggestions"]}
    # Un score perfecto sigue siendo una propuesta: solo el PUT puede crear la fila.
    assert _count(database, "media_mappings") == 0


def test_match_vacio_y_una_entrada_de_anime_no_proponen_manga(tmp_path):
    database, registry = _database(tmp_path)

    with _client(database, registry) as client:
        empty = client.post("/api/manga/link/match", params={"series_id": "0:Berserk"})
        _sembrar_media(database, "Berserk", 999, media_type="ANIME")
        only_anime = client.post("/api/manga/link/match", params={"series_id": "0:Berserk"})

    for response in (empty, only_anime):
        assert response.status_code == 200
        assert response.json()["match"] is None
        assert response.json()["match_score"] == 0.0
        assert response.json()["suggestions"] == []
    assert _count(database, "media_mappings") == 0


def test_un_vinculo_confirmado_manda_sobre_el_matcher(tmp_path):
    database, registry = _database(tmp_path)
    _sembrar_media(database, "Berserk equivocado", 105398)
    database.set_media_mapping(
        "local_archive", "0:Berserk", 42, chapter_offset=100, manga_link=True
    )

    with _client(database, registry) as client:
        response = client.post("/api/manga/link/match", params={"series_id": "0:Berserk"})

    assert response.status_code == 200
    assert response.json()["link"] == {
        "media_id": 42,
        "chapter_offset": 100,
        "title": "Berserk equivocado",
    }
    assert response.json()["match_score"] == 1.0


def test_match_admite_biblioteca_plana_y_rechaza_una_raiz_inventada(tmp_path):
    database, registry = _database(tmp_path, flat=True)
    _sembrar_media(database, "Berserk", 105398)

    with _client(database, registry) as client:
        flat = client.post("/api/manga/link/match", params={"series_id": "0:."})
        invented = client.post("/api/manga/link/match", params={"series_id": "99:Loquesea"})

    assert flat.status_code == 200
    assert flat.json()["series_title"] == "Berserk"
    assert flat.json()["match"]["title"] == "Berserk"
    assert invented.status_code == 400


def test_confirmar_guarda_el_id_canonico_revincula_y_desvincula(tmp_path):
    database, registry = _database(tmp_path)
    canonical_id = _sembrar_media(database, "Berserk", 105398)
    other_id = _sembrar_media(database, "Berserk Deluxe", 105399)

    with _client(database, registry) as client:
        missing = client.get("/api/manga/link", params={"series_id": "0:Berserk"})
        confirmed = client.put(
            "/api/manga/link",
            params={"series_id": "0:Berserk"},
            json={"media_id": canonical_id, "chapter_offset": 100},
        )
        repeated = client.put(
            "/api/manga/link",
            params={"series_id": "0:Berserk"},
            json={"media_id": canonical_id, "chapter_offset": 100},
        )
        rows_after_repeat = _count(database, "media_mappings")
        with database.connect() as connection:
            stored_media_id = connection.execute("SELECT media_id FROM media_mappings").fetchone()[
                0
            ]
        current = client.get("/api/manga/link", params={"series_id": "0:Berserk"})
        relinked = client.put(
            "/api/manga/link",
            params={"series_id": "0:Berserk"},
            json={"media_id": other_id},
        )
        rows_after_relink = _count(database, "media_mappings")
        deleted = client.delete("/api/manga/link", params={"series_id": "0:Berserk"})
        deleted_again = client.delete("/api/manga/link", params={"series_id": "0:Berserk"})

    assert missing.status_code == 200
    assert missing.json() is None
    assert canonical_id == 42
    assert confirmed.status_code == 200
    assert repeated.status_code == 200
    assert rows_after_repeat == 1
    assert stored_media_id == 42
    assert current.json() == {
        "media_id": 42,
        "chapter_offset": 100,
        "title": "Berserk",
    }
    assert database.external_id_for_account(42, "anilist") == "105398"
    assert relinked.json()["media_id"] == other_id
    assert rows_after_relink == 1
    assert deleted.status_code == 204
    assert deleted_again.status_code == 204
    assert _count(database, "media_mappings") == 0
    with pytest.raises(UnlinkedSeriesError):
        require_link(database, "local_archive", "0:Berserk")


def test_confirmar_rechaza_ids_externos_ausentes_y_de_anime(tmp_path):
    database, registry = _database(tmp_path)
    _sembrar_media(database, "Berserk", 105398)
    anime_id = _sembrar_media(database, "Berserk", 999, media_type="ANIME")

    with _client(database, registry) as client:
        external = client.put(
            "/api/manga/link",
            params={"series_id": "0:Berserk"},
            json={"media_id": 105398},
        )
        absent = client.put(
            "/api/manga/link",
            params={"series_id": "0:Berserk"},
            json={"media_id": 999999},
        )
        anime = client.put(
            "/api/manga/link",
            params={"series_id": "0:Berserk"},
            json={"media_id": anime_id},
        )

    assert external.status_code == 422
    assert absent.status_code == 422
    assert anime.status_code == 422
    assert _count(database, "media_mappings") == 0


def test_confirmar_valida_serie_capitulo_y_fuente_antes_de_escribir(tmp_path):
    database, registry = _database(tmp_path)
    canonical_id = _sembrar_media(database, "Berserk", 105398)

    with _client(database, registry) as client:
        absent = client.put(
            "/api/manga/link",
            params={"series_id": "0:NoExiste"},
            json={"media_id": canonical_id},
        )
        chapter = client.put(
            "/api/manga/link",
            params={"series_id": "0:Berserk/Cap 13.cbz"},
            json={"media_id": canonical_id},
        )
        wrong_source = client.put(
            "/api/manga/link",
            params={"source": "crunchyroll", "series_id": "0:Berserk"},
            json={"media_id": canonical_id},
        )

    assert absent.status_code == 404
    assert chapter.status_code == 404
    assert wrong_source.status_code == 404
    assert _count(database, "media_mappings") == 0


def test_confirmar_admite_biblioteca_plana_y_acota_el_offset(tmp_path):
    database, registry = _database(tmp_path, flat=True)
    canonical_id = _sembrar_media(database, "Berserk", 105398)

    with _client(database, registry) as client:
        invalid = client.put(
            "/api/manga/link",
            params={"series_id": "0:."},
            json={"media_id": canonical_id, "chapter_offset": 100000},
        )
        valid = client.put(
            "/api/manga/link",
            params={"series_id": "0:."},
            json={"media_id": canonical_id},
        )

    assert invalid.status_code == 422
    assert valid.status_code == 200
    assert require_link(database, "local_archive", "0:.").media_id == canonical_id


def test_una_correccion_de_playback_no_reapunta_un_vinculo_de_manga(tmp_path):
    database, registry = _database(tmp_path)
    canonical_id = _sembrar_media(database, "Berserk", 105398)

    with _client(database, registry, raise_server_exceptions=False) as client:
        confirmed = client.put(
            "/api/manga/link",
            params={"series_id": "0:Berserk"},
            json={"media_id": canonical_id, "chapter_offset": 100},
        )
        correction = client.post(
            "/api/playback/correction",
            json={
                "raw_title": "berserk",
                "media_id": 999,
                "site_identifier": "0:Berserk",
                "site_adapter": "local_archive",
            },
        )

    assert confirmed.status_code == 200
    # Sin el guarda de 04-02, playback reapunta el vínculo y borra el offset; la Fase 5
    # terminaría escribiendo en otra serie real, con reintento duradero y sin deshacer.
    assert correction.status_code == 500
    link = require_link(database, "local_archive", "0:Berserk")
    assert (link.media_id, link.chapter_offset) == (42, 100)
    with database.connect() as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM media_mappings WHERE provider = 'local_archive'"
            ).fetchone()[0]
            == 1
        )


def test_un_mapping_de_anime_no_se_lee_como_vinculo_de_manga(tmp_path):
    database, registry = _database(tmp_path)
    database.set_media_mapping("crunchyroll", "abc", 777, 3)

    with _client(database, registry, raise_server_exceptions=False) as client:
        reading = client.post(
            "/api/manga/reading-events",
            params={
                "source": "crunchyroll",
                "series_id": "abc",
                "chapter_id": "abc/1",
            },
            json={"chapter": 1},
        )
        link = client.get(
            "/api/manga/link",
            params={"source": "crunchyroll", "series_id": "abc"},
        )

    # Sin el guarda de lectura, 777 (id externo) saldría como canónico y linked=true
    # aunque el usuario nunca hubiera confirmado un vínculo de manga.
    assert reading.status_code == 500
    assert link.status_code == 500
    assert database.get_media_mapping("crunchyroll", "abc") == (777, 3)


def test_un_delete_de_manga_no_borra_un_mapping_de_anime(tmp_path):
    database, registry = _database(tmp_path)
    database.set_media_mapping("crunchyroll", "abc", 777, 3)

    with _client(database, registry, raise_server_exceptions=False) as client:
        response = client.delete(
            "/api/manga/link",
            params={"source": "crunchyroll", "series_id": "abc"},
        )

    # Sin el guarda de borrado, este endpoint elimina el mapping con el que la extensión
    # trackea anime y el usuario solo lo descubre cuando Crunchyroll deja de sincronizar.
    assert response.status_code == 500
    assert database.get_media_mapping("crunchyroll", "abc") == (777, 3)


def test_un_evento_sin_vinculo_se_registra_y_no_encola(tmp_path):
    database, registry = _database(tmp_path)

    with _client(database, registry) as client:
        response = client.post(
            "/api/manga/reading-events",
            params={
                "series_id": "0:Berserk",
                "chapter_id": "0:Berserk/Cap 12",
            },
            json={"chapter": 12},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["id"] > 0
    assert data["linked"] is False
    assert data["media_id"] is None
    assert "vinculada" in data["reason"].lower()
    with database.connect() as connection:
        event = connection.execute(
            "SELECT media_id FROM reading_events WHERE id = ?", (data["id"],)
        ).fetchone()
        assert event["media_id"] is None
        # TRIPWIRE: hoy pasa gratis porque este camino no encola. Debe ponerse rojo si la
        # Fase 5 añade enqueue_mutation aquí sin cruzar antes require_link.
        assert connection.execute("SELECT COUNT(*) FROM pending_mutations").fetchone()[0] == 0


def test_un_evento_confirmado_guarda_el_media_id_canonico(tmp_path):
    database, registry = _database(tmp_path)
    canonical_id = _sembrar_media(database, "Berserk", 105398)

    with _client(database, registry) as client:
        confirmed = client.put(
            "/api/manga/link",
            params={"series_id": "0:Berserk"},
            json={"media_id": canonical_id},
        )
        response = client.post(
            "/api/manga/reading-events",
            params={
                "series_id": "0:Berserk",
                "chapter_id": "0:Berserk/Cap 12",
            },
            json={"chapter": 12},
        )

    assert confirmed.status_code == 200
    assert response.status_code == 200
    assert response.json()["linked"] is True
    assert response.json()["media_id"] == 42
    assert response.json()["reason"] is None
    with database.connect() as connection:
        assert (
            connection.execute(
                "SELECT media_id FROM reading_events ORDER BY id DESC LIMIT 1"
            ).fetchone()[0]
            == 42
        )


def test_una_propuesta_alta_no_encola_nada_sin_confirmacion(tmp_path):
    database, registry = _database(tmp_path)
    _sembrar_media(database, "Berserk: The Prototype", 105398)

    with _client(database, registry) as client:
        proposal = client.post("/api/manga/link/match", params={"series_id": "0:Berserk"})
        reading = client.post(
            "/api/manga/reading-events",
            params={
                "series_id": "0:Berserk",
                "chapter_id": "0:Berserk/Cap 12",
            },
            json={"chapter": 12},
        )

    assert proposal.status_code == 200
    assert proposal.json()["match_score"] >= 0.85
    assert reading.status_code == 200
    assert reading.json()["linked"] is False
    assert _count(database, "media_mappings") == 0
    assert _count(database, "pending_mutations") == 0
