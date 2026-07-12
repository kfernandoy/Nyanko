import json
import sqlite3
import time
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass
from pathlib import Path

from .normalizer import normalize_title
from .models import MediaDetails, MediaStatistics, StatisticGroup, StatisticsResponse


SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS playback_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    detected_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    source TEXT NOT NULL,
    raw_title TEXT NOT NULL,
    anime_title TEXT,
    episode INTEGER,
    status TEXT NOT NULL DEFAULT 'pending',
    media_id INTEGER,
    progress_before INTEGER,
    progress_after INTEGER
);
CREATE TABLE IF NOT EXISTS match_corrections (
    raw_pattern TEXT PRIMARY KEY,
    media_id INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS media_mappings (
    provider TEXT NOT NULL,
    site_identifier TEXT NOT NULL,
    media_id INTEGER NOT NULL,
    episode_offset INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(provider, site_identifier)
);
CREATE TABLE IF NOT EXISTS cache (
    key TEXT PRIMARY KEY,
    payload TEXT NOT NULL,
    expires_at INTEGER NOT NULL,
    created_at INTEGER NOT NULL DEFAULT 0,
    updated_at INTEGER NOT NULL DEFAULT 0,
    accessed_at INTEGER NOT NULL DEFAULT 0,
    provider_id TEXT,
    account_alias TEXT,
    resource TEXT,
    refresh_reason TEXT
);
CREATE TABLE IF NOT EXISTS providers (
    id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider_id TEXT NOT NULL REFERENCES providers(id),
    alias TEXT NOT NULL DEFAULT 'default',
    external_user_id TEXT,
    credential_ref TEXT,
    is_primary INTEGER NOT NULL DEFAULT 0,
    last_synced_at TEXT,
    UNIQUE(provider_id, alias)
);
CREATE TABLE IF NOT EXISTS media (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    media_type TEXT NOT NULL DEFAULT 'ANIME',
    format TEXT,
    episode_count INTEGER,
    chapter_count INTEGER,
    volume_count INTEGER,
    release_year INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS media_titles (
    media_id INTEGER NOT NULL REFERENCES media(id) ON DELETE CASCADE,
    language TEXT NOT NULL,
    title TEXT NOT NULL,
    normalized_title TEXT,
    is_primary INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY(media_id, language, title)
);
CREATE TABLE IF NOT EXISTS media_genres (
    media_id INTEGER NOT NULL REFERENCES media(id) ON DELETE CASCADE,
    genre TEXT NOT NULL,
    PRIMARY KEY(media_id, genre)
);
CREATE TABLE IF NOT EXISTS media_tags (
    media_id INTEGER NOT NULL REFERENCES media(id) ON DELETE CASCADE,
    tag TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(media_id, tag)
);
CREATE TABLE IF NOT EXISTS media_seasons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    media_id INTEGER NOT NULL REFERENCES media(id) ON DELETE CASCADE,
    season_number INTEGER,
    label TEXT,
    year INTEGER,
    UNIQUE(media_id, season_number)
);
CREATE TABLE IF NOT EXISTS episodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    media_id INTEGER NOT NULL REFERENCES media(id) ON DELETE CASCADE,
    season_id INTEGER REFERENCES media_seasons(id) ON DELETE SET NULL,
    episode_number REAL NOT NULL,
    episode_type TEXT NOT NULL DEFAULT 'NORMAL',
    title TEXT,
    duration_minutes INTEGER,
    UNIQUE(media_id, episode_type, episode_number)
);
CREATE TABLE IF NOT EXISTS external_identities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    media_id INTEGER NOT NULL REFERENCES media(id) ON DELETE CASCADE,
    provider_id TEXT NOT NULL REFERENCES providers(id),
    external_id TEXT NOT NULL,
    url TEXT,
    confidence REAL NOT NULL DEFAULT 1.0,
    UNIQUE(provider_id, external_id)
);
CREATE TABLE IF NOT EXISTS conflicts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    media_id INTEGER NOT NULL REFERENCES media(id) ON DELETE CASCADE,
    account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    field TEXT NOT NULL,
    local_value TEXT,
    remote_value TEXT,
    remote_updated_at TEXT,
    detected_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status TEXT NOT NULL DEFAULT 'pending',
    resolution_value TEXT,
    resolved_at TEXT,
    UNIQUE(media_id, account_id, field, status)
);
CREATE TABLE IF NOT EXISTS extension_clients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    label TEXT NOT NULL,
    token_hash TEXT NOT NULL UNIQUE,
    created_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL,
    last_seen_at INTEGER,
    revoked_at INTEGER
);
CREATE TABLE IF NOT EXISTS library_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    media_id INTEGER NOT NULL UNIQUE REFERENCES media(id) ON DELETE CASCADE,
    status TEXT NOT NULL,
    progress INTEGER NOT NULL DEFAULT 0,
    score REAL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS remote_library_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    media_id INTEGER NOT NULL REFERENCES media(id) ON DELETE CASCADE,
    external_entry_id TEXT,
    status TEXT NOT NULL,
    progress INTEGER NOT NULL DEFAULT 0,
    score REAL,
    original_payload TEXT NOT NULL,
    last_synced_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(account_id, media_id)
);
CREATE TABLE IF NOT EXISTS media_details_cache (
    media_id INTEGER NOT NULL REFERENCES media(id) ON DELETE CASCADE,
    provider_id TEXT NOT NULL REFERENCES providers(id),
    external_id TEXT NOT NULL,
    title TEXT,
    title_romaji TEXT,
    title_english TEXT,
    title_native TEXT,
    synonyms_json TEXT NOT NULL DEFAULT '[]',
    description TEXT,
    site_url TEXT,
    banner_image TEXT,
    cover_image TEXT,
    banner_image_local TEXT,
    cover_image_local TEXT,
    color TEXT,
    format TEXT,
    media_type TEXT NOT NULL DEFAULT 'ANIME',
    status TEXT,
    source TEXT,
    season TEXT,
    season_year INTEGER,
    episodes INTEGER,
    chapters INTEGER,
    volumes INTEGER,
    duration INTEGER,
    genres_json TEXT NOT NULL DEFAULT '[]',
    studios_json TEXT NOT NULL DEFAULT '[]',
    country TEXT,
    average_score INTEGER,
    next_episode INTEGER,
    next_airing_at INTEGER,
    score_format TEXT,
    trailer_json TEXT,
    characters_json TEXT NOT NULL DEFAULT '[]',
    staff_json TEXT NOT NULL DEFAULT '[]',
    relations_json TEXT NOT NULL DEFAULT '[]',
    recommendations_json TEXT NOT NULL DEFAULT '[]',
    fetched_at INTEGER NOT NULL DEFAULT 0,
    provider_updated_at INTEGER,
    payload_hash TEXT,
    PRIMARY KEY (media_id, provider_id)
);
CREATE TABLE IF NOT EXISTS wont_watch (
    provider_id TEXT NOT NULL,
    external_id TEXT NOT NULL,
    title TEXT,
    cover_image TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (provider_id, external_id)
);
CREATE TABLE IF NOT EXISTS library_folders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT NOT NULL UNIQUE,
    recursive INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS local_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT NOT NULL UNIQUE,
    media_id INTEGER REFERENCES media(id) ON DELETE SET NULL,
    episode INTEGER,
    parsed_title TEXT,
    matched INTEGER NOT NULL DEFAULT 0,
    scanned_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS torrent_sources (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  url TEXT NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 1,
  kind TEXT NOT NULL DEFAULT 'release',
  created_at INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS torrent_seen (
  signature TEXT PRIMARY KEY,
  media_id INTEGER,
  discarded INTEGER NOT NULL DEFAULT 0,
  downloaded INTEGER NOT NULL DEFAULT 0,
  seen_at INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS pending_mutations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  provider_id TEXT NOT NULL,
  account_alias TEXT NOT NULL,
  kind TEXT NOT NULL,
  external_id TEXT NOT NULL,
  media_id INTEGER,
  payload TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  attempts INTEGER NOT NULL DEFAULT 0,
  next_attempt_at INTEGER NOT NULL DEFAULT 0,
  event_id INTEGER,
  error TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

CANONICAL_SCHEMA_VERSION = 7
# media: alto a propósito — los detalles guardados en local son lo que hace que
# reabrir/editar una card sea instantáneo (estilo Taiga); son JSON pequeños.
CACHE_RESOURCE_LIMITS = {"media:": 500, "season:": 24, "discover:": 80}


@dataclass(frozen=True, slots=True)
class CacheRecord:
    key: str
    payload: object
    expires_at: int
    updated_at: int
    stale: bool
    provider_id: str | None = None
    account_alias: str | None = None
    resource: str | None = None
    refresh_reason: str | None = None


class Database:
    def __init__(self, path: Path):
        self.path = path

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self._requires_canonical_migration():
            self._backup_before_migration()
        with self.connect() as connection:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.executescript(SCHEMA)
            self._migrate_torrent_filters(connection)
            columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(cache)").fetchall()
            }
            if "created_at" not in columns:
                connection.execute(
                    "ALTER TABLE cache ADD COLUMN created_at INTEGER NOT NULL DEFAULT 0"
                )
            if "updated_at" not in columns:
                connection.execute(
                    "ALTER TABLE cache ADD COLUMN updated_at INTEGER NOT NULL DEFAULT 0"
                )
            self._add_column(connection, "cache", "accessed_at", "INTEGER NOT NULL DEFAULT 0")
            self._add_column(connection, "cache", "provider_id", "TEXT")
            self._add_column(connection, "cache", "account_alias", "TEXT")
            self._add_column(connection, "cache", "resource", "TEXT")
            self._add_column(connection, "cache", "refresh_reason", "TEXT")
            self._add_column(connection, "playback_events", "status", "TEXT NOT NULL DEFAULT 'pending'")
            self._add_column(connection, "playback_events", "media_id", "INTEGER")
            self._add_column(connection, "playback_events", "progress_before", "INTEGER")
            self._add_column(connection, "playback_events", "progress_after", "INTEGER")
            self._add_column(connection, "playback_events", "provider_id", "TEXT")
            self._add_column(connection, "playback_events", "account_id", "INTEGER")
            self._add_column(connection, "playback_events", "canonical_media_id", "INTEGER")
            self._add_column(connection, "playback_events", "error_message", "TEXT")
            self._add_column(connection, "match_corrections", "provider_id", "TEXT")
            self._add_column(connection, "match_corrections", "canonical_media_id", "INTEGER")
            self._add_column(connection, "media_details_cache", "banner_image_local", "TEXT")
            self._add_column(connection, "media_details_cache", "cover_image_local", "TEXT")
            self._add_column(connection, "media_details_cache", "provider_updated_at", "INTEGER")
            self._add_column(connection, "media", "release_year", "INTEGER")
            self._add_column(connection, "media", "chapter_count", "INTEGER")
            self._add_column(connection, "media", "volume_count", "INTEGER")
            self._add_column(connection, "media_titles", "normalized_title", "TEXT")
            self._backfill_normalized_titles(connection)
            self._backfill_media_types(connection)
            self._add_column(connection, "library_entries", "started_at", "TEXT")
            self._add_column(connection, "library_entries", "completed_at", "TEXT")
            self._add_column(connection, "torrent_sources", "kind", "TEXT NOT NULL DEFAULT 'release'")
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_media_titles_normalized "
                "ON media_titles(normalized_title)"
            )
            connection.execute(
                "INSERT OR IGNORE INTO schema_migrations(version) VALUES (?)",
                (CANONICAL_SCHEMA_VERSION,),
            )
            self.ensure_provider("anilist", "AniList", connection=connection)
            existing = connection.execute(
                "SELECT COUNT(*) AS n FROM torrent_sources"
            ).fetchone()
            if existing["n"] == 0:
                connection.execute(
                    "INSERT INTO torrent_sources(name, url, enabled, created_at) "
                    "VALUES (?, ?, 1, ?)",
                    (
                        "Nyaa",
                        # Anime English-translated, ordenado por fecha (RSS).
                        "https://nyaa.si/?page=rss&c=1_2&f=0",
                        int(time.time()),
                    ),
                )

    @staticmethod
    def _backfill_normalized_titles(connection: sqlite3.Connection) -> None:
        rows = connection.execute(
            "SELECT media_id, language, title FROM media_titles "
            "WHERE normalized_title IS NULL OR normalized_title = ''"
        ).fetchall()
        connection.executemany(
            "UPDATE media_titles SET normalized_title = ? "
            "WHERE media_id = ? AND language = ? AND title = ?",
            (
                (normalize_title(row["title"]).casefold(), row["media_id"], row["language"], row["title"])
                for row in rows
            ),
        )

    @staticmethod
    def _backfill_media_types(connection: sqlite3.Connection) -> None:
        # Repara filas de `media` anteriores a que sync_media_details escribiera
        # media_type: la ficha cacheada ya sabe si es ANIME o MANGA. Solo toca las
        # que no cuadran, así que a partir del primer arranque no reescribe nada.
        connection.execute(
            "UPDATE media SET media_type = ("
            "SELECT media_type FROM media_details_cache d "
            "WHERE d.media_id = media.id AND d.media_type IN ('ANIME', 'MANGA') "
            "LIMIT 1) "
            "WHERE id IN ("
            "SELECT d.media_id FROM media_details_cache d "
            "JOIN media m ON m.id = d.media_id "
            "WHERE d.media_type IN ('ANIME', 'MANGA') "
            "AND (m.media_type IS NULL OR m.media_type != d.media_type))"
        )

    @staticmethod
    def _loads_json_or_default(value: str | None, default):
        if not value:
            return default
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default

    def _detect_conflict(
        self,
        connection: sqlite3.Connection,
        account_id: int,
        media_id: int,
        new_payload: dict,
    ) -> None:
        old_row = connection.execute(
            "SELECT status, progress, original_payload FROM remote_library_entries "
            "WHERE account_id = ? AND media_id = ?",
            (account_id, media_id),
        ).fetchone()
        if old_row is None:
            return
        old_status = old_row["status"]
        old_progress = old_row["progress"]
        new_status = new_payload.get("status")
        new_progress = new_payload.get("progress")
        remote_changed = old_status != new_status or old_progress != new_progress
        if not remote_changed:
            return
        local_row = connection.execute(
            "SELECT status, progress FROM library_entries WHERE media_id = ?",
            (media_id,),
        ).fetchone()
        if local_row is None:
            return
        local_changed = (
            local_row["status"] != old_status or local_row["progress"] != old_progress
        )
        if not local_changed:
            return
        if local_row["status"] != new_status:
            self.record_conflict(
                media_id,
                account_id,
                "status",
                local_row["status"],
                new_status,
                connection=connection,
            )
        if local_row["progress"] != new_progress:
            self.record_conflict(
                media_id,
                account_id,
                "progress",
                str(local_row["progress"]),
                str(new_progress),
                connection=connection,
            )

    @staticmethod
    def _payload_titles(payload: dict) -> list[tuple[str, str, bool]]:
        values = [
            ("USER_PREFERRED", payload.get("title"), True),
            ("ROMAJI", payload.get("title_romaji"), False),
            ("ENGLISH", payload.get("title_english"), False),
            ("NATIVE", payload.get("title_native"), False),
        ]
        values.extend(("SYNONYM", title, False) for title in payload.get("synonyms") or [])
        result: list[tuple[str, str, bool]] = []
        seen: set[tuple[str, str]] = set()
        for language, title, primary in values:
            if not title or (language, title) in seen:
                continue
            seen.add((language, title))
            result.append((language, title, primary))
        return result

    @staticmethod
    def _add_column(
        connection: sqlite3.Connection, table: str, column: str, definition: str
    ) -> None:
        columns = {
            row["name"] for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if column not in columns:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    @staticmethod
    def _migrate_torrent_filters(connection: sqlite3.Connection) -> None:
        cols = {r["name"] for r in connection.execute("PRAGMA table_info(torrent_filters)").fetchall()}
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS torrent_filter_conditions (
              id INTEGER PRIMARY KEY,
              filter_id INTEGER NOT NULL REFERENCES torrent_filters(id) ON DELETE CASCADE,
              element TEXT NOT NULL, operator TEXT NOT NULL, value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS torrent_filter_anime (
              filter_id INTEGER NOT NULL REFERENCES torrent_filters(id) ON DELETE CASCADE,
              media_id INTEGER NOT NULL,
              PRIMARY KEY (filter_id, media_id)
            );
            """
        )
        if "field" in cols:  # old C7 schema -> migrate
            old = connection.execute(
                "SELECT id, field, op, value, action, enabled FROM torrent_filters"
            ).fetchall()
            connection.execute("ALTER TABLE torrent_filters RENAME TO torrent_filters_old_c7")
            connection.execute(
                """
                CREATE TABLE torrent_filters (
                  id INTEGER PRIMARY KEY, name TEXT NOT NULL,
                  action TEXT NOT NULL, match TEXT NOT NULL, scope TEXT NOT NULL,
                  enabled INTEGER NOT NULL DEFAULT 1, created_at INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            action_map = {"exclude": "discard", "include": "select", "prefer": "prefer"}
            for r in old:
                cur = connection.execute(
                    "INSERT INTO torrent_filters(name, action, match, scope, enabled, created_at) "
                    "VALUES (?, ?, 'all', 'all', ?, ?)",
                    (f"{r['field']} {r['op']} {r['value']}",
                     action_map.get(r["action"], "discard"), r["enabled"], int(time.time())),
                )
                connection.execute(
                    "INSERT INTO torrent_filter_conditions(filter_id, element, operator, value) "
                    "VALUES (?, ?, ?, ?)",
                    (cur.lastrowid, r["field"], r["op"], r["value"]),
                )
            connection.execute("DROP TABLE torrent_filters_old_c7")
        else:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS torrent_filters (
                  id INTEGER PRIMARY KEY, name TEXT NOT NULL,
                  action TEXT NOT NULL, match TEXT NOT NULL, scope TEXT NOT NULL,
                  enabled INTEGER NOT NULL DEFAULT 1, created_at INTEGER NOT NULL DEFAULT 0
                )
                """
            )

    def _requires_canonical_migration(self) -> bool:
        if self.path == Path(":memory:") or not self.path.exists() or self.path.stat().st_size == 0:
            return False
        connection = sqlite3.connect(self.path)
        try:
            table = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'schema_migrations'"
            ).fetchone()
            if not table:
                return True
            row = connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
            return not row or (row[0] or 0) < CANONICAL_SCHEMA_VERSION
        finally:
            connection.close()

    def _backup_before_migration(self) -> Path:
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        backup_path = self.path.with_name(
            f"{self.path.stem}.backup-v{CANONICAL_SCHEMA_VERSION}-{timestamp}{self.path.suffix}"
        )
        source = sqlite3.connect(self.path)
        destination = sqlite3.connect(backup_path)
        try:
            source.backup(destination)
        finally:
            destination.close()
            source.close()
        return backup_path

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        # timeout=30s: con el backfill escribiendo en un hilo, una request interactiva
        # espera el lock en vez de fallar con "database is locked".
        connection = sqlite3.connect(self.path, timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        # WAL: los lectores no se bloquean con el escritor del backfill (:memory: lo ignora).
        if self.path != Path(":memory:"):
            connection.execute("PRAGMA journal_mode = WAL")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def get_setting(self, key: str) -> str | None:
        with self.connect() as connection:
            row = connection.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
            return row["value"] if row else None

    def set_setting(self, key: str, value: str) -> None:
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO settings(key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )

    def delete_setting(self, key: str) -> None:
        with self.connect() as connection:
            connection.execute("DELETE FROM settings WHERE key = ?", (key,))

    def get_library_folders(self) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT id, path, recursive FROM library_folders ORDER BY path"
            ).fetchall()
            return [
                {"id": row["id"], "path": row["path"], "recursive": bool(row["recursive"])}
                for row in rows
            ]

    def add_library_folder(self, path: str, recursive: bool) -> dict:
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO library_folders(path, recursive) VALUES (?, ?) "
                "ON CONFLICT(path) DO UPDATE SET recursive = excluded.recursive",
                (path, int(recursive)),
            )
            row = connection.execute(
                "SELECT id, path, recursive FROM library_folders WHERE path = ?", (path,)
            ).fetchone()
            return {"id": row["id"], "path": row["path"], "recursive": bool(row["recursive"])}

    def delete_library_folder(self, folder_id: int) -> bool:
        with self.connect() as connection:
            cursor = connection.execute(
                "DELETE FROM library_folders WHERE id = ?", (folder_id,)
            )
            return cursor.rowcount > 0

    def replace_local_files(self, rows: list[dict]) -> None:
        with self.connect() as connection:
            connection.execute("DELETE FROM local_files")
            connection.executemany(
                "INSERT OR IGNORE INTO local_files"
                "(path, media_id, episode, parsed_title, matched) "
                "VALUES (?, ?, ?, ?, ?)",
                [
                    (
                        row["path"],
                        row.get("media_id"),
                        row.get("episode"),
                        row.get("parsed_title"),
                        int(bool(row.get("media_id"))),
                    )
                    for row in rows
                ],
            )

    def set_local_files_media(
        self,
        media_id: int | None,
        from_media_id: int | None = None,
        parsed_title: str | None = None,
    ) -> int:
        """(Re)asocia un grupo de archivos escaneados a una obra canónica.

        Identifica el grupo por su media_id actual (grupos matcheados) o por
        parsed_title (grupos sin asociar). ``media_id=None`` quita la asociación.
        """
        matched = int(media_id is not None)
        with self.connect() as connection:
            if from_media_id is not None:
                cursor = connection.execute(
                    "UPDATE local_files SET media_id = ?, matched = ? WHERE media_id = ?",
                    (media_id, matched, from_media_id),
                )
            else:
                cursor = connection.execute(
                    "UPDATE local_files SET media_id = ?, matched = ? WHERE parsed_title = ?",
                    (media_id, matched, parsed_title),
                )
            return cursor.rowcount

    def get_local_parsed_titles(self, media_id: int) -> list[str]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT DISTINCT parsed_title FROM local_files "
                "WHERE media_id = ? AND parsed_title IS NOT NULL",
                (media_id,),
            ).fetchall()
            return [row["parsed_title"] for row in rows]

    def primary_title(self, media_id: int) -> str | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT title FROM media_titles WHERE media_id = ? "
                "ORDER BY is_primary DESC, "
                "CASE language WHEN 'USER_PREFERRED' THEN 0 WHEN 'ROMAJI' THEN 1 ELSE 2 END "
                "LIMIT 1",
                (media_id,),
            ).fetchone()
            return row["title"] if row else None

    def media_total_units(self, media_id: int) -> int | None:
        """Episodios (anime) o capítulos (manga) totales del catálogo, si se conocen."""
        with self.connect() as connection:
            row = connection.execute(
                "SELECT media_type, episode_count, chapter_count FROM media WHERE id = ?",
                (media_id,),
            ).fetchone()
            if row is None:
                return None
            return row["chapter_count"] if row["media_type"] == "MANGA" else row["episode_count"]

    # --- Cola de mutaciones: efecto local inmediato, envío al proveedor en segundo plano ---

    def enqueue_mutation(
        self,
        provider_id: str,
        account_alias: str,
        kind: str,
        external_id: str | int,
        payload: dict,
        media_id: int | None = None,
        event_id: int | None = None,
    ) -> int:
        with self.connect() as connection:
            cursor = connection.execute(
                "INSERT INTO pending_mutations"
                "(provider_id, account_alias, kind, external_id, media_id, payload, event_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    provider_id,
                    account_alias,
                    kind,
                    str(external_id),
                    media_id,
                    json.dumps(payload),
                    event_id,
                ),
            )
            return int(cursor.lastrowid)

    def due_mutations(self, now: int, limit: int = 10) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM pending_mutations "
                "WHERE status = 'pending' AND next_attempt_at <= ? "
                "ORDER BY id LIMIT ?",
                (now, limit),
            ).fetchall()
            return [dict(row) for row in rows]

    def mark_mutation_done(self, mutation_id: int) -> None:
        with self.connect() as connection:
            connection.execute(
                "DELETE FROM pending_mutations WHERE id = ?", (mutation_id,)
            )

    def mark_mutation_retry(
        self, mutation_id: int, attempts: int, next_attempt_at: int, error: str
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                "UPDATE pending_mutations SET attempts = ?, next_attempt_at = ?, error = ? "
                "WHERE id = ?",
                (attempts, next_attempt_at, error[:500], mutation_id),
            )

    def mark_mutation_failed(self, mutation_id: int, error: str) -> None:
        with self.connect() as connection:
            connection.execute(
                "UPDATE pending_mutations SET status = 'failed', error = ? WHERE id = ?",
                (error[:500], mutation_id),
            )

    def requeue_mutation_by_event(self, event_id: int) -> bool:
        """Reactiva la mutación fallida asociada a un evento del historial."""
        with self.connect() as connection:
            cursor = connection.execute(
                "UPDATE pending_mutations SET status = 'pending', attempts = 0, "
                "next_attempt_at = 0, error = NULL "
                "WHERE event_id = ? AND status = 'failed'",
                (event_id,),
            )
            return cursor.rowcount > 0

    def pending_mutation_overrides(
        self, provider_id: str, account_alias: str
    ) -> dict[str, dict]:
        """Cambios aún en cola por external_id, para superponerlos a la lista en vivo
        hasta que el proveedor los confirme (misma idea que recent_remote_overrides)."""
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT external_id, payload FROM pending_mutations "
                "WHERE provider_id = ? AND account_alias = ? AND status = 'pending' "
                "ORDER BY id",
                (provider_id, account_alias),
            ).fetchall()
        overrides: dict[str, dict] = {}
        for row in rows:
            payload = json.loads(row["payload"])
            changes = {
                key: payload[key]
                for key in ("status", "progress", "score")
                if payload.get(key) is not None
            }
            if changes:
                overrides.setdefault(row["external_id"], {}).update(changes)
        return overrides

    def has_remote_library_entry(
        self, provider_id: str, account_alias: str, media_id: int
    ) -> bool:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM remote_library_entries rle "
                "JOIN accounts a ON a.id = rle.account_id "
                "WHERE a.provider_id = ? AND a.alias = ? AND rle.media_id = ? LIMIT 1",
                (provider_id, account_alias, media_id),
            ).fetchone()
            return row is not None

    def local_series_folder(self, media_id: int) -> str | None:
        """Carpeta donde ya viven los episodios locales de una obra (el archivo más
        reciente manda), para descargar los torrents nuevos junto a ellos."""
        with self.connect() as connection:
            row = connection.execute(
                "SELECT path FROM local_files WHERE media_id = ? ORDER BY rowid DESC LIMIT 1",
                (media_id,),
            ).fetchone()
            if row is None:
                return None
            return str(Path(row["path"]).parent)

    def get_local_match_overrides(self) -> dict[str, int]:
        """Correcciones manuales como {patrón normalizado: media_id canónico},
        para que el escaneo las respete antes del matching difuso."""
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT raw_pattern, canonical_media_id FROM match_corrections "
                "WHERE canonical_media_id IS NOT NULL"
            ).fetchall()
            return {row["raw_pattern"]: int(row["canonical_media_id"]) for row in rows}

    def get_local_series(self) -> list[dict]:
        """Series escaneadas agrupadas. Matcheadas por media_id (con título canónico);
        no matcheadas agrupadas por parsed_title (media_id None)."""
        with self.connect() as connection:
            matched = connection.execute(
                """
                SELECT lf.media_id AS media_id,
                       COALESCE(
                           (SELECT mt.title FROM media_titles mt
                            WHERE mt.media_id = lf.media_id
                            ORDER BY mt.is_primary DESC,
                                     CASE mt.language
                                         WHEN 'USER_PREFERRED' THEN 0
                                         WHEN 'ROMAJI' THEN 1
                                         ELSE 2
                                     END
                            LIMIT 1),
                           lf.parsed_title
                       ) AS title,
                       COUNT(*) AS episode_count
                FROM local_files lf
                WHERE lf.media_id IS NOT NULL
                GROUP BY lf.media_id
                ORDER BY title COLLATE NOCASE
                """
            ).fetchall()
            unmatched = connection.execute(
                """
                SELECT parsed_title AS title, COUNT(*) AS episode_count
                FROM local_files
                WHERE media_id IS NULL AND parsed_title IS NOT NULL
                GROUP BY parsed_title
                ORDER BY title COLLATE NOCASE
                """
            ).fetchall()
            result = [
                {"media_id": r["media_id"], "title": r["title"] or "", "episode_count": r["episode_count"], "matched": True}
                for r in matched
            ]
            result += [
                {"media_id": None, "title": r["title"] or "", "episode_count": r["episode_count"], "matched": False}
                for r in unmatched
            ]
            return result

    def get_local_files_summary(self) -> dict:
        with self.connect() as connection:
            total = connection.execute("SELECT COUNT(*) FROM local_files").fetchone()[0]
            matched = connection.execute(
                "SELECT COUNT(*) FROM local_files WHERE matched = 1"
            ).fetchone()[0]
            return {"total": total, "matched": matched, "unmatched": total - matched}

    def get_local_episodes_by_media(self) -> dict[int, dict[int, str]]:
        """Matched local files as {canonical_media_id: {episode: path}}.

        Los archivos sin número de episodio (películas, especiales sueltos) cuentan
        como episodio 1: si no, la card no ofrecía botón de reproducción."""
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT media_id, COALESCE(episode, 1) AS episode, path FROM local_files "
                "WHERE matched = 1 AND media_id IS NOT NULL "
                "ORDER BY path"
            ).fetchall()
        by_media: dict[int, dict[int, str]] = {}
        for row in rows:
            by_media.setdefault(int(row["media_id"]), {}).setdefault(
                int(row["episode"]), row["path"]
            )
        return by_media

    def get_cache(self, key: str):
        record = self.get_cache_record(key)
        return record.payload if record is not None and not record.stale else None

    def get_cache_meta(self, key: str) -> tuple[int, bool] | None:
        """(updated_at, stale) sin deserializar el payload: fingerprint barato para
        memoizar en proceso listas grandes (la de biblioteca ronda los 3 MB de JSON)."""
        with self.connect() as connection:
            row = connection.execute(
                "SELECT updated_at, expires_at FROM cache WHERE key = ?", (key,)
            ).fetchone()
            if not row:
                return None
            return row["updated_at"], row["expires_at"] <= int(time.time())

    def get_cache_record(self, key: str) -> CacheRecord | None:
        now = int(time.time())
        with self.connect() as connection:
            row = connection.execute(
                "SELECT key, payload, expires_at, updated_at, provider_id, account_alias, "
                "resource, refresh_reason FROM cache WHERE key = ?",
                (key,),
            ).fetchone()
            if not row:
                return None
            try:
                payload = json.loads(row["payload"])
            except json.JSONDecodeError:
                connection.execute("DELETE FROM cache WHERE key = ?", (key,))
                return None
            connection.execute(
                "UPDATE cache SET accessed_at = ? WHERE key = ?", (now, key)
            )
            return CacheRecord(
                key=row["key"],
                payload=payload,
                expires_at=row["expires_at"],
                updated_at=row["updated_at"],
                stale=row["expires_at"] <= now,
                provider_id=row["provider_id"],
                account_alias=row["account_alias"],
                resource=row["resource"],
                refresh_reason=row["refresh_reason"],
            )

    def set_cache(
        self,
        key: str,
        payload,
        ttl_seconds: int,
        *,
        provider_id: str | None = None,
        account_alias: str | None = None,
        resource: str | None = None,
        refresh_reason: str = "network_refresh",
    ) -> None:
        now = int(time.time())
        expires_at = now + ttl_seconds
        serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        key_parts = key.split(":", 2)
        if len(key_parts) == 3:
            provider_id = provider_id or key_parts[0]
            account_alias = account_alias or key_parts[1]
            resource = resource or key_parts[2]
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO cache(key, payload, expires_at, created_at, updated_at, accessed_at, "
                "provider_id, account_alias, resource, refresh_reason) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET payload = excluded.payload, "
                "expires_at = excluded.expires_at, updated_at = excluded.updated_at, "
                "accessed_at = excluded.accessed_at, "
                "provider_id = excluded.provider_id, account_alias = excluded.account_alias, "
                "resource = excluded.resource, refresh_reason = excluded.refresh_reason",
                (
                    key,
                    serialized,
                    expires_at,
                    now,
                    now,
                    now,
                    provider_id,
                    account_alias,
                    resource,
                    refresh_reason,
                ),
            )
            for prefix, limit in CACHE_RESOURCE_LIMITS.items():
                if resource and resource.startswith(prefix):
                    connection.execute(
                        "DELETE FROM cache WHERE key IN ("
                        "SELECT key FROM cache WHERE provider_id IS ? AND account_alias IS ? "
                        "AND resource LIKE ? ORDER BY accessed_at DESC, key DESC "
                        "LIMIT -1 OFFSET ?)",
                        (provider_id, account_alias, f"{prefix}%", limit),
                    )
                    break

    def get_cache_status(self) -> list[dict]:
        now = int(time.time())
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT key, expires_at, updated_at, length(payload) AS size, "
                "provider_id, account_alias, resource, refresh_reason "
                "FROM cache ORDER BY key"
            ).fetchall()
            return [
                {
                    "key": row["key"],
                    "expires_at": row["expires_at"],
                    "updated_at": row["updated_at"],
                    "size": row["size"],
                    "stale": row["expires_at"] <= now,
                    "provider_id": row["provider_id"],
                    "account_alias": row["account_alias"],
                    "resource": row["resource"],
                    "refresh_reason": row["refresh_reason"],
                }
                for row in rows
            ]

    def invalidate_cache(self, prefix: str | None = None) -> None:
        with self.connect() as connection:
            if prefix is None:
                connection.execute("DELETE FROM cache")
            else:
                connection.execute("DELETE FROM cache WHERE key LIKE ?", (f"{prefix}%",))

    def clear_all_data(self) -> None:
        with self.connect() as connection:
            connection.execute("DELETE FROM settings")
            connection.execute("DELETE FROM playback_events")
            connection.execute("DELETE FROM match_corrections")
            connection.execute("DELETE FROM cache")
            connection.execute("DELETE FROM remote_library_entries")
            connection.execute("DELETE FROM library_entries")
            connection.execute("DELETE FROM external_identities")
            connection.execute("DELETE FROM media_titles")
            connection.execute("DELETE FROM media")
            connection.execute("DELETE FROM accounts")
            connection.execute("DELETE FROM extension_clients")

    def create_extension_client(
        self, label: str, token_hash: str, expires_at: int
    ) -> int:
        now = int(time.time())
        with self.connect() as connection:
            cursor = connection.execute(
                "INSERT INTO extension_clients(label, token_hash, created_at, expires_at) "
                "VALUES (?, ?, ?, ?)",
                (label, token_hash, now, expires_at),
            )
            return int(cursor.lastrowid)

    def validate_extension_token(self, token_hash: str) -> bool:
        now = int(time.time())
        with self.connect() as connection:
            row = connection.execute(
                "SELECT id FROM extension_clients WHERE token_hash = ? "
                "AND revoked_at IS NULL AND expires_at > ?",
                (token_hash, now),
            ).fetchone()
            if row is None:
                return False
            connection.execute(
                "UPDATE extension_clients SET last_seen_at = ? WHERE id = ?",
                (now, row["id"]),
            )
            return True

    def rotate_extension_token(
        self, old_token_hash: str, new_token_hash: str, expires_at: int, label: str | None = None
    ) -> bool:
        now = int(time.time())
        with self.connect() as connection:
            cursor = connection.execute(
                "UPDATE extension_clients SET token_hash = ?, expires_at = ?, "
                "label = COALESCE(?, label), last_seen_at = ? "
                "WHERE token_hash = ? AND revoked_at IS NULL AND expires_at > ?",
                (new_token_hash, expires_at, label, now, old_token_hash, now),
            )
            return cursor.rowcount == 1

    def revoke_extension_clients_by_label(self, label: str) -> int:
        # Al re-emparejar un mismo navegador (token caducado/revocado) se creaba una fila
        # nueva cada vez y se acumulaban clientes duplicados. Revocamos los activos con esa
        # etiqueta antes de crear el nuevo, dejando un único cliente activo por navegador.
        with self.connect() as connection:
            cursor = connection.execute(
                "UPDATE extension_clients SET revoked_at = ? "
                "WHERE label = ? AND revoked_at IS NULL",
                (int(time.time()), label),
            )
            return cursor.rowcount

    def revoke_extension_client(self, client_id: int) -> bool:
        with self.connect() as connection:
            cursor = connection.execute(
                "UPDATE extension_clients SET revoked_at = ? "
                "WHERE id = ? AND revoked_at IS NULL",
                (int(time.time()), client_id),
            )
            return cursor.rowcount == 1

    def get_extension_clients(self) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT id, label, created_at, expires_at, last_seen_at, revoked_at "
                "FROM extension_clients ORDER BY created_at DESC"
            ).fetchall()
            return [dict(row) for row in rows]

    def ensure_provider(
        self,
        provider_id: str,
        display_name: str,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> None:
        if connection is None:
            with self.connect() as own_connection:
                self.ensure_provider(provider_id, display_name, connection=own_connection)
            return
        connection.execute(
            "INSERT INTO providers(id, display_name) VALUES (?, ?) "
            "ON CONFLICT(id) DO UPDATE SET display_name = excluded.display_name",
            (provider_id, display_name),
        )

    def ensure_account(
        self,
        provider_id: str,
        alias: str = "default",
        credential_ref: str | None = None,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> int:
        alias = "default"
        if connection is None:
            with self.connect() as own_connection:
                return self.ensure_account(
                    provider_id,
                    alias,
                    credential_ref,
                    connection=own_connection,
                )
        connection.execute(
            "INSERT INTO accounts(provider_id, alias, credential_ref) VALUES (?, ?, ?) "
            "ON CONFLICT(provider_id, alias) DO UPDATE SET "
            "credential_ref = COALESCE(excluded.credential_ref, accounts.credential_ref)",
            (provider_id, alias, credential_ref),
        )
        row = connection.execute(
            "SELECT id FROM accounts WHERE provider_id = ? AND alias = ?",
            (provider_id, alias),
        ).fetchone()
        account_id = int(row["id"])
        primary = connection.execute(
            "SELECT id FROM accounts WHERE provider_id = ? AND is_primary = 1",
            (provider_id,),
        ).fetchone()
        if primary is None:
            connection.execute("UPDATE accounts SET is_primary = 1 WHERE id = ?", (account_id,))
        return account_id

    def get_accounts(self) -> list[dict]:
        # has_credential_ref distingue "nunca conectó" (fila creada por rutas de
        # lectura, credential_ref NULL) de "sesión caducada" (hubo login real).
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT id, provider_id AS provider, alias, is_primary, "
                "last_synced_at, credential_ref IS NOT NULL AS has_credential_ref "
                "FROM accounts WHERE alias = 'default' "
                "ORDER BY provider_id, is_primary DESC, alias"
            ).fetchall()
            return [dict(row) for row in rows]

    def update_account(
        self,
        account_id: int,
        *,
        is_primary: bool | None = None,
    ) -> dict | None:
        with self.connect() as connection:
            current = connection.execute(
                "SELECT * FROM accounts WHERE id = ?", (account_id,)
            ).fetchone()
            if current is None:
                return None
            if is_primary:
                connection.execute("UPDATE accounts SET is_primary = 0")
                connection.execute(
                    "UPDATE accounts SET is_primary = 1 WHERE id = ?", (account_id,)
                )
                primary_provider = connection.execute(
                    "SELECT value FROM settings WHERE key = 'primary_provider'"
                ).fetchone()
                if current["provider_id"] == (
                    primary_provider["value"] if primary_provider else "anilist"
                ):
                    connection.execute(
                        "INSERT INTO library_entries(media_id, status, progress, score) "
                        "SELECT media_id, status, progress, score FROM remote_library_entries "
                        "WHERE account_id = ? "
                        "ON CONFLICT(media_id) DO UPDATE SET status = excluded.status, "
                        "progress = excluded.progress, score = excluded.score, "
                        "updated_at = CURRENT_TIMESTAMP",
                        (account_id,),
                    )
            row = connection.execute(
                "SELECT id, provider_id AS provider, alias, is_primary, "
                "last_synced_at, credential_ref IS NOT NULL AS has_credential_ref "
                "FROM accounts WHERE id = ?",
                (account_id,),
            ).fetchone()
            return dict(row)

    def sync_provider_library(
        self,
        provider_id: str,
        display_name: str,
        items: list[object],
        account_alias: str = "default",
        media_type: str = "ANIME",
    ) -> dict[str, int]:
        mapping: dict[str, int] = {}
        with self.connect() as connection:
            self.ensure_provider(provider_id, display_name, connection=connection)
            account_id = self.ensure_account(
                provider_id,
                account_alias,
                credential_ref=f"keyring:{provider_id}:{account_alias}",
                connection=connection,
            )
            account_is_primary = bool(
                connection.execute(
                    "SELECT is_primary FROM accounts WHERE id = ?", (account_id,)
                ).fetchone()["is_primary"]
            )
            primary_provider_row = connection.execute(
                "SELECT value FROM settings WHERE key = 'primary_provider'"
            ).fetchone()
            primary_provider = primary_provider_row["value"] if primary_provider_row else "anilist"
            writes_canonical_library = account_is_primary and provider_id == primary_provider
            for item in items:
                payload = item.model_dump(mode="json")
                external_id = str(payload["id"])
                identity = connection.execute(
                    "SELECT media_id FROM external_identities "
                    "WHERE provider_id = ? AND external_id = ?",
                    (provider_id, external_id),
                ).fetchone()
                if identity:
                    media_id = int(identity["media_id"])
                else:
                    # ponytail: proveedores independientes, cada external_id es su propia obra.
                    cursor = connection.execute(
                        "INSERT INTO media(media_type, episode_count, chapter_count, "
                        "volume_count, format, release_year) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (
                            media_type,
                            payload.get("episodes"),
                            payload.get("chapters"),
                            payload.get("volumes"),
                            payload.get("format"),
                            payload.get("year"),
                        ),
                    )
                    media_id = int(cursor.lastrowid)
                    connection.execute(
                        "INSERT INTO external_identities"
                        "(media_id, provider_id, external_id, url) "
                        "VALUES (?, ?, ?, ?)",
                        (media_id, provider_id, external_id, payload.get("site_url")),
                    )
                # Referencia externa confiable: AniList publica el id de MAL de la misma
                # obra. Pre-registrarla hace que un sync posterior de MAL reutilice esta
                # fila canónica en vez de duplicarla. OR IGNORE: si MAL sincronizó primero,
                # su identidad ya apunta a su propia fila y no se roba.
                # ponytail: solo anime — los ids de anime y manga de MAL son espacios
                # numéricos distintos y la clave (provider, external_id) no distingue tipo;
                # extender a manga cuando la identidad incluya media_type.
                if provider_id == "anilist" and media_type == "ANIME" and payload.get("id_mal"):
                    # La identidad referencia providers(id); "mal" puede no existir aún.
                    self.ensure_provider("mal", "MyAnimeList", connection=connection)
                    connection.execute(
                        "INSERT OR IGNORE INTO external_identities"
                        "(media_id, provider_id, external_id, url) "
                        "VALUES (?, 'mal', ?, ?)",
                        (
                            media_id,
                            str(payload["id_mal"]),
                            f"https://myanimelist.net/anime/{payload['id_mal']}",
                        ),
                    )
                connection.execute(
                    "UPDATE media SET media_type = ?, episode_count = COALESCE(?, episode_count), "
                    "chapter_count = COALESCE(?, chapter_count), "
                    "volume_count = COALESCE(?, volume_count), "
                    "format = COALESCE(?, format), release_year = COALESCE(?, release_year), "
                    "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (
                        media_type,
                        payload.get("episodes"),
                        payload.get("chapters"),
                        payload.get("volumes"),
                        payload.get("format"),
                        payload.get("year"),
                        media_id,
                    ),
                )
                connection.execute(
                    "UPDATE media_titles SET is_primary = 0 "
                    "WHERE media_id = ? AND language = 'USER_PREFERRED'",
                    (media_id,),
                )
                for language, title, primary in self._payload_titles(payload):
                    # Upsert: con INSERT OR IGNORE la fila existente nunca recuperaba
                    # is_primary=1 tras el UPDATE previo, y la base quedaba sin ningún
                    # título primario después del segundo sync.
                    connection.execute(
                        "INSERT INTO media_titles"
                        "(media_id, language, title, normalized_title, is_primary) "
                        "VALUES (?, ?, ?, ?, ?) "
                        "ON CONFLICT(media_id, language, title) DO UPDATE SET "
                        "is_primary = excluded.is_primary, "
                        "normalized_title = excluded.normalized_title",
                        (
                            media_id,
                            language,
                            title,
                            normalize_title(title).casefold(),
                            int(primary),
                        ),
                    )
                connection.executemany(
                    "INSERT OR IGNORE INTO media_genres(media_id, genre) VALUES (?, ?)",
                    ((media_id, genre) for genre in payload.get("genres") or []),
                )
                episode_count = payload.get("episodes")
                self._detect_conflict(connection, account_id, media_id, payload)
                if writes_canonical_library:
                    connection.execute(
                        "INSERT INTO library_entries"
                        "(media_id, status, progress, started_at, completed_at) "
                        "VALUES (?, ?, ?, ?, ?) ON CONFLICT(media_id) DO UPDATE SET "
                        "status = excluded.status, progress = excluded.progress, "
                        "started_at = COALESCE(excluded.started_at, started_at), "
                        "completed_at = COALESCE(excluded.completed_at, completed_at), "
                        "updated_at = CURRENT_TIMESTAMP",
                        (
                            media_id,
                            payload["status"],
                            payload["progress"],
                            payload.get("started_at"),
                            payload.get("completed_at"),
                        ),
                    )
                if (
                    media_type == "ANIME"
                    and isinstance(episode_count, int)
                    and 0 < episode_count <= 10000
                ):
                    connection.executemany(
                        "INSERT OR IGNORE INTO episodes(media_id, episode_number) VALUES (?, ?)",
                        ((media_id, number) for number in range(1, episode_count + 1)),
                    )
                connection.execute(
                    "INSERT INTO remote_library_entries"
                    "(account_id, media_id, status, progress, original_payload) "
                    "VALUES (?, ?, ?, ?, ?) "
                    "ON CONFLICT(account_id, media_id) DO UPDATE SET "
                    "status = excluded.status, progress = excluded.progress, "
                    "original_payload = excluded.original_payload, "
                    "last_synced_at = CURRENT_TIMESTAMP",
                    (
                        account_id,
                        media_id,
                        payload["status"],
                        payload["progress"],
                        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                    ),
                )
                mapping[external_id] = media_id
            connection.execute(
                "UPDATE accounts SET last_synced_at = CURRENT_TIMESTAMP WHERE id = ?",
                (account_id,),
            )
        return mapping

    def sync_media_details(
        self,
        provider_id: str,
        external_id: str | int,
        details: object,
        media_type: str = "ANIME",
        *,
        _connection: sqlite3.Connection | None = None,
    ) -> int | None:
        payload = details.model_dump(mode="json")
        # _connection: reutiliza una transacción abierta (persist_details_batch) en vez
        # de abrir/cerrar una por item — clave para que el backfill no sature el lock.
        with (nullcontext(_connection) if _connection is not None else self.connect()) as connection:
            identity = connection.execute(
                "SELECT media_id FROM external_identities WHERE provider_id = ? AND external_id = ?",
                (provider_id, str(external_id)),
            ).fetchone()
            if identity is None:
                cursor = connection.execute(
                    "INSERT INTO media(media_type, format, episode_count, chapter_count, "
                    "volume_count, release_year) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        media_type,
                        payload.get("format"),
                        payload.get("episodes"),
                        payload.get("chapters"),
                        payload.get("volumes"),
                        payload.get("season_year"),
                    ),
                )
                media_id = int(cursor.lastrowid)
                connection.execute(
                    "INSERT INTO external_identities(media_id, provider_id, external_id, url) "
                    "VALUES (?, ?, ?, ?)",
                    (media_id, provider_id, str(external_id), payload.get("site_url")),
                )
            else:
                media_id = int(identity["media_id"])
            connection.execute(
                "UPDATE media SET media_type = ?, format = ?, episode_count = ?, chapter_count = ?, "
                "volume_count = ?, release_year = COALESCE(?, release_year), "
                "updated_at = CURRENT_TIMESTAMP "
                "WHERE id = ?",
                (
                    media_type,
                    payload.get("format"),
                    payload.get("episodes"),
                    payload.get("chapters"),
                    payload.get("volumes"),
                    payload.get("season_year"),
                    media_id,
                ),
            )
            titles = {
                "ROMAJI": payload.get("title_romaji"),
                "ENGLISH": payload.get("title_english"),
                "NATIVE": payload.get("title_native"),
            }
            for language, title in titles.items():
                if title:
                    connection.execute(
                        "INSERT OR IGNORE INTO media_titles"
                        "(media_id, language, title, normalized_title) VALUES (?, ?, ?, ?)",
                        (media_id, language, title, normalize_title(title).casefold()),
                    )
            connection.executemany(
                "INSERT OR IGNORE INTO media_genres(media_id, genre) VALUES (?, ?)",
                ((media_id, genre) for genre in payload.get("genres") or []),
            )
            season_year = payload.get("season_year")
            season_label = payload.get("season")
            if season_year or season_label:
                connection.execute(
                    "INSERT INTO media_seasons(media_id, season_number, label, year) "
                    "VALUES (?, 1, ?, ?) ON CONFLICT(media_id, season_number) DO UPDATE SET "
                    "label = excluded.label, year = excluded.year",
                    (media_id, season_label, season_year),
                )
                season_id = connection.execute(
                    "SELECT id FROM media_seasons WHERE media_id = ? AND season_number = 1",
                    (media_id,),
                ).fetchone()["id"]
            else:
                season_id = None
            episode_count = payload.get("episodes")
            if (
                media_type == "ANIME"
                and isinstance(episode_count, int)
                and 0 < episode_count <= 10000
            ):
                connection.executemany(
                    "INSERT OR IGNORE INTO episodes(media_id, season_id, episode_number) "
                    "VALUES (?, ?, ?)",
                    (
                        (media_id, season_id, number)
                        for number in range(1, episode_count + 1)
                    ),
                )
                if season_id is not None:
                    connection.execute(
                        "UPDATE episodes SET season_id = COALESCE(season_id, ?) WHERE media_id = ?",
                        (season_id, media_id),
                    )
            serialized_payload = json.dumps(
                payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            )
            connection.execute(
                "INSERT INTO media_details_cache("
                "media_id, provider_id, external_id, title, title_romaji, title_english, title_native, "
                "synonyms_json, description, site_url, banner_image, cover_image, banner_image_local, cover_image_local, color, format, "
                "media_type, status, source, season, season_year, episodes, chapters, volumes, "
                "duration, genres_json, studios_json, country, average_score, next_episode, "
                "next_airing_at, score_format, trailer_json, characters_json, staff_json, "
                "relations_json, recommendations_json, fetched_at, payload_hash"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(media_id, provider_id) DO UPDATE SET "
                "external_id = excluded.external_id, title = excluded.title, "
                "title_romaji = excluded.title_romaji, title_english = excluded.title_english, "
                "title_native = excluded.title_native, synonyms_json = excluded.synonyms_json, "
                "description = excluded.description, site_url = excluded.site_url, "
                "banner_image = excluded.banner_image, cover_image = excluded.cover_image, "
                "banner_image_local = COALESCE(media_details_cache.banner_image_local, excluded.banner_image_local), "
                "cover_image_local = COALESCE(media_details_cache.cover_image_local, excluded.cover_image_local), "
                "color = excluded.color, format = excluded.format, media_type = excluded.media_type, "
                "status = excluded.status, source = excluded.source, season = excluded.season, "
                "season_year = excluded.season_year, episodes = excluded.episodes, "
                "chapters = excluded.chapters, volumes = excluded.volumes, duration = excluded.duration, "
                "genres_json = excluded.genres_json, studios_json = excluded.studios_json, "
                "country = excluded.country, average_score = excluded.average_score, "
                "next_episode = excluded.next_episode, next_airing_at = excluded.next_airing_at, "
                "score_format = excluded.score_format, trailer_json = excluded.trailer_json, "
                # Los cuatro bloques pesados NO se pisan con un valor vacío. El backfill baja
                # un detalle LIGERO (sin characters/staff/relations/recommendations: ver
                # _ANIME_LIST_FIELDS) y esos campos llegan como '[]'. Sin esta guarda, cada
                # pasada del backfill BORRARÍA los personajes y relaciones que la apertura de
                # ficha había cacheado. Un '[]' entrante significa "no lo he pedido", no "no
                # tiene". Escribir vacío encima de datos buenos es pérdida de datos silenciosa.
                "characters_json = CASE WHEN excluded.characters_json IN ('[]', '') "
                "THEN media_details_cache.characters_json ELSE excluded.characters_json END, "
                "staff_json = CASE WHEN excluded.staff_json IN ('[]', '') "
                "THEN media_details_cache.staff_json ELSE excluded.staff_json END, "
                "relations_json = CASE WHEN excluded.relations_json IN ('[]', '') "
                "THEN media_details_cache.relations_json ELSE excluded.relations_json END, "
                "recommendations_json = CASE WHEN excluded.recommendations_json IN ('[]', '') "
                "THEN media_details_cache.recommendations_json ELSE excluded.recommendations_json END, "
                "fetched_at = excluded.fetched_at, payload_hash = excluded.payload_hash",
                (
                    media_id,
                    provider_id,
                    str(external_id),
                    payload.get("title"),
                    payload.get("title_romaji"),
                    payload.get("title_english"),
                    payload.get("title_native"),
                    json.dumps(payload.get("synonyms") or [], ensure_ascii=False, separators=(",", ":")),
                    payload.get("description"),
                    payload.get("site_url"),
                    payload.get("banner_image"),
                    payload.get("cover_image"),
                    None,
                    None,
                    payload.get("color"),
                    payload.get("format"),
                    payload.get("media_type") or media_type,
                    payload.get("status"),
                    payload.get("source"),
                    payload.get("season"),
                    payload.get("season_year"),
                    payload.get("episodes"),
                    payload.get("chapters"),
                    payload.get("volumes"),
                    payload.get("duration"),
                    json.dumps(payload.get("genres") or [], ensure_ascii=False, separators=(",", ":")),
                    json.dumps(payload.get("studios") or [], ensure_ascii=False, separators=(",", ":")),
                    payload.get("country"),
                    payload.get("average_score"),
                    payload.get("next_episode"),
                    payload.get("next_airing_at"),
                    payload.get("score_format"),
                    json.dumps(payload.get("trailer"), ensure_ascii=False, separators=(",", ":"))
                    if payload.get("trailer") is not None
                    else None,
                    json.dumps(payload.get("characters") or [], ensure_ascii=False, separators=(",", ":")),
                    json.dumps(payload.get("staff") or [], ensure_ascii=False, separators=(",", ":")),
                    json.dumps(payload.get("relations") or [], ensure_ascii=False, separators=(",", ":")),
                    json.dumps(payload.get("recommendations") or [], ensure_ascii=False, separators=(",", ":")),
                    int(time.time()),
                    str(hash(serialized_payload)),
                ),
            )
            # provider_updated_at (updatedAt del proveedor) por separado, para no re-contar
            # los 39 placeholders del INSERT posicional de arriba.
            connection.execute(
                "UPDATE media_details_cache SET provider_updated_at = ? "
                "WHERE media_id = ? AND provider_id = ?",
                (payload.get("updated_at"), media_id, provider_id),
            )
            return media_id

    def persist_details_batch(
        self, provider_id: str, details_list: list, media_type: str = "ANIME"
    ) -> None:
        """Persiste el texto de varios detalles en UNA sola transacción — un solo lock
        de escritura y un commit para todo el lote, en vez de 3 conexiones por item."""
        if not details_list:
            return
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO settings(key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (f"score_format:{provider_id}", details_list[0].score_format),
            )
            for details in details_list:
                self.sync_media_details(
                    provider_id, details.id, details, media_type, _connection=connection
                )

    def get_persisted_media_details(
        self, provider_id: str, media_id: int
    ) -> MediaDetails | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM media_details_cache WHERE provider_id = ? AND media_id = ?",
                (provider_id, media_id),
            ).fetchone()
            if row is None:
                return None
            payload = {
                "id": int(row["external_id"]),
                "updated_at": row["provider_updated_at"],
                "title": row["title"],
                "title_romaji": row["title_romaji"],
                "title_english": row["title_english"],
                "title_native": row["title_native"],
                "synonyms": self._loads_json_or_default(row["synonyms_json"], []),
                "description": row["description"],
                "site_url": row["site_url"] or "",
                "banner_image": row["banner_image_local"] or row["banner_image"],
                "cover_image": row["cover_image_local"] or row["cover_image"],
                "color": row["color"],
                "format": row["format"],
                "media_type": row["media_type"] or "ANIME",
                "status": row["status"],
                "source": row["source"],
                "season": row["season"],
                "season_year": row["season_year"],
                "episodes": row["episodes"],
                "chapters": row["chapters"],
                "volumes": row["volumes"],
                "duration": row["duration"],
                "genres": self._loads_json_or_default(row["genres_json"], []),
                "studios": self._loads_json_or_default(row["studios_json"], []),
                "country": row["country"],
                "average_score": row["average_score"],
                "next_episode": row["next_episode"],
                "next_airing_at": row["next_airing_at"],
                "score_format": row["score_format"] or "POINT_10",
                "canonical_id": media_id,
                "characters": self._loads_json_or_default(row["characters_json"], []),
                "staff": self._loads_json_or_default(row["staff_json"], []),
                "relations": self._loads_json_or_default(row["relations_json"], []),
                "recommendations": self._loads_json_or_default(row["recommendations_json"], []),
                "trailer": self._loads_json_or_default(row["trailer_json"], None),
            }
            try:
                return MediaDetails.model_validate(payload)
            except Exception:
                return None

    def set_media_asset_paths(
        self,
        provider_id: str,
        external_id: str | int,
        *,
        cover_image_local: str | None = None,
        banner_image_local: str | None = None,
    ) -> None:
        media_id = self.canonical_media_id(provider_id, external_id)
        if media_id is None:
            return
        updates: list[str] = []
        parameters: list[object] = []
        if cover_image_local is not None:
            updates.append("cover_image_local = ?")
            parameters.append(cover_image_local)
        if banner_image_local is not None:
            updates.append("banner_image_local = ?")
            parameters.append(banner_image_local)
        if not updates:
            return
        parameters.extend([media_id, provider_id])
        with self.connect() as connection:
            connection.execute(
                f"UPDATE media_details_cache SET {', '.join(updates)} "
                "WHERE media_id = ? AND provider_id = ?",
                parameters,
            )

    def persisted_details_ids(
        self, provider_id: str, external_ids: list[str]
    ) -> set[str]:
        if not external_ids:
            return set()
        placeholders = ",".join("?" for _ in external_ids)
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT external_id FROM media_details_cache "
                f"WHERE provider_id = ? AND external_id IN ({placeholders})",
                (provider_id, *external_ids),
            ).fetchall()
        return {row["external_id"] for row in rows}

    def persisted_details_updated_at(
        self, provider_id: str, external_ids: list[str]
    ) -> dict[str, int | None]:
        """external_id -> provider_updated_at guardado, para detectar detalles obsoletos
        comparándolo con el updatedAt fresco de la lista (refresco por cambio, no por TTL).
        Un id ausente = detalle no persistido todavía."""
        if not external_ids:
            return {}
        placeholders = ",".join("?" for _ in external_ids)
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT external_id, provider_updated_at FROM media_details_cache "
                f"WHERE provider_id = ? AND external_id IN ({placeholders})",
                (provider_id, *external_ids),
            ).fetchall()
        return {row["external_id"]: row["provider_updated_at"] for row in rows}

    def persisted_cover_map(
        self, provider_id: str, external_ids: list[str]
    ) -> dict[str, str]:
        if not external_ids:
            return {}
        placeholders = ",".join("?" for _ in external_ids)
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT external_id, cover_image_local FROM media_details_cache "
                f"WHERE provider_id = ? AND external_id IN ({placeholders}) "
                "AND cover_image_local IS NOT NULL",
                (provider_id, *external_ids),
            ).fetchall()
        return {row["external_id"]: row["cover_image_local"] for row in rows}

    def local_statistics(self, provider: str, account: str) -> StatisticsResponse:
        """Derive statistics from locally synced remote_library_entries (for providers without a stats API)."""
        def _stats_for_type(connection, media_type: str) -> MediaStatistics:
            rows = connection.execute(
                """
                SELECT rle.media_id, rle.status, rle.progress, rle.score, m.format, m.release_year
                FROM remote_library_entries rle
                JOIN media m ON m.id = rle.media_id
                JOIN accounts a ON a.id = rle.account_id
                WHERE a.provider_id = ? AND a.alias = ? AND m.media_type = ?
                """,
                (provider, account, media_type),
            ).fetchall()
            count = len(rows)
            episodes = sum(r["progress"] for r in rows)
            scores = [r["score"] for r in rows if r["score"] is not None]
            mean_score = round(sum(scores) / len(scores), 1) if scores else 0.0
            status_counts: Counter = Counter(r["status"] for r in rows)
            format_counts: Counter = Counter(r["format"] for r in rows if r["format"])
            year_counts: Counter = Counter(str(r["release_year"]) for r in rows if r["release_year"])
            media_ids = [r["media_id"] for r in rows] if rows else []
            if media_ids:
                placeholders = ",".join("?" * len(media_ids))
                genre_rows = connection.execute(
                    f"SELECT genre, COUNT(*) AS cnt FROM media_genres "
                    f"WHERE media_id IN ({placeholders}) GROUP BY genre ORDER BY cnt DESC LIMIT 10",
                    media_ids,
                ).fetchall()
                genres = [StatisticGroup(label=r["genre"], count=r["cnt"]) for r in genre_rows]
            else:
                genres = []
            return MediaStatistics(
                count=count,
                episodes_watched=episodes,
                minutes_watched=0,
                mean_score=mean_score,
                genres=genres,
                statuses=[StatisticGroup(label=s, count=c) for s, c in status_counts.most_common()],
                formats=[StatisticGroup(label=f, count=c) for f, c in format_counts.most_common()],
                release_years=[StatisticGroup(label=y, count=c) for y, c in sorted(year_counts.items(), key=lambda x: -x[1])],
                studios=[],
                countries=[],
            )

        with self.connect() as connection:
            return StatisticsResponse(
                anime=_stats_for_type(connection, "ANIME"),
                manga=_stats_for_type(connection, "MANGA"),
            )

    def get_combined_library(
        self,
        media_type: str = "ANIME",
        preferred_provider: str = "anilist",
        preferred_account: str = "default",
        *,
        only_provider: str | None = None,
        only_account: str | None = None,
    ) -> list[dict]:
        # only_provider/only_account acota a las entradas de ESE proveedor (la vista
        # por proveedor no debe mezclar las bibliotecas de las demás cuentas). Sin
        # ellos une todas las cuentas (vista "combined").
        scope_sql = ""
        scope_params: tuple = ()
        if only_provider is not None:
            scope_sql = " AND a.provider_id = ?"
            scope_params = (only_provider,)
            if only_account is not None:
                scope_sql += " AND a.alias = ?"
                scope_params = (only_provider, only_account)
        with self.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT
                    m.id AS media_id,
                    rle.original_payload,
                    a.provider_id,
                    a.alias AS account_alias,
                    a.is_primary,
                    rle.last_synced_at,
                    le.status AS local_status,
                    le.progress AS local_progress,
                    le.score AS local_score,
                    le.started_at AS local_started_at,
                    le.completed_at AS local_completed_at
                FROM media m
                JOIN remote_library_entries rle ON rle.media_id = m.id
                JOIN accounts a ON a.id = rle.account_id
                LEFT JOIN library_entries le ON le.media_id = m.id
                WHERE m.media_type = ?{scope_sql}
                ORDER BY
                    m.id,
                    CASE
                        WHEN a.provider_id = ? AND a.alias = ? THEN 0
                        WHEN a.provider_id = ? THEN 1
                        WHEN a.is_primary = 1 THEN 2
                        ELSE 3
                    END,
                    rle.last_synced_at DESC
                """,
                (media_type, *scope_params, preferred_provider, preferred_account, preferred_provider),
            ).fetchall()
            if not rows:
                return []

            media_ids = [int(row["media_id"]) for row in rows]
            placeholders = ",".join("?" for _ in media_ids)
            title_rows = connection.execute(
                f"SELECT media_id, language, title FROM media_titles "
                f"WHERE media_id IN ({placeholders}) ORDER BY is_primary DESC, language",
                media_ids,
            ).fetchall()
            genre_rows = connection.execute(
                f"SELECT media_id, genre FROM media_genres WHERE media_id IN ({placeholders})",
                media_ids,
            ).fetchall()
            tag_rows = connection.execute(
                f"SELECT media_id, tag FROM media_tags WHERE media_id IN ({placeholders})",
                media_ids,
            ).fetchall()
            detail_rows = connection.execute(
                f"SELECT media_id, provider_id, external_id, cover_image_local "
                f"FROM media_details_cache WHERE media_id IN ({placeholders}) "
                "AND cover_image_local IS NOT NULL",
                media_ids,
            ).fetchall()

        titles_by_media: dict[int, dict[str, list[str]]] = {}
        for row in title_rows:
            titles_by_media.setdefault(int(row["media_id"]), {}).setdefault(
                row["language"], []
            ).append(row["title"])
        genres_by_media: dict[int, list[str]] = {}
        for row in genre_rows:
            genres_by_media.setdefault(int(row["media_id"]), []).append(row["genre"])
        tags_by_media: dict[int, list[str]] = {}
        for row in tag_rows:
            tags_by_media.setdefault(int(row["media_id"]), []).append(row["tag"])
        local_covers_by_media: dict[tuple[int, str], str] = {}
        for row in detail_rows:
            local_covers_by_media[(int(row["media_id"]), row["provider_id"])] = row["cover_image_local"]

        def payload_date(value: object) -> str | None:
            # MediaItem espera fechas como texto YYYY-MM-DD; ediciones locales
            # antiguas pudieron guardar el dict FuzzyDate ({year, month, day}).
            if isinstance(value, dict):
                year = value.get("year")
                if not year:
                    return None
                return f"{year:04d}-{(value.get('month') or 1):02d}-{(value.get('day') or 1):02d}"
            return value if isinstance(value, str) and value else None

        combined: list[dict] = []
        seen_media_ids: set[int] = set()
        for row in rows:
            media_id = int(row["media_id"])
            if media_id in seen_media_ids:
                continue
            seen_media_ids.add(media_id)

            payload = json.loads(row["original_payload"])
            titles = titles_by_media.get(media_id, {})
            known_titles = {
                payload.get("title"),
                payload.get("title_romaji"),
                payload.get("title_english"),
                payload.get("title_native"),
                *(payload.get("synonyms") or []),
            }
            payload.update(
                {
                    "status": row["local_status"] or payload.get("status"),
                    "progress": row["local_progress"]
                    if row["local_progress"] is not None
                    else payload.get("progress", 0),
                    "score": row["local_score"]
                    if row["local_score"] is not None
                    else payload.get("score"),
                    "started_at": payload_date(
                        row["local_started_at"] or payload.get("started_at")
                    ),
                    "completed_at": payload_date(
                        row["local_completed_at"] or payload.get("completed_at")
                    ),
                    "canonical_id": media_id,
                    "provider": row["provider_id"],
                    "account_alias": row["account_alias"],
                    "title_romaji": payload.get("title_romaji")
                    or next(iter(titles.get("ROMAJI", [])), None),
                    "title_english": payload.get("title_english")
                    or next(iter(titles.get("ENGLISH", [])), None),
                    "title_native": payload.get("title_native")
                    or next(iter(titles.get("NATIVE", [])), None),
                    "genres": genres_by_media.get(media_id, payload.get("genres") or []),
                    "tags": tags_by_media.get(media_id, []),
                    "cover_image": local_covers_by_media.get(
                        (media_id, row["provider_id"]), payload.get("cover_image")
                    ),
                    "synonyms": [
                        *(payload.get("synonyms") or []),
                        *[
                            title
                            for variants in titles.values()
                            for title in variants
                            if title not in known_titles
                        ],
                    ],
                }
            )
            combined.append(payload)
        return combined

    def canonical_media_id(self, provider_id: str, external_id: str | int) -> int | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT media_id FROM external_identities WHERE provider_id = ? AND external_id = ?",
                (provider_id, str(external_id)),
            ).fetchone()
            return int(row["media_id"]) if row else None

    def get_remote_entry(
        self, provider_id: str, alias: str, media_id: int
    ) -> dict | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT rle.id, rle.status, rle.progress, rle.score, rle.original_payload "
                "FROM remote_library_entries rle "
                "JOIN accounts a ON a.id = rle.account_id "
                "WHERE a.provider_id = ? AND a.alias = ? AND rle.media_id = ?",
                (provider_id, alias, media_id),
            ).fetchone()
            return dict(row) if row else None

    def recent_remote_overrides(
        self, provider_id: str, alias: str, within_seconds: int = 180
    ) -> dict[str, dict]:
        # Just-saved edits, keyed by external_id, so a provider with an eventually
        # consistent read API (MyAnimeList) still shows the user's change immediately.
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT ei.external_id, rle.status, rle.progress, rle.score "
                "FROM remote_library_entries rle "
                "JOIN accounts a ON a.id = rle.account_id "
                "JOIN external_identities ei "
                "  ON ei.media_id = rle.media_id AND ei.provider_id = a.provider_id "
                "WHERE a.provider_id = ? AND a.alias = ? "
                "AND rle.last_synced_at >= datetime('now', ?)",
                (provider_id, alias, f"-{int(within_seconds)} seconds"),
            ).fetchall()
            return {row["external_id"]: dict(row) for row in rows}

    def wont_watch_ids(self, provider_id: str) -> set[str]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT external_id FROM wont_watch WHERE provider_id = ?",
                (provider_id,),
            ).fetchall()
            return {row["external_id"] for row in rows}

    def wont_watch_list(self, provider_id: str) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT external_id, title, cover_image FROM wont_watch "
                "WHERE provider_id = ? ORDER BY created_at DESC",
                (provider_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def add_wont_watch(
        self, provider_id: str, external_id: str, title: str | None, cover_image: str | None
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO wont_watch (provider_id, external_id, title, cover_image) "
                "VALUES (?, ?, ?, ?) ON CONFLICT(provider_id, external_id) DO UPDATE SET "
                "title = excluded.title, cover_image = excluded.cover_image",
                (provider_id, str(external_id), title, cover_image),
            )

    def remove_wont_watch(self, provider_id: str, external_id: str) -> None:
        with self.connect() as connection:
            connection.execute(
                "DELETE FROM wont_watch WHERE provider_id = ? AND external_id = ?",
                (provider_id, str(external_id)),
            )

    def external_id_for_account(
        self, media_id: int, provider_id: str
    ) -> str | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT external_id FROM external_identities "
                "WHERE media_id = ? AND provider_id = ?",
                (media_id, provider_id),
            ).fetchone()
            return row["external_id"] if row else None

    def update_remote_library_entry(
        self,
        account_id: int,
        media_id: int,
        *,
        status: str | None = None,
        progress: int | None = None,
        score: float | None = None,
        extra_payload: dict | None = None,
    ) -> None:
        with self.connect() as connection:
            payload = dict(extra_payload or {})
            # Fechas/notas viven en original_payload: fusionarlas mantiene la copia
            # local consistente sin esperar la próxima sincronización del proveedor.
            if extra_payload:
                row = connection.execute(
                    "SELECT original_payload FROM remote_library_entries "
                    "WHERE account_id = ? AND media_id = ?",
                    (account_id, media_id),
                ).fetchone()
                if payload.get("media_type") in {"ANIME", "MANGA"}:
                    connection.execute(
                        "UPDATE media SET media_type = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                        (payload["media_type"], media_id),
                    )
                if row is not None:
                    payload = json.loads(row["original_payload"]) if row["original_payload"] else {}
                    payload.update(extra_payload)
                    connection.execute(
                        "UPDATE remote_library_entries SET original_payload = ? "
                        "WHERE account_id = ? AND media_id = ?",
                        (json.dumps(payload, ensure_ascii=False, separators=(",", ":")), account_id, media_id),
                    )
                else:
                    entry_status = status or payload.get("status") or "PLANNING"
                    entry_progress = progress if progress is not None else int(payload.get("progress") or 0)
                    entry_score = score if score is not None else payload.get("score")
                    payload.update({"status": entry_status, "progress": entry_progress})
                    if entry_score is not None:
                        payload["score"] = entry_score
                    connection.execute(
                        "INSERT INTO remote_library_entries"
                        "(account_id, media_id, status, progress, score, original_payload) "
                        "VALUES (?, ?, ?, ?, ?, ?) "
                        "ON CONFLICT(account_id, media_id) DO UPDATE SET "
                        "status = excluded.status, progress = excluded.progress, "
                        "score = excluded.score, original_payload = excluded.original_payload, "
                        "last_synced_at = CURRENT_TIMESTAMP",
                        (
                            account_id,
                            media_id,
                            entry_status,
                            entry_progress,
                            entry_score,
                            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                        ),
                    )
            updates: list[str] = []
            parameters: list[object] = []
            if status is not None:
                updates.append("status = ?")
                parameters.append(status)
            if progress is not None:
                updates.append("progress = ?")
                parameters.append(progress)
            if score is not None:
                updates.append("score = ?")
                parameters.append(score)
            if not updates:
                return
            parameters.extend([account_id, media_id])
            connection.execute(
                f"UPDATE remote_library_entries SET {', '.join(updates)}, "
                "last_synced_at = CURRENT_TIMESTAMP WHERE account_id = ? AND media_id = ?",
                parameters,
            )
            account = connection.execute(
                "SELECT provider_id, is_primary FROM accounts WHERE id = ?",
                (account_id,),
            ).fetchone()
            primary_provider = connection.execute(
                "SELECT value FROM settings WHERE key = 'primary_provider'"
            ).fetchone()
            if (
                account
                and account["is_primary"]
                and account["provider_id"] == (primary_provider["value"] if primary_provider else "anilist")
            ):
                current = connection.execute(
                    "SELECT status, progress, score FROM remote_library_entries "
                    "WHERE account_id = ? AND media_id = ?",
                    (account_id, media_id),
                ).fetchone()
                if current:
                    connection.execute(
                        "INSERT INTO library_entries(media_id, status, progress, score) "
                        "VALUES (?, ?, ?, ?) ON CONFLICT(media_id) DO UPDATE SET "
                        "status = excluded.status, progress = excluded.progress, "
                        "score = excluded.score, updated_at = CURRENT_TIMESTAMP",
                        (media_id, current["status"], current["progress"], current["score"]),
                    )

    def enrich_provider_library(
        self, provider_id: str, items: list[object]
    ) -> list[object]:
        if not items:
            return []
        external_ids = [str(item.id) for item in items]
        placeholders = ",".join("?" for _ in external_ids)
        with self.connect() as connection:
            rows = connection.execute(
                f"SELECT ei.external_id, ei.media_id, mt.language, mt.title "
                f"FROM external_identities ei JOIN media_titles mt ON mt.media_id = ei.media_id "
                f"WHERE ei.provider_id = ? AND ei.external_id IN ({placeholders}) "
                "ORDER BY mt.is_primary DESC, mt.language",
                (provider_id, *external_ids),
            ).fetchall()
            genre_rows = connection.execute(
                f"SELECT ei.external_id, mg.genre FROM external_identities ei "
                f"JOIN media_genres mg ON mg.media_id = ei.media_id "
                f"WHERE ei.provider_id = ? AND ei.external_id IN ({placeholders})",
                (provider_id, *external_ids),
            ).fetchall()
        grouped: dict[str, dict] = {}
        for row in rows:
            data = grouped.setdefault(
                row["external_id"],
                {"canonical_id": int(row["media_id"]), "titles": {}},
            )
            data["titles"].setdefault(row["language"], []).append(row["title"])
        genres_by_external: dict[str, list[str]] = {}
        for row in genre_rows:
            genres_by_external.setdefault(row["external_id"], []).append(row["genre"])
        tags_by_external = self.enrich_tags(provider_id, items)
        local_covers = self.persisted_cover_map(provider_id, external_ids)
        enriched: list[object] = []
        for item in items:
            data = grouped.get(str(item.id))
            if data is None:
                enriched.append(item)
                continue
            titles = data["titles"]
            known = {
                item.title,
                item.title_romaji,
                item.title_english,
                item.title_native,
                *item.synonyms,
            }
            aliases = [
                title
                for values in titles.values()
                for title in values
                if title not in known
            ]
            enriched.append(
                item.model_copy(
                    update={
                        "synonyms": [*item.synonyms, *aliases],
                        "genres": [
                            *item.genres,
                            *(
                                genre
                                for genre in genres_by_external.get(str(item.id), [])
                                if genre not in item.genres
                            ),
                        ],
                        "tags": [
                            *item.tags,
                            *(
                                tag
                                for tag in tags_by_external.get(str(item.id), [])
                                if tag not in item.tags
                            ),
                        ],
                        "cover_image": local_covers.get(str(item.id), item.cover_image),
                        "canonical_id": data["canonical_id"],
                        "provider": provider_id,
                    }
                )
            )
        return enriched

    def get_match_correction(self, raw_pattern: str, provider_id: str = "anilist") -> int | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT media_id FROM match_corrections WHERE raw_pattern = ? "
                "AND (provider_id = ? OR provider_id IS NULL)",
                (raw_pattern, provider_id),
            ).fetchone()
            return row["media_id"] if row else None

    def get_all_match_corrections(self, provider_id: str = "anilist") -> dict[str, int]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT raw_pattern, media_id FROM match_corrections "
                "WHERE provider_id = ? OR provider_id IS NULL",
                (provider_id,),
            ).fetchall()
            return {row["raw_pattern"]: row["media_id"] for row in rows}

    def get_media_mapping(
        self, provider: str, site_identifier: str
    ) -> tuple[int, int] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT media_id, episode_offset FROM media_mappings "
                "WHERE provider = ? AND site_identifier = ?",
                (provider, site_identifier),
            ).fetchone()
            if row is None:
                return None
            return row["media_id"], row["episode_offset"]

    def set_media_mapping(
        self, provider: str, site_identifier: str, media_id: int, episode_offset: int = 0
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO media_mappings(provider, site_identifier, media_id, episode_offset) "
                "VALUES (?, ?, ?, ?) "
                "ON CONFLICT(provider, site_identifier) DO UPDATE SET "
                "media_id = excluded.media_id, episode_offset = excluded.episode_offset",
                (provider, site_identifier, media_id, episode_offset),
            )

    def set_match_correction(
        self, raw_pattern: str, media_id: int, provider_id: str = "anilist"
    ) -> None:
        canonical_media_id = self.canonical_media_id(provider_id, media_id)
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO match_corrections"
                "(raw_pattern, media_id, provider_id, canonical_media_id) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(raw_pattern) DO UPDATE SET media_id = excluded.media_id, "
                "provider_id = excluded.provider_id, "
                "canonical_media_id = excluded.canonical_media_id",
                (raw_pattern, media_id, provider_id, canonical_media_id),
            )

    def delete_match_correction(self, raw_pattern: str) -> None:
        with self.connect() as connection:
            connection.execute("DELETE FROM match_corrections WHERE raw_pattern = ?", (raw_pattern,))

    def insert_playback_event(
        self,
        source: str,
        raw_title: str,
        anime_title: str | None,
        episode: int | None,
        status: str = "pending",
        provider_id: str | None = None,
        account_id: int | None = None,
        canonical_media_id: int | None = None,
    ) -> int:
        with self.connect() as connection:
            cursor = connection.execute(
                "INSERT INTO playback_events "
                "(source, raw_title, anime_title, episode, status, provider_id, account_id, "
                "canonical_media_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    source,
                    raw_title,
                    anime_title,
                    episode,
                    status,
                    provider_id,
                    account_id,
                    canonical_media_id,
                ),
            )
            return int(cursor.lastrowid)

    def update_playback_event(
        self,
        event_id: int,
        status: str,
        media_id: int | None = None,
        progress_before: int | None = None,
        progress_after: int | None = None,
        provider_id: str | None = None,
        account_id: int | None = None,
        canonical_media_id: int | None = None,
        error_message: str | None = None,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                "UPDATE playback_events SET status = ?, media_id = COALESCE(?, media_id), "
                "progress_before = COALESCE(?, progress_before), "
                "progress_after = COALESCE(?, progress_after), "
                "provider_id = COALESCE(?, provider_id), account_id = COALESCE(?, account_id), "
                "canonical_media_id = COALESCE(?, canonical_media_id), "
                "error_message = COALESCE(?, error_message) "
                "WHERE id = ?",
                (
                    status,
                    media_id,
                    progress_before,
                    progress_after,
                    provider_id,
                    account_id,
                    canonical_media_id,
                    error_message,
                    event_id,
                ),
            )

    def get_last_playback_event(self) -> dict | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM playback_events ORDER BY detected_at DESC, id DESC LIMIT 1"
            ).fetchone()
            return dict(row) if row else None

    def get_playback_event(self, event_id: int) -> dict | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM playback_events WHERE id = ?", (event_id,)
            ).fetchone()
            return dict(row) if row else None

    def get_recent_matching_playback_event(
        self,
        source: str,
        raw_title: str,
        episode: int | None,
        within_seconds: int,
    ) -> dict | None:
        modifier = f"-{max(0, within_seconds)} seconds"
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM playback_events "
                "WHERE source = ? AND raw_title = ? AND episode IS ? "
                "AND detected_at >= datetime('now', ?) "
                "ORDER BY detected_at DESC, id DESC LIMIT 1",
                (source, raw_title, episode, modifier),
            ).fetchone()
            return dict(row) if row else None

    def get_recent_playback_events(
        self,
        limit: int = 50,
        status: str | None = None,
        source: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> list[dict]:
        clauses: list[str] = []
        parameters: list[str | int] = []
        if status:
            clauses.append("status = ?")
            parameters.append(status)
        if source:
            clauses.append("source = ?")
            parameters.append(source)
        if date_from:
            clauses.append("date(detected_at) >= date(?)")
            parameters.append(date_from)
        if date_to:
            clauses.append("date(detected_at) <= date(?)")
            parameters.append(date_to)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        parameters.append(limit)
        with self.connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM playback_events{where} "
                "ORDER BY detected_at DESC, id DESC LIMIT ?",
                parameters,
            ).fetchall()
            return [dict(row) for row in rows]

    def clear_playback_events(self) -> None:
        with self.connect() as connection:
            connection.execute("DELETE FROM playback_events")

    def prune_playback_events(self, retention_days: int) -> int:
        modifier = f"-{max(1, retention_days)} days"
        with self.connect() as connection:
            cursor = connection.execute(
                "DELETE FROM playback_events WHERE detected_at < datetime('now', ?)",
                (modifier,),
            )
            return cursor.rowcount

    def add_media_tag(self, media_id: int, tag: str) -> None:
        with self.connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO media_tags(media_id, tag) VALUES (?, ?)",
                (media_id, tag.strip().casefold()),
            )

    def remove_media_tag(self, media_id: int, tag: str) -> None:
        with self.connect() as connection:
            connection.execute(
                "DELETE FROM media_tags WHERE media_id = ? AND tag = ?",
                (media_id, tag.strip().casefold()),
            )

    def get_media_tags(self, media_id: int) -> list[str]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT tag FROM media_tags WHERE media_id = ? ORDER BY tag",
                (media_id,),
            ).fetchall()
            return [row["tag"] for row in rows]

    def get_all_tags(self) -> list[str]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT DISTINCT tag FROM media_tags ORDER BY tag"
            ).fetchall()
            return [row["tag"] for row in rows]

    def enrich_tags(
        self, provider_id: str, items: list[object]
    ) -> dict[str, list[str]]:
        if not items:
            return {}
        external_ids = [str(item.id) for item in items]
        placeholders = ",".join("?" for _ in external_ids)
        with self.connect() as connection:
            rows = connection.execute(
                f"SELECT ei.external_id, mt.tag FROM external_identities ei "
                f"JOIN media_tags mt ON mt.media_id = ei.media_id "
                f"WHERE ei.provider_id = ? AND ei.external_id IN ({placeholders})",
                (provider_id, *external_ids),
            ).fetchall()
        tags_by_external: dict[str, list[str]] = {}
        for row in rows:
            tags_by_external.setdefault(row["external_id"], []).append(row["tag"])
        return tags_by_external

    def record_conflict(
        self,
        media_id: int,
        account_id: int,
        field: str,
        local_value: str | None,
        remote_value: str | None,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> int | None:
        if connection is None:
            with self.connect() as own_connection:
                return self.record_conflict(
                    media_id,
                    account_id,
                    field,
                    local_value,
                    remote_value,
                    connection=own_connection,
                )
        existing = connection.execute(
            "SELECT id FROM conflicts WHERE media_id = ? AND account_id = ? "
            "AND field = ? AND status = 'pending'",
            (media_id, account_id, field),
        ).fetchone()
        if existing:
            connection.execute(
                "UPDATE conflicts SET local_value = ?, remote_value = ?, "
                "detected_at = CURRENT_TIMESTAMP WHERE id = ?",
                (local_value, remote_value, existing["id"]),
            )
            return int(existing["id"])
        cursor = connection.execute(
            "INSERT INTO conflicts(media_id, account_id, field, local_value, "
            "remote_value, status) VALUES (?, ?, ?, ?, ?, 'pending')",
            (media_id, account_id, field, local_value, remote_value),
        )
        return int(cursor.lastrowid)

    def get_conflicts(
        self, status: str = "pending", account_id: int | None = None
    ) -> list[dict]:
        clauses: list[str] = ["c.status = ?"]
        parameters: list[str | int] = [status]
        if account_id is not None:
            clauses.append("c.account_id = ?")
            parameters.append(account_id)
        where = " AND ".join(clauses)
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT c.id, c.media_id, c.account_id, a.provider_id AS provider, "
                "a.alias, c.field, c.local_value, c.remote_value, c.detected_at, "
                "c.status, c.resolution_value, "
                "COALESCE((SELECT title FROM media_titles WHERE media_id = c.media_id "
                "ORDER BY is_primary DESC, language LIMIT 1), CAST(c.media_id AS TEXT)) "
                "AS title FROM conflicts c JOIN accounts a ON a.id = c.account_id "
                f"WHERE {where} ORDER BY c.detected_at DESC",
                parameters,
            ).fetchall()
            return [dict(row) for row in rows]

    def get_conflicts_by_id(self, conflict_id: int) -> dict | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT c.id, c.media_id, c.account_id, a.provider_id AS provider, "
                "a.alias, c.field, c.local_value, c.remote_value, c.detected_at, "
                "c.status, c.resolution_value, "
                "COALESCE((SELECT title FROM media_titles WHERE media_id = c.media_id "
                "ORDER BY is_primary DESC, language LIMIT 1), CAST(c.media_id AS TEXT)) "
                "AS title FROM conflicts c JOIN accounts a ON a.id = c.account_id "
                "WHERE c.id = ?",
                (conflict_id,),
            ).fetchone()
            return dict(row) if row else None

    def resolve_conflict(
        self,
        conflict_id: int,
        resolution: str,
        resolution_value: str | None = None,
    ) -> bool:
        with self.connect() as connection:
            cursor = connection.execute(
                "UPDATE conflicts SET status = ?, resolution_value = ?, "
                "resolved_at = CURRENT_TIMESTAMP WHERE id = ? AND status = 'pending'",
                (resolution, resolution_value, conflict_id),
            )
            return cursor.rowcount == 1

    def dismiss_conflict(self, conflict_id: int) -> bool:
        return self.resolve_conflict(conflict_id, "dismissed")

    def update_account_progress(
        self, account_id: int, media_id: int, progress: int
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                "UPDATE remote_library_entries SET progress = ? "
                "WHERE account_id = ? AND media_id = ?",
                (progress, account_id, media_id),
            )
            account = connection.execute(
                "SELECT provider_id, is_primary FROM accounts WHERE id = ?",
                (account_id,),
            ).fetchone()
            primary_provider = connection.execute(
                "SELECT value FROM settings WHERE key = 'primary_provider'"
            ).fetchone()
            if (
                account
                and account["is_primary"]
                and account["provider_id"] == (primary_provider["value"] if primary_provider else "anilist")
            ):
                connection.execute(
                    "UPDATE library_entries SET progress = ?, updated_at = CURRENT_TIMESTAMP "
                    "WHERE media_id = ?",
                    (progress, media_id),
                )

    def update_account_status(
        self, account_id: int, media_id: int, status: str
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                "UPDATE remote_library_entries SET status = ? "
                "WHERE account_id = ? AND media_id = ?",
                (status, account_id, media_id),
            )
            account = connection.execute(
                "SELECT provider_id, is_primary FROM accounts WHERE id = ?",
                (account_id,),
            ).fetchone()
            primary_provider = connection.execute(
                "SELECT value FROM settings WHERE key = 'primary_provider'"
            ).fetchone()
            if (
                account
                and account["is_primary"]
                and account["provider_id"] == (primary_provider["value"] if primary_provider else "anilist")
            ):
                connection.execute(
                    "UPDATE library_entries SET status = ?, updated_at = CURRENT_TIMESTAMP "
                    "WHERE media_id = ?",
                    (status, media_id),
                )

    def list_torrent_sources(self) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT id, name, url, enabled, kind FROM torrent_sources ORDER BY id"
            ).fetchall()
            return [dict(row) for row in rows]

    def add_torrent_source(self, name: str, url: str, enabled: bool = True, kind: str = "release") -> int:
        with self.connect() as connection:
            cursor = connection.execute(
                "INSERT INTO torrent_sources(name, url, enabled, kind, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (name, url, 1 if enabled else 0, kind, int(time.time())),
            )
            return int(cursor.lastrowid)

    def update_torrent_source(self, source_id: int, name: str, url: str, enabled: bool, kind: str = "release") -> None:
        with self.connect() as connection:
            connection.execute(
                "UPDATE torrent_sources SET name = ?, url = ?, enabled = ?, kind = ? WHERE id = ?",
                (name, url, 1 if enabled else 0, kind, source_id),
            )

    def delete_torrent_source(self, source_id: int) -> None:
        with self.connect() as connection:
            connection.execute("DELETE FROM torrent_sources WHERE id = ?", (source_id,))

    def list_torrent_filters(self) -> list[dict]:
        with self.connect() as connection:
            filters = connection.execute(
                "SELECT id, name, action, match, scope, enabled FROM torrent_filters ORDER BY id"
            ).fetchall()
            result = []
            for f in filters:
                conds = connection.execute(
                    "SELECT element, operator, value FROM torrent_filter_conditions WHERE filter_id = ?",
                    (f["id"],),
                ).fetchall()
                anime = connection.execute(
                    "SELECT media_id FROM torrent_filter_anime WHERE filter_id = ?", (f["id"],)
                ).fetchall()
                result.append({
                    "id": f["id"], "name": f["name"], "action": f["action"],
                    "match": f["match"], "scope": f["scope"], "enabled": bool(f["enabled"]),
                    "conditions": [dict(c) for c in conds],
                    "anime_ids": [a["media_id"] for a in anime],
                })
            return result

    def add_torrent_filter(
        self, name: str, action: str, match: str, scope: str,
        enabled: bool, conditions: list[dict], anime_ids: list[int],
    ) -> int:
        with self.connect() as connection:
            cur = connection.execute(
                "INSERT INTO torrent_filters(name, action, match, scope, enabled, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (name, action, match, scope, 1 if enabled else 0, int(time.time())),
            )
            fid = int(cur.lastrowid)
            self._write_filter_children(connection, fid, conditions, anime_ids)
            return fid

    def update_torrent_filter(
        self, filter_id: int, name: str, action: str, match: str, scope: str,
        enabled: bool, conditions: list[dict], anime_ids: list[int],
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                "UPDATE torrent_filters SET name=?, action=?, match=?, scope=?, enabled=? WHERE id=?",
                (name, action, match, scope, 1 if enabled else 0, filter_id),
            )
            connection.execute("DELETE FROM torrent_filter_conditions WHERE filter_id=?", (filter_id,))
            connection.execute("DELETE FROM torrent_filter_anime WHERE filter_id=?", (filter_id,))
            self._write_filter_children(connection, filter_id, conditions, anime_ids)

    @staticmethod
    def _write_filter_children(
        connection: sqlite3.Connection, filter_id: int,
        conditions: list[dict], anime_ids: list[int],
    ) -> None:
        connection.executemany(
            "INSERT INTO torrent_filter_conditions(filter_id, element, operator, value) "
            "VALUES (?, ?, ?, ?)",
            [(filter_id, c["element"], c["operator"], c["value"]) for c in conditions],
        )
        connection.executemany(
            "INSERT OR IGNORE INTO torrent_filter_anime(filter_id, media_id) VALUES (?, ?)",
            [(filter_id, mid) for mid in anime_ids],
        )

    def delete_torrent_filter(self, filter_id: int) -> None:
        with self.connect() as connection:
            connection.execute("DELETE FROM torrent_filters WHERE id = ?", (filter_id,))

    def list_seen_signatures(self) -> set[str]:
        with self.connect() as connection:
            rows = connection.execute("SELECT signature FROM torrent_seen").fetchall()
            return {row["signature"] for row in rows}

    def list_discarded_signatures(self) -> set[str]:
        # Una sola consulta: iterar torrent_seen con is_torrent_discarded() por firma
        # era O(n) queries por refresco de feed y torrent_seen crece sin límite.
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT signature FROM torrent_seen WHERE discarded = 1"
            ).fetchall()
            return {row["signature"] for row in rows}

    def is_torrent_discarded(self, signature: str) -> bool:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT discarded FROM torrent_seen WHERE signature = ?", (signature,)
            ).fetchone()
            return bool(row["discarded"]) if row else False

    def mark_torrent_seen(self, signature: str, media_id: int | None) -> None:
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO torrent_seen(signature, media_id, seen_at) VALUES (?, ?, ?) "
                "ON CONFLICT(signature) DO NOTHING",
                (signature, media_id, int(time.time())),
            )

    def set_torrent_discarded(self, signature: str, media_id: int | None) -> None:
        self._set_torrent_flag(signature, media_id, "discarded")

    def set_torrent_downloaded(self, signature: str, media_id: int | None) -> None:
        self._set_torrent_flag(signature, media_id, "downloaded")

    def _set_torrent_flag(self, signature: str, media_id: int | None, column: str) -> None:
        with self.connect() as connection:
            connection.execute(
                f"INSERT INTO torrent_seen(signature, media_id, {column}, seen_at) "
                f"VALUES (?, ?, 1, ?) "
                f"ON CONFLICT(signature) DO UPDATE SET {column} = 1",
                (signature, media_id, int(time.time())),
            )

    def primary_account(self) -> tuple[str, str] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT provider_id AS provider, alias FROM accounts "
                "ORDER BY is_primary DESC, id LIMIT 1"
            ).fetchone()
            return (row["provider"], row["alias"]) if row else None
