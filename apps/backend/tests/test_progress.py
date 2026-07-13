"""Tabla de casos del modelo de progreso (docs/specs/progress-model.md).

Lo que se prueba aquí es lo que impide que el botón de deshacer ponga a cero el AniList
real del usuario, y que la guarda monotónica empuje un valor inferior encima de su
progreso de verdad. Los casos van primero; el módulo, después.
"""
import sqlite3
from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from nyanko_api.database import Database
from nyanko_api.main import app, get_database
from nyanko_api.models import FuzzyDate, MediaDetails, MediaItem, MediaListEntry
from nyanko_api.progress import effective_chapter, is_reread, next_progress, to_provider
from nyanko_api.providers import ProviderCapabilities


# --- El módulo puro ---


@pytest.mark.parametrize(
    ("chapter", "expected"),
    [(10.5, 10), (10.0, 10), (1, 1)],
)
def test_to_provider_floors_to_the_int_the_provider_accepts(chapter, expected):
    result = to_provider(chapter)
    assert result == expected
    assert isinstance(result, int)


@pytest.mark.parametrize(
    ("chapter", "tracker_progress", "tracker_status", "expected"),
    [
        # Sube: el capítulo cruza al proveedor floored.
        (10.5, 9, "CURRENT", 10),
        (11.0, 10, "CURRENT", 11),
        # Nada que subir: el floor ya es lo que el tracker tiene. Reenviarlo es ruido.
        (10.5, 10, "CURRENT", None),
        (0.5, 0, "CURRENT", None),
        # Regresión: la guarda monotónica muerde. Esto es lo que salva el progreso real.
        (9.0, 12, "CURRENT", None),
        # Sin valor del tracker: FALLA CERRADO. No se escribe a ciegas en la lista real.
        (10.5, None, "CURRENT", None),
        # Relectura de una serie terminada: no se empuja un 1 encima de un 24.
        (1.0, 24, "COMPLETED", None),
    ],
)
def test_next_progress_case_table(chapter, tracker_progress, tracker_status, expected):
    assert next_progress(chapter, tracker_progress, tracker_status) == expected


def test_next_progress_fails_closed_without_a_tracker_value():
    # Explícito aparte de la tabla: es la garantía de seguridad del módulo.
    assert next_progress(10.5, None, "CURRENT") is None


def test_is_reread_signals_a_completed_series_being_read_again():
    assert is_reread(1.0, 24, "COMPLETED") is True
    assert is_reread(1.0, 24, "CURRENT") is False
    # Sin tracker no se afirma nada: desconocido no es relectura.
    assert is_reread(1.0, None, "COMPLETED") is False


@pytest.mark.parametrize(
    ("progress", "chapter_progress", "expected"),
    [
        # Cuadran: el decimal es bueno.
        (10, 10.5, 10.5),
        # El tracker se movió por debajo (sync de database.py:2639): chapter_progress es basura.
        (12, 10.5, 12.0),
        # Anime, o manga que nunca pasó por el reader.
        (10, None, 10.0),
    ],
)
def test_effective_chapter_reconciles_the_pair_at_read_time(progress, chapter_progress, expected):
    assert effective_chapter(progress, chapter_progress) == expected


# --- progress_before en los TRES endpoints que graban progress_after ---

TRACKER_PROGRESS = 7  # lo que el proveedor tiene: lo que el undo debe restaurar
LOCAL_PROGRESS = 3  # lo que la UI movió en local: leerlo sería el bug
NEW_PROGRESS = 11
EXTERNAL_ID = 10


class _FakeProvider:
    name = "anilist"
    display_name = "AniList"
    capabilities = ProviderCapabilities(manga=True)

    async def edit_entry(self, credential, external_id, update, media_type="ANIME"):
        return MediaListEntry(
            id=1,
            status=update.status or "CURRENT",
            score=0.0,
            progress=update.progress or 0,
            repeat=0,
            private=False,
            started_at=FuzzyDate(),
            completed_at=FuzzyDate(),
        )

    async def details(self, credential, external_id):
        return MediaDetails(
            id=external_id,
            title="Frieren",
            synonyms=[],
            site_url="https://anilist.co/anime/10",
            status="FINISHED",
            episodes=28,
            genres=[],
            studios=[],
            score_format="POINT_100",
        )


@pytest.fixture
def database(monkeypatch) -> Database:
    database = Database(Path(":memory:"))
    connection = sqlite3.connect(":memory:", check_same_thread=False)
    connection.row_factory = sqlite3.Row

    @contextmanager
    def connect():
        yield connection
        connection.commit()

    monkeypatch.setattr(database, "connect", connect)
    database.initialize()
    return database


@pytest.fixture
def seeded(database, monkeypatch):
    """Tracker=7, local=3. DISTINTOS y ninguno 0: un progress_before de 0 o de 3 falla."""
    monkeypatch.setattr("nyanko_api.main._get_provider", lambda settings, provider: _FakeProvider())
    monkeypatch.setattr("nyanko_api.main.get_provider_credential", lambda provider, alias: "token")
    monkeypatch.setattr("nyanko_api.main.TorrentChecker.start", lambda self: None)

    database.sync_provider_library(
        "anilist",
        "AniList",
        [MediaItem(id=EXTERNAL_ID, title="Frieren", status="CURRENT", progress=TRACKER_PROGRESS, episodes=28)],
    )
    canonical = database.canonical_media_id("anilist", EXTERNAL_ID)
    with database.connect() as connection:
        connection.execute(
            "UPDATE library_entries SET progress = ? WHERE media_id = ?",
            (LOCAL_PROGRESS, canonical),
        )

    app.dependency_overrides[get_database] = lambda: database
    with TestClient(app) as client:
        yield client, database, canonical
    app.dependency_overrides.pop(get_database, None)


def _last_event(database: Database) -> sqlite3.Row:
    with database.connect() as connection:
        return connection.execute(
            "SELECT progress_before, progress_after FROM playback_events ORDER BY id DESC LIMIT 1"
        ).fetchone()


def _call_update_progress(client, canonical):
    return client.post(
        "/api/library/progress",
        json={"media_id": EXTERNAL_ID, "progress": NEW_PROGRESS},
    )


def _call_edit_media_entry(client, canonical):
    return client.put(
        f"/api/media/{EXTERNAL_ID}/entry",
        json={"progress": NEW_PROGRESS},
    )


def _call_bulk_update(client, canonical):
    return client.post(
        f"/api/library/bulk-update?media_id={canonical}",
        json={"progress": NEW_PROGRESS},
    )


@pytest.mark.parametrize(
    "call",
    [_call_update_progress, _call_edit_media_entry, _call_bulk_update],
    ids=["POST /api/library/progress", "PUT /api/media/{id}/entry", "POST /api/library/bulk-update"],
)
def test_progress_before_records_the_tracker_value_not_the_local_one(seeded, call):
    client, database, canonical = seeded

    response = call(client, canonical)
    assert response.status_code == 200, response.text

    event = _last_event(database)
    assert event is not None, "el endpoint no grabó ningún playback_event"

    # `undo_playback` (main.py:3792) ESCRIBE progress_before de vuelta en el proveedor.
    # Un 0 de relleno pondría a cero el AniList real; el valor local (3) lo retrocedería
    # tres capítulos; y progress_after (11) sale de leer el tracker DESPUÉS de que
    # update_remote_library_entry sobrescriba el espejo — un undo que no deshace nada.
    assert event["progress_before"] == TRACKER_PROGRESS, (
        f"progress_before={event['progress_before']!r}: se esperaba el valor DEL TRACKER "
        f"({TRACKER_PROGRESS}), no el local ({LOCAL_PROGRESS}), ni 0, ni progress_after"
    )
    assert event["progress_after"] == NEW_PROGRESS
    assert event["progress_before"] != event["progress_after"]
