import sqlite3
from pathlib import Path

import pytest

from nyanko_api.database import Database
from tests.test_persisted_urls import assert_no_persisted_urls


READER_TABLES = ("reader_prefs", "reader_progress", "reading_events")


def _database(tmp_path: Path) -> Database:
    database = Database(tmp_path / "nyanko.sqlite3")
    database.initialize()
    return database


def _row_counts(connection: sqlite3.Connection) -> dict[str, int]:
    tables = [
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
        if row[0] not in {"schema_migrations", *READER_TABLES}
    ]
    return {
        table: connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
        for table in tables
    }


def _degrade_to_v8(path: Path) -> None:
    """Quita solo las tablas v9 para reproducir una BD v8 con el esquema real."""
    with sqlite3.connect(path) as connection:
        for table in READER_TABLES:
            connection.execute(f'DROP TABLE "{table}"')
        connection.execute("DELETE FROM schema_migrations")
        connection.execute("INSERT INTO schema_migrations(version) VALUES (8)")


def test_esquema_v9_declara_tipos_defaults_y_claves_compuestas(tmp_path):
    database = _database(tmp_path)

    with database.connect() as connection:
        prefs = {
            row["name"]: row
            for row in connection.execute("PRAGMA table_info(reader_prefs)").fetchall()
        }
        progress = connection.execute("PRAGMA table_info(reader_progress)").fetchall()
        events = {
            row["name"]: row["type"]
            for row in connection.execute("PRAGMA table_info(reading_events)").fetchall()
        }
        playback = {
            row["name"] for row in connection.execute("PRAGMA table_info(playback_events)")
        }

        assert prefs["mode"]["dflt_value"] == "'rtl'"
        assert all("zoom" not in column and "pan" not in column for column in prefs)
        assert [row["name"] for row in prefs.values() if row["pk"]] == [
            "source_name",
            "series_id",
        ]
        assert [row["name"] for row in progress if row["pk"]] == [
            "source_name",
            "chapter_id",
        ]
        assert events["chapter"] == "REAL"
        assert events["progress_before"] == "REAL"
        assert events["progress_after"] == "REAL"
        assert "chapter" not in playback
        assert_no_persisted_urls(connection)


def test_preferencias_se_aislan_por_serie_y_conservan_actualizaciones_parciales(tmp_path):
    database = _database(tmp_path)

    assert database.get_reader_prefs("local_archive", "0:Inexistente") is None
    database.set_reader_prefs(
        "local_archive",
        "0:Berserk",
        mode="rtl",
        double_page=1,
        double_page_offset=1,
    )
    database.set_reader_prefs("local_archive", "0:Berserk", mode="ltr")
    database.set_reader_prefs("local_archive", "0:SoloLeveling", mode="vertical")
    database.set_reader_prefs("local_archive", "0:Default", fit="width")

    berserk = database.get_reader_prefs("local_archive", "0:Berserk")
    solo_leveling = database.get_reader_prefs("local_archive", "0:SoloLeveling")
    defaults = database.get_reader_prefs("local_archive", "0:Default")
    assert berserk == {
        "mode": "ltr",
        "fit": None,
        "double_page": 1,
        "double_page_offset": 1,
    }
    assert solo_leveling["mode"] == "vertical"
    assert defaults["mode"] == "rtl"

    with database.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM reader_prefs").fetchone()[0] == 3
        assert_no_persisted_urls(connection)


def test_progreso_se_aisla_por_capitulo_y_actualiza_sin_duplicar(tmp_path):
    database = _database(tmp_path)
    chapter_id = "0:Berserk/Cap 12"

    assert database.get_reader_progress("local_archive", chapter_id) is None
    database.set_reader_progress("local_archive", chapter_id, 47)
    database.set_reader_progress("local_archive", chapter_id, 47)
    database.set_reader_progress("local_archive", "0:Berserk/Cap 13", 3)

    assert database.get_reader_progress("local_archive", chapter_id)["page"] == 47
    assert database.get_reader_progress("local_archive", "0:Berserk/Cap 13")["page"] == 3

    with database.connect() as connection:
        rows = connection.execute(
            "SELECT chapter_id FROM reader_progress ORDER BY chapter_id"
        ).fetchall()
        assert len(rows) == 2
        assert all(not Path(row["chapter_id"]).is_absolute() for row in rows)
        assert all(str(tmp_path) not in row["chapter_id"] for row in rows)
        assert_no_persisted_urls(connection)


def test_evento_de_lectura_conserva_el_capitulo_decimal_y_media_id_nulo(tmp_path):
    database = _database(tmp_path)

    event_id = database.insert_reading_event(
        "local_archive",
        "0:Berserk",
        "0:Berserk/Cap 12",
        12.5,
        media_id=None,
        progress_before=12.0,
        progress_after=12.5,
    )

    events = database.get_recent_reading_events()
    assert len(events) == 1
    assert events[0]["id"] == event_id
    assert events[0]["chapter"] == 12.5
    assert events[0]["media_id"] is None
    assert events[0]["status"] == "pending"

    with database.connect() as connection:
        assert_no_persisted_urls(connection)


def test_migracion_v8_a_v9_es_aditiva_con_backup_y_recuentos_estables(tmp_path):
    path = tmp_path / "nyanko.sqlite3"
    Database(path).initialize()
    _degrade_to_v8(path)

    with sqlite3.connect(path) as connection:
        connection.execute("INSERT INTO media(id, media_type) VALUES (901, 'MANGA')")
        connection.execute(
            "INSERT INTO library_entries(media_id, status, progress, chapter_progress) "
            "VALUES (901, 'CURRENT', 12, 12.5)"
        )
        counts_before = _row_counts(connection)

    Database(path).initialize()

    with sqlite3.connect(path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert set(READER_TABLES) <= tables
        assert _row_counts(connection) == counts_before
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] == 9
        assert_no_persisted_urls(connection)

    backups = list(tmp_path.glob("nyanko.backup-v9-*.sqlite3"))
    assert len(backups) == 1
    with sqlite3.connect(backups[0]) as backup:
        backup_tables = {
            row[0]
            for row in backup.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        assert not set(READER_TABLES) & backup_tables
        assert _row_counts(backup) == counts_before
        assert backup.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] == 8


def test_guardia_rechaza_url_absoluta_en_una_tabla_nueva(tmp_path):
    database = _database(tmp_path)
    database.set_reader_progress(
        "local_archive",
        "http://127.0.0.1:49876/assets/pages/x.jpg",
        1,
    )

    with database.connect() as connection:
        with pytest.raises(AssertionError, match="reader_progress"):
            assert_no_persisted_urls(connection)
