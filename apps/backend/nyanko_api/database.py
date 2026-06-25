import json
import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from .normalizer import normalize_title


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
    sync_direction TEXT NOT NULL DEFAULT 'bidirectional',
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
CREATE TABLE IF NOT EXISTS association_candidates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_identity_id INTEGER NOT NULL REFERENCES external_identities(id) ON DELETE CASCADE,
    candidate_media_id INTEGER NOT NULL REFERENCES media(id) ON DELETE CASCADE,
    confidence REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resolved_at TEXT,
    UNIQUE(source_identity_id, candidate_media_id)
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
"""

CANONICAL_SCHEMA_VERSION = 6
CACHE_RESOURCE_LIMITS = {"media:": 100, "season:": 24}


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
            self._add_column(connection, "media", "release_year", "INTEGER")
            self._add_column(connection, "media", "chapter_count", "INTEGER")
            self._add_column(connection, "media", "volume_count", "INTEGER")
            self._add_column(connection, "media_titles", "normalized_title", "TEXT")
            self._backfill_normalized_titles(connection)
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_media_titles_normalized "
                "ON media_titles(normalized_title)"
            )
            connection.execute(
                "INSERT OR IGNORE INTO schema_migrations(version) VALUES (?)",
                (CANONICAL_SCHEMA_VERSION,),
            )
            self.ensure_provider("anilist", "AniList", connection=connection)

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

    @classmethod
    def _find_canonical_match(
        cls,
        connection: sqlite3.Connection,
        provider_id: str,
        payload: dict,
        media_type: str = "ANIME",
    ) -> tuple[tuple[int, float] | None, list[tuple[float, int]]]:
        normalized_titles = {
            normalize_title(title).casefold()
            for _, title, _ in cls._payload_titles(payload)
            if normalize_title(title)
        }
        if not normalized_titles:
            return None, []
        placeholders = ",".join("?" for _ in normalized_titles)
        rows = connection.execute(
            f"SELECT DISTINCT m.id, m.format, m.episode_count, m.chapter_count, "
            f"m.volume_count, m.release_year "
            f"FROM media m JOIN media_titles mt ON mt.media_id = m.id "
            f"WHERE mt.normalized_title IN ({placeholders}) "
            "AND m.media_type = ? "
            "AND NOT EXISTS (SELECT 1 FROM external_identities ei "
            "WHERE ei.media_id = m.id AND ei.provider_id = ?)",
            (*normalized_titles, media_type, provider_id),
        ).fetchall()
        scored: list[tuple[float, int]] = []
        for row in rows:
            score = 0.8
            if media_type == "MANGA":
                comparisons = (
                    (payload.get("year"), row["release_year"], 0.1, 0.25),
                    (payload.get("chapters"), row["chapter_count"], 0.1, 0.2),
                    (payload.get("volumes"), row["volume_count"], 0.05, 0.1),
                    (payload.get("format"), row["format"], 0.05, 0.1),
                )
            else:
                comparisons = (
                    (payload.get("year"), row["release_year"], 0.1, 0.25),
                    (payload.get("episodes"), row["episode_count"], 0.1, 0.2),
                    (payload.get("format"), row["format"], 0.05, 0.1),
                )
            for incoming, existing, bonus, penalty in comparisons:
                if incoming is not None and existing is not None:
                    score += bonus if incoming == existing else -penalty
            scored.append((max(0.0, min(1.0, score)), int(row["id"])))
        scored.sort(reverse=True)
        if not scored or scored[0][0] < 0.9:
            return None, scored
        if len(scored) > 1 and scored[0][0] - scored[1][0] < 0.05:
            return None, scored
        return (scored[0][1], scored[0][0]), scored

    @staticmethod
    def _add_column(
        connection: sqlite3.Connection, table: str, column: str, definition: str
    ) -> None:
        columns = {
            row["name"] for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if column not in columns:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

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
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
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

    def get_cache(self, key: str):
        record = self.get_cache_record(key)
        return record.payload if record is not None and not record.stale else None

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
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT id, provider_id AS provider, alias, sync_direction, is_primary, "
                "last_synced_at FROM accounts ORDER BY provider_id, is_primary DESC, alias"
            ).fetchall()
            return [dict(row) for row in rows]

    def update_account(
        self,
        account_id: int,
        *,
        sync_direction: str | None = None,
        is_primary: bool | None = None,
    ) -> dict | None:
        with self.connect() as connection:
            current = connection.execute(
                "SELECT * FROM accounts WHERE id = ?", (account_id,)
            ).fetchone()
            if current is None:
                return None
            if sync_direction is not None:
                connection.execute(
                    "UPDATE accounts SET sync_direction = ? WHERE id = ?",
                    (sync_direction, account_id),
                )
            if is_primary:
                connection.execute(
                    "UPDATE accounts SET is_primary = 0 WHERE provider_id = ?",
                    (current["provider_id"],),
                )
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
                "SELECT id, provider_id AS provider, alias, sync_direction, is_primary, "
                "last_synced_at FROM accounts WHERE id = ?",
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
                    matched, candidates = self._find_canonical_match(
                        connection, provider_id, payload, media_type=media_type
                    )
                    if matched:
                        media_id, confidence = matched
                    else:
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
                        confidence = 1.0
                    identity_cursor = connection.execute(
                        "INSERT INTO external_identities"
                        "(media_id, provider_id, external_id, url, confidence) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (
                            media_id,
                            provider_id,
                            external_id,
                            payload.get("site_url"),
                            confidence,
                        ),
                    )
                    if matched is None:
                        connection.executemany(
                            "INSERT OR IGNORE INTO association_candidates"
                            "(source_identity_id, candidate_media_id, confidence) "
                            "VALUES (?, ?, ?)",
                            (
                                (int(identity_cursor.lastrowid), candidate_id, score)
                                for score, candidate_id in candidates
                                if score >= 0.5
                            ),
                        )
                connection.execute(
                    "UPDATE media SET episode_count = COALESCE(?, episode_count), "
                    "chapter_count = COALESCE(?, chapter_count), "
                    "volume_count = COALESCE(?, volume_count), "
                    "format = COALESCE(?, format), release_year = COALESCE(?, release_year), "
                    "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (
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
                    connection.execute(
                        "INSERT OR IGNORE INTO media_titles"
                        "(media_id, language, title, normalized_title, is_primary) "
                        "VALUES (?, ?, ?, ?, ?)",
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
                        "INSERT INTO library_entries(media_id, status, progress) "
                        "VALUES (?, ?, ?) ON CONFLICT(media_id) DO UPDATE SET "
                        "status = excluded.status, progress = excluded.progress, "
                        "updated_at = CURRENT_TIMESTAMP",
                        (media_id, payload["status"], payload["progress"]),
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
    ) -> int | None:
        payload = details.model_dump(mode="json")
        with self.connect() as connection:
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
                "UPDATE media SET format = ?, episode_count = ?, chapter_count = ?, "
                "volume_count = ?, release_year = COALESCE(?, release_year), "
                "updated_at = CURRENT_TIMESTAMP "
                "WHERE id = ?",
                (
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
            return media_id

    def canonical_media_id(self, provider_id: str, external_id: str | int) -> int | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT media_id FROM external_identities WHERE provider_id = ? AND external_id = ?",
                (provider_id, str(external_id)),
            ).fetchone()
            return int(row["media_id"]) if row else None

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
    ) -> None:
        with self.connect() as connection:
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
                "updated_at = CURRENT_TIMESTAMP WHERE account_id = ? AND media_id = ?",
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
                local_updates = updates[:]
                local_parameters = parameters[:-2]
                local_parameters.extend([media_id])
                connection.execute(
                    f"UPDATE library_entries SET {', '.join(local_updates)}, "
                    "updated_at = CURRENT_TIMESTAMP WHERE media_id = ?",
                    local_parameters,
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
                        "canonical_id": data["canonical_id"],
                        "provider": provider_id,
                    }
                )
            )
        return enriched

    def get_association_candidates(self, status: str = "pending") -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT ac.id, ac.source_identity_id, ei.provider_id AS source_provider, "
                "ei.external_id AS source_external_id, ac.candidate_media_id, "
                "ac.confidence, ac.status, "
                "COALESCE((SELECT title FROM media_titles WHERE media_id = ei.media_id "
                "ORDER BY is_primary DESC, language LIMIT 1), ei.external_id) AS source_title, "
                "COALESCE((SELECT title FROM media_titles WHERE media_id = ac.candidate_media_id "
                "ORDER BY is_primary DESC, language LIMIT 1), CAST(ac.candidate_media_id AS TEXT)) "
                "AS candidate_title FROM association_candidates ac "
                "JOIN external_identities ei ON ei.id = ac.source_identity_id "
                "WHERE ac.status = ? ORDER BY ac.confidence DESC, ac.id",
                (status,),
            ).fetchall()
            return [dict(row) for row in rows]

    def dismiss_association_candidate(self, candidate_id: int) -> bool:
        with self.connect() as connection:
            cursor = connection.execute(
                "UPDATE association_candidates SET status = 'dismissed', "
                "resolved_at = CURRENT_TIMESTAMP WHERE id = ? AND status = 'pending'",
                (candidate_id,),
            )
            return cursor.rowcount == 1

    def resolve_association_candidate(self, candidate_id: int) -> int:
        with self.connect() as connection:
            candidate = connection.execute(
                "SELECT ac.*, ei.media_id AS source_media_id FROM association_candidates ac "
                "JOIN external_identities ei ON ei.id = ac.source_identity_id "
                "WHERE ac.id = ? AND ac.status = 'pending'",
                (candidate_id,),
            ).fetchone()
            if candidate is None:
                raise ValueError("Association candidate not found or already resolved")
            source_media_id = int(candidate["source_media_id"])
            target_media_id = int(candidate["candidate_media_id"])
            if source_media_id == target_media_id:
                raise ValueError("Identity is already associated with this work")
            identity_conflict = connection.execute(
                "SELECT 1 FROM external_identities source JOIN external_identities target "
                "ON target.provider_id = source.provider_id WHERE source.media_id = ? "
                "AND target.media_id = ? LIMIT 1",
                (source_media_id, target_media_id),
            ).fetchone()
            remote_conflict = connection.execute(
                "SELECT 1 FROM remote_library_entries source "
                "JOIN remote_library_entries target ON target.account_id = source.account_id "
                "WHERE source.media_id = ? AND target.media_id = ? LIMIT 1",
                (source_media_id, target_media_id),
            ).fetchone()
            local_conflict = connection.execute(
                "SELECT 1 FROM library_entries source JOIN library_entries target "
                "WHERE source.media_id = ? AND target.media_id = ? LIMIT 1",
                (source_media_id, target_media_id),
            ).fetchone()
            if identity_conflict or remote_conflict or local_conflict:
                raise ValueError("Association has incompatible library entries")
            connection.execute(
                "INSERT OR IGNORE INTO media_titles"
                "(media_id, language, title, normalized_title, is_primary) "
                "SELECT ?, language, title, normalized_title, 0 FROM media_titles "
                "WHERE media_id = ?",
                (target_media_id, source_media_id),
            )
            connection.execute(
                "INSERT OR IGNORE INTO media_seasons(media_id, season_number, label, year) "
                "SELECT ?, season_number, label, year FROM media_seasons WHERE media_id = ?",
                (target_media_id, source_media_id),
            )
            connection.execute(
                "INSERT OR IGNORE INTO episodes"
                "(media_id, episode_number, episode_type, title, duration_minutes) "
                "SELECT ?, episode_number, episode_type, title, duration_minutes FROM episodes "
                "WHERE media_id = ?",
                (target_media_id, source_media_id),
            )
            connection.execute(
                "UPDATE remote_library_entries SET media_id = ? WHERE media_id = ?",
                (target_media_id, source_media_id),
            )
            connection.execute(
                "UPDATE library_entries SET media_id = ? WHERE media_id = ?",
                (target_media_id, source_media_id),
            )
            connection.execute(
                "UPDATE playback_events SET canonical_media_id = ? WHERE canonical_media_id = ?",
                (target_media_id, source_media_id),
            )
            connection.execute(
                "UPDATE match_corrections SET canonical_media_id = ? WHERE canonical_media_id = ?",
                (target_media_id, source_media_id),
            )
            connection.execute(
                "UPDATE external_identities SET media_id = ? WHERE media_id = ?",
                (target_media_id, source_media_id),
            )
            connection.execute(
                "UPDATE external_identities SET confidence = 1.0 WHERE id = ?",
                (candidate["source_identity_id"],),
            )
            connection.execute(
                "UPDATE association_candidates SET status = CASE WHEN id = ? "
                "THEN 'resolved' ELSE 'dismissed' END, resolved_at = CURRENT_TIMESTAMP "
                "WHERE source_identity_id = ? AND status = 'pending'",
                (candidate_id, candidate["source_identity_id"]),
            )
            connection.execute("DELETE FROM media WHERE id = ?", (source_media_id,))
            return target_media_id

    def get_linked_identities(self) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT ei.id AS identity_id, ei.media_id, ei.provider_id AS provider, "
                "ei.external_id, ei.confidence, counts.identity_count, "
                "COALESCE((SELECT title FROM media_titles WHERE media_id = ei.media_id "
                "ORDER BY is_primary DESC, language LIMIT 1), ei.external_id) AS title "
                "FROM external_identities ei JOIN (SELECT media_id, COUNT(*) AS identity_count "
                "FROM external_identities GROUP BY media_id HAVING COUNT(*) > 1) counts "
                "ON counts.media_id = ei.media_id ORDER BY ei.media_id, ei.provider_id"
            ).fetchall()
            return [dict(row) for row in rows]

    def separate_external_identity(self, identity_id: int) -> int:
        with self.connect() as connection:
            identity = connection.execute(
                "SELECT * FROM external_identities WHERE id = ?", (identity_id,)
            ).fetchone()
            if identity is None:
                raise ValueError("External identity not found")
            source_media_id = int(identity["media_id"])
            count = connection.execute(
                "SELECT COUNT(*) FROM external_identities WHERE media_id = ?",
                (source_media_id,),
            ).fetchone()[0]
            if count < 2:
                raise ValueError("External identity is not linked to another provider")
            media = connection.execute(
                "SELECT media_type, format, episode_count, release_year FROM media WHERE id = ?",
                (source_media_id,),
            ).fetchone()
            cursor = connection.execute(
                "INSERT INTO media(media_type, format, episode_count, release_year) "
                "VALUES (?, ?, ?, ?)",
                tuple(media),
            )
            target_media_id = int(cursor.lastrowid)
            connection.execute(
                "INSERT INTO media_titles(media_id, language, title, normalized_title, is_primary) "
                "SELECT ?, language, title, normalized_title, is_primary FROM media_titles "
                "WHERE media_id = ?",
                (target_media_id, source_media_id),
            )
            connection.execute(
                "INSERT INTO media_seasons(media_id, season_number, label, year) "
                "SELECT ?, season_number, label, year FROM media_seasons WHERE media_id = ?",
                (target_media_id, source_media_id),
            )
            connection.execute(
                "INSERT INTO episodes(media_id, episode_number, episode_type, title, duration_minutes) "
                "SELECT ?, episode_number, episode_type, title, duration_minutes FROM episodes "
                "WHERE media_id = ?",
                (target_media_id, source_media_id),
            )
            provider_id = identity["provider_id"]
            connection.execute(
                "UPDATE remote_library_entries SET media_id = ? WHERE media_id = ? "
                "AND account_id IN (SELECT id FROM accounts WHERE provider_id = ?)",
                (target_media_id, source_media_id, provider_id),
            )
            primary_provider = connection.execute(
                "SELECT value FROM settings WHERE key = 'primary_provider'"
            ).fetchone()
            if provider_id == (primary_provider["value"] if primary_provider else "anilist"):
                connection.execute(
                    "UPDATE library_entries SET media_id = ? WHERE media_id = ?",
                    (target_media_id, source_media_id),
                )
            connection.execute(
                "UPDATE playback_events SET canonical_media_id = ? "
                "WHERE canonical_media_id = ? AND provider_id = ?",
                (target_media_id, source_media_id, provider_id),
            )
            connection.execute(
                "UPDATE match_corrections SET canonical_media_id = ? "
                "WHERE canonical_media_id = ? AND provider_id = ?",
                (target_media_id, source_media_id, provider_id),
            )
            connection.execute(
                "UPDATE external_identities SET media_id = ?, confidence = 1.0 WHERE id = ?",
                (target_media_id, identity_id),
            )
            connection.execute(
                "UPDATE association_candidates SET status = 'separated', "
                "resolved_at = CURRENT_TIMESTAMP WHERE source_identity_id = ?",
                (identity_id,),
            )
            return target_media_id

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
