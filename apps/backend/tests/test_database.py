import asyncio
import sqlite3
from contextlib import contextmanager
from pathlib import Path

import pytest
from pydantic import BaseModel

from nyanko_api.database import Database
from nyanko_api.main import _cache_refreshes, cached_list, cached_value
from nyanko_api.models import MediaItem


class _SampleValue(BaseModel):
    value: str


def memory_database(monkeypatch) -> Database:
    database = Database(Path(":memory:"))
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row

    @contextmanager
    def connect():
        yield connection
        connection.commit()

    monkeypatch.setattr(database, "connect", connect)
    database.initialize()
    return database


def test_initialize_migrates_legacy_cache_table(monkeypatch):
    database = Database(Path(":memory:"))
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute(
        "CREATE TABLE cache (key TEXT PRIMARY KEY, payload TEXT NOT NULL, expires_at INTEGER NOT NULL)"
    )

    @contextmanager
    def connect():
        yield connection
        connection.commit()

    monkeypatch.setattr(database, "connect", connect)
    database.initialize()
    columns = {row["name"] for row in connection.execute("PRAGMA table_info(cache)")}

    assert {"created_at", "updated_at", "accessed_at"}.issubset(columns)


def test_initialize_creates_canonical_provider_schema(monkeypatch):
    database = memory_database(monkeypatch)

    with database.connect() as connection:
        tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        version = connection.execute(
            "SELECT MAX(version) AS version FROM schema_migrations"
        ).fetchone()["version"]
        provider = connection.execute(
            "SELECT display_name FROM providers WHERE id = 'anilist'"
        ).fetchone()

    assert {
        "accounts",
        "media",
        "media_titles",
        "external_identities",
        "library_entries",
        "remote_library_entries",
        "media_seasons",
        "episodes",
        "extension_clients",
    }.issubset(tables)
    assert version == 7
    assert provider["display_name"] == "AniList"


def test_accounts_are_collapsed_to_default_alias(monkeypatch):
    database = memory_database(monkeypatch)
    database.ensure_provider("anilist", "AniList")
    first_id = database.ensure_account("anilist", "first")
    second_id = database.ensure_account("anilist", "second")

    accounts = database.get_accounts()

    assert first_id == second_id
    assert len(accounts) == 1
    assert accounts[0]["alias"] == "default"


def test_extension_token_lifecycle(monkeypatch):
    database = memory_database(monkeypatch)
    monkeypatch.setattr("nyanko_api.database.time.time", lambda: 100)
    client_id = database.create_extension_client("Firefox", "old-hash", 200)

    assert database.validate_extension_token("old-hash") is True
    assert database.rotate_extension_token("old-hash", "new-hash", 300)
    assert database.validate_extension_token("old-hash") is False
    assert database.validate_extension_token("new-hash") is True
    assert database.revoke_extension_client(client_id)
    assert database.validate_extension_token("new-hash") is False


def test_sync_provider_library_reuses_canonical_media(monkeypatch):
    database = memory_database(monkeypatch)
    first = MediaItem(
        id=42,
        title="Example",
        status="CURRENT",
        progress=3,
        episodes=12,
    )
    updated = first.model_copy(update={"progress": 4})

    initial_mapping = database.sync_provider_library("anilist", "AniList", [first])
    updated_mapping = database.sync_provider_library("anilist", "AniList", [updated])

    assert initial_mapping == updated_mapping
    assert database.canonical_media_id("anilist", 42) == initial_mapping["42"]
    with database.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM media").fetchone()[0] == 1
        remote = connection.execute(
            "SELECT progress FROM remote_library_entries"
        ).fetchone()
        local = connection.execute("SELECT progress FROM library_entries").fetchone()
    assert remote["progress"] == 4
    assert local["progress"] == 4


def test_cross_provider_import_keeps_providers_independent(monkeypatch):
    database = memory_database(monkeypatch)
    anilist = MediaItem(
        id=10,
        title="Sousou no Frieren",
        title_english="Frieren: Beyond Journey's End",
        status="CURRENT",
        progress=12,
        episodes=28,
        year=2023,
        format="TV",
    )
    mal = MediaItem(
        id=52991,
        title="Sousou no Frieren",
        title_english="Frieren: Beyond Journey's End",
        status="COMPLETED",
        progress=28,
        episodes=28,
        year=2023,
        format="TV",
    )

    anilist_mapping = database.sync_provider_library("anilist", "AniList", [anilist])
    mal_mapping = database.sync_provider_library("mal", "MyAnimeList", [mal])

    # Mismo título, proveedores distintos: cada uno es su propia obra, sin fusión.
    assert anilist_mapping["10"] != mal_mapping["52991"]
    with database.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM media").fetchone()[0] == 2
        identities = connection.execute(
            "SELECT provider_id, confidence FROM external_identities ORDER BY provider_id"
        ).fetchall()
    assert [row["provider_id"] for row in identities] == ["anilist", "mal"]
    assert all(row["confidence"] == 1.0 for row in identities)


def test_get_combined_library_lists_each_provider_work_independently(monkeypatch):
    database = memory_database(monkeypatch)
    anilist = MediaItem(
        id=10,
        title="Sousou no Frieren",
        title_english="Frieren: Beyond Journey's End",
        status="CURRENT",
        progress=12,
        episodes=28,
        year=2023,
        format="TV",
        genres=["Adventure"],
    )
    mal = MediaItem(
        id=52991,
        title="Sousou no Frieren",
        status="COMPLETED",
        progress=28,
        episodes=28,
        year=2023,
        format="TV",
    )

    database.sync_provider_library("anilist", "AniList", [anilist])
    database.sync_provider_library("mal", "MyAnimeList", [mal])

    combined = database.get_combined_library("ANIME", "anilist", "default")

    # Independientes: el mismo título de dos proveedores son dos entradas distintas.
    assert len(combined) == 2
    assert {entry["canonical_id"] for entry in combined} == {
        database.canonical_media_id("anilist", 10),
        database.canonical_media_id("mal", 52991),
    }


def test_cross_provider_import_does_not_merge_ambiguous_titles(monkeypatch):
    database = memory_database(monkeypatch)
    first = MediaItem(
        id=1,
        title="First Work",
        synonyms=["Shared Title"],
        status="CURRENT",
        progress=1,
        episodes=12,
        year=2020,
        format="TV",
    )
    second = first.model_copy(update={"id": 2, "title": "Second Work"})
    incoming = first.model_copy(
        update={"id": 3, "title": "Shared Title", "synonyms": []}
    )

    database.sync_provider_library("anilist", "AniList", [first, second])
    database.sync_provider_library("mal", "MyAnimeList", [incoming])

    with database.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM media").fetchone()[0] == 3
    # Proveedores independientes: el título compartido NO se fusiona entre proveedores.
    assert database.canonical_media_id("mal", 3) != database.canonical_media_id("anilist", 1)


def test_cross_provider_import_rejects_conflicting_metadata(monkeypatch):
    database = memory_database(monkeypatch)
    original = MediaItem(
        id=1,
        title="Same Name",
        status="CURRENT",
        progress=1,
        episodes=12,
        year=2000,
        format="TV",
    )
    remake = original.model_copy(
        update={"id": 2, "episodes": 24, "year": 2025}
    )

    database.sync_provider_library("anilist", "AniList", [original])
    database.sync_provider_library("mal", "MyAnimeList", [remake])

    with database.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM media").fetchone()[0] == 2


def test_scoped_cache_records_provider_account_and_origin(monkeypatch):
    database = memory_database(monkeypatch)

    database.set_cache("anilist:personal:list", [{"id": 1}], 60)
    record = database.get_cache_record("anilist:personal:list")
    status = database.get_cache_status()[0]

    assert record is not None
    assert record.provider_id == "anilist"
    assert record.account_alias == "personal"
    assert record.resource == "list"
    assert record.refresh_reason == "network_refresh"
    assert status["account_alias"] == "personal"


def test_cache_prunes_least_recently_used_details_per_account(monkeypatch):
    database = memory_database(monkeypatch)
    monkeypatch.setattr("nyanko_api.database.CACHE_RESOURCE_LIMITS", {"media:": 2})
    clock = iter([1, 2, 3, 4, 5, 6])
    monkeypatch.setattr("nyanko_api.database.time.time", lambda: next(clock))

    database.set_cache("anilist:one:media:1", {}, 60)
    database.set_cache("anilist:one:media:2", {}, 60)
    assert database.get_cache("anilist:one:media:1") == {}
    database.set_cache("anilist:one:media:3", {}, 60)

    assert database.get_cache_record("anilist:one:media:2") is None
    assert {item["key"] for item in database.get_cache_status()} == {
        "anilist:one:media:1",
        "anilist:one:media:3",
    }


def test_accounts_have_one_primary_and_can_be_updated(monkeypatch):
    database = memory_database(monkeypatch)

    first = database.ensure_account("anilist", "first")
    second = database.ensure_account("anilist", "second")
    accounts = database.get_accounts()

    assert sum(bool(account["is_primary"]) for account in accounts) == 1
    assert next(account for account in accounts if account["id"] == first)["is_primary"]

    updated = database.update_account(second, is_primary=True)

    assert updated is not None
    assert updated["is_primary"] == 1
    assert sum(bool(account["is_primary"]) for account in database.get_accounts()) == 1


def test_only_primary_account_updates_canonical_library(monkeypatch):
    database = memory_database(monkeypatch)
    first = MediaItem(id=42, title="Example", status="CURRENT", progress=3)
    second = first.model_copy(update={"status": "COMPLETED", "progress": 12})

    database.sync_provider_library("anilist", "AniList", [first], "first")
    database.sync_provider_library("anilist", "AniList", [second], "second")

    with database.connect() as connection:
        canonical = connection.execute(
            "SELECT status, progress FROM library_entries"
        ).fetchone()
    assert dict(canonical) == {"status": "COMPLETED", "progress": 12}


def test_sync_media_details_adds_titles_season_and_episode_slots(monkeypatch):
    database = memory_database(monkeypatch)

    class Details:
        def model_dump(self, mode):
            assert mode == "json"
            return {
                "format": "TV",
                "episodes": 3,
                "site_url": "https://anilist.co/anime/99",
                "title_romaji": "Romaji title",
                "title_english": "English title",
                "title_native": "Native title",
                "season": "SPRING",
                "season_year": 2026,
            }

    media_id = database.sync_media_details("anilist", 99, Details())

    assert media_id is not None
    with database.connect() as connection:
        titles = connection.execute(
            "SELECT COUNT(*) FROM media_titles WHERE media_id = ?", (media_id,)
        ).fetchone()[0]
        seasons = connection.execute(
            "SELECT COUNT(*) FROM media_seasons WHERE media_id = ?", (media_id,)
        ).fetchone()[0]
        episodes = connection.execute(
            "SELECT COUNT(*) FROM episodes WHERE media_id = ?", (media_id,)
        ).fetchone()[0]
    assert titles == 3
    assert seasons == 1
    assert episodes == 3


def test_cache_round_trip_and_invalidation(monkeypatch):
    database = memory_database(monkeypatch)

    database.set_cache("anilist:list", [{"id": 1}], 60)
    database.set_cache("anilist:season:WINTER:2026", [{"id": 2}], 60)

    assert database.get_cache("anilist:list") == [{"id": 1}]
    database.invalidate_cache("anilist:list")
    assert database.get_cache("anilist:list") is None
    assert database.get_cache("anilist:season:WINTER:2026") == [{"id": 2}]


def test_expired_cache_is_not_returned(monkeypatch):
    database = memory_database(monkeypatch)
    monkeypatch.setattr("nyanko_api.database.time.time", lambda: 100)
    database.set_cache("expired", {"value": True}, 10)

    monkeypatch.setattr("nyanko_api.database.time.time", lambda: 111)
    assert database.get_cache("expired") is None
    record = database.get_cache_record("expired")
    assert record is not None
    assert record.stale is True
    assert record.payload == {"value": True}


def test_corrupt_cache_is_discarded(monkeypatch):
    database = memory_database(monkeypatch)
    with database.connect() as connection:
        connection.execute(
            "INSERT INTO cache (key, payload, expires_at) VALUES (?, ?, ?)",
            ("corrupt", "{", 9999999999),
        )

    assert database.get_cache_record("corrupt") is None
    assert database.get_cache_status() == []


def test_clear_all_data_removes_settings_cache_and_events(monkeypatch):
    database = memory_database(monkeypatch)
    database.set_setting("anilist_access_token", "secret")
    database.set_cache("anilist:list", [{"id": 1}], 60)
    with database.connect() as connection:
        connection.execute(
            "INSERT INTO playback_events (source, raw_title) VALUES (?, ?)",
            ("test", "Test - Episode 1"),
        )

    database.clear_all_data()

    assert database.get_setting("anilist_access_token") is None
    assert database.get_cache("anilist:list") is None


def test_clear_all_data_removes_match_corrections(monkeypatch):
    database = memory_database(monkeypatch)
    database.set_match_correction("wrong title", 42)

    database.clear_all_data()

    assert database.get_match_correction("wrong title") is None


def test_match_correction_round_trip(monkeypatch):
    database = memory_database(monkeypatch)
    assert database.get_match_correction("raw title") is None

    database.set_match_correction("raw title", 42)
    assert database.get_match_correction("raw title") == 42

    database.set_match_correction("raw title", 7)
    assert database.get_match_correction("raw title") == 7

    database.delete_match_correction("raw title")
    assert database.get_match_correction("raw title") is None


def test_playback_history_filters_and_clear(monkeypatch):
    database = memory_database(monkeypatch)
    first = database.insert_playback_event("vlc", "Show - 01", "Show", 1)
    database.update_playback_event(first, status="confirmed", media_id=10, progress_after=1)
    database.insert_playback_event("mpv", "Other - 02", "Other", 2, status="ignored")

    assert database.get_playback_event(first)["media_id"] == 10
    assert len(database.get_recent_playback_events(status="confirmed")) == 1
    assert len(database.get_recent_playback_events(source="mpv")) == 1
    assert database.get_recent_matching_playback_event("vlc", "Show - 01", 1, 300)["id"] == first

    database.clear_playback_events()
    assert database.get_recent_playback_events() == []


def test_playback_history_date_filter_and_retention(monkeypatch):
    database = memory_database(monkeypatch)
    old = database.insert_playback_event("vlc", "Old - 01", "Old", 1)
    recent = database.insert_playback_event("mpv", "Recent - 01", "Recent", 1)
    with database.connect() as connection:
        connection.execute(
            "UPDATE playback_events SET detected_at = '2020-01-15 12:00:00' WHERE id = ?",
            (old,),
        )

    assert [event["id"] for event in database.get_recent_playback_events(date_from="2026-01-01")] == [recent]
    assert database.prune_playback_events(90) == 1
    assert database.get_playback_event(old) is None


@pytest.mark.asyncio
async def test_stale_cache_is_used_when_refresh_fails(monkeypatch):
    database = memory_database(monkeypatch)
    monkeypatch.setattr("nyanko_api.database.time.time", lambda: 100)
    database.set_cache(
        "anilist:list",
        [{"id": 1, "title": "Cached", "status": "CURRENT", "progress": 1}],
        10,
    )
    monkeypatch.setattr("nyanko_api.database.time.time", lambda: 111)

    async def unavailable():
        raise RuntimeError("AniList unavailable")

    items, status = await cached_list(database, "anilist:list", 60, MediaItem, unavailable)
    await asyncio.sleep(0)
    assert items[0].title == "Cached"
    assert status == "stale"
    assert database.get_cache_status()[0]["stale"] is True


@pytest.mark.asyncio
async def test_stale_cache_returns_before_background_refresh(monkeypatch):
    database = memory_database(monkeypatch)
    monkeypatch.setattr("nyanko_api.database.time.time", lambda: 100)
    database.set_cache("key", {"value": "cached"}, 10)
    monkeypatch.setattr("nyanko_api.database.time.time", lambda: 111)
    started = asyncio.Event()
    release = asyncio.Event()

    async def loader():
        started.set()
        await release.wait()
        return _SampleValue(value="remote")

    value, status = await cached_value(database, "key", 60, _SampleValue, loader)

    assert value.value == "cached"
    assert status == "stale"
    await started.wait()
    refresh = next(iter(_cache_refreshes.values()))
    release.set()
    await refresh
    assert database.get_cache_record("key").payload == {"value": "remote"}


def test_sync_provider_library_stores_genres_and_enrich_returns_them(monkeypatch):
    database = memory_database(monkeypatch)
    item = MediaItem(
        id=55,
        title="Genre Test",
        status="CURRENT",
        progress=1,
        genres=["Action", "Fantasy"],
    )

    database.sync_provider_library("anilist", "AniList", [item])
    enriched = database.enrich_provider_library("anilist", [item])

    assert enriched[0].genres == ["Action", "Fantasy"]
    with database.connect() as connection:
        genres = {
            row["genre"]
            for row in connection.execute(
                "SELECT genre FROM media_genres WHERE media_id = ?",
                (enriched[0].canonical_id,),
            ).fetchall()
        }
    assert genres == {"Action", "Fantasy"}


def test_enrich_provider_library_does_not_reuse_closed_connection(monkeypatch):
    database = Database(Path(":memory:"))
    uri = "file:nyanko-closed-connection-test?mode=memory&cache=shared"
    anchor = sqlite3.connect(uri, uri=True)

    @contextmanager
    def connect():
        connection = sqlite3.connect(uri, uri=True)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    monkeypatch.setattr(database, "connect", connect)
    try:
        database.initialize()
        item = MediaItem(
            id=56,
            title="Connection Test",
            status="CURRENT",
            progress=1,
            genres=["Drama"],
        )

        database.sync_provider_library("anilist", "AniList", [item])
        enriched = database.enrich_provider_library("anilist", [item])

        assert enriched[0].genres == ["Drama"]
        assert enriched[0].canonical_id is not None
    finally:
        anchor.close()


def test_playback_event_error_message_round_trip(monkeypatch):
    database = memory_database(monkeypatch)
    event_id = database.insert_playback_event(
        source="test",
        raw_title="test",
        anime_title="Test",
        episode=1,
        status="failed",
    )
    database.update_playback_event(
        event_id,
        status="failed",
        error_message="AniList rejected the update",
    )

    event = database.get_playback_event(event_id)
    assert event is not None
    assert event["status"] == "failed"
    assert event["error_message"] == "AniList rejected the update"


def test_media_tags_round_trip(monkeypatch):
    database = memory_database(monkeypatch)
    database.sync_provider_library(
        "anilist", "AniList", [MediaItem(id=1, title="Tagged", status="CURRENT", progress=1)]
    )
    canonical_id = database.canonical_media_id("anilist", 1)
    assert canonical_id is not None

    database.add_media_tag(canonical_id, "Favorite")
    database.add_media_tag(canonical_id, "Rewatch")
    database.add_media_tag(canonical_id, "favorite")

    assert database.get_media_tags(canonical_id) == ["favorite", "rewatch"]
    assert database.get_all_tags() == ["favorite", "rewatch"]

    database.remove_media_tag(canonical_id, "favorite")

    assert database.get_media_tags(canonical_id) == ["rewatch"]
    assert database.get_all_tags() == ["rewatch"]


@pytest.mark.asyncio
async def test_cached_value_returns_hit_for_fresh_cache(monkeypatch):
    database = memory_database(monkeypatch)
    monkeypatch.setattr("nyanko_api.database.time.time", lambda: 100)
    database.set_cache("key", {"value": "cached"}, 60)

    async def loader():
        return _SampleValue(value="remote")

    value, status = await cached_value(database, "key", 60, _SampleValue, loader)

    assert value.value == "cached"
    assert status == "hit"


@pytest.mark.asyncio
async def test_cached_value_returns_miss_and_stores_value(monkeypatch):
    database = memory_database(monkeypatch)

    async def loader():
        return _SampleValue(value="remote")

    value, status = await cached_value(database, "key", 60, _SampleValue, loader)

    assert value.value == "remote"
    assert status == "miss"
    record = database.get_cache_record("key")
    assert record is not None
    assert record.payload["value"] == "remote"


def test_detects_conflict_when_local_and_remote_changed(monkeypatch):
    database = memory_database(monkeypatch)
    first = MediaItem(id=1, title="Frieren", status="CURRENT", progress=5)
    database.sync_provider_library("anilist", "AniList", [first])

    # Simulate local edit through canonical library.
    with database.connect() as connection:
        connection.execute(
            "UPDATE library_entries SET status = 'PAUSED', progress = 6 WHERE media_id = 1"
        )

    # Remote changes arrive during sync.
    remote_changed = first.model_copy(update={"status": "COMPLETED", "progress": 12})
    database.sync_provider_library("anilist", "AniList", [remote_changed])

    conflicts = database.get_conflicts("pending")
    assert len(conflicts) == 2
    fields = {conflict["field"] for conflict in conflicts}
    assert fields == {"status", "progress"}


def test_no_conflict_when_only_remote_changed(monkeypatch):
    database = memory_database(monkeypatch)
    first = MediaItem(id=1, title="Frieren", status="CURRENT", progress=5)
    database.sync_provider_library("anilist", "AniList", [first])

    remote_changed = first.model_copy(update={"progress": 12})
    database.sync_provider_library("anilist", "AniList", [remote_changed])

    assert database.get_conflicts("pending") == []


def test_resolve_conflict_updates_values(monkeypatch):
    database = memory_database(monkeypatch)
    first = MediaItem(id=1, title="Frieren", status="CURRENT", progress=5)
    database.sync_provider_library("anilist", "AniList", [first])

    with database.connect() as connection:
        connection.execute(
            "UPDATE library_entries SET progress = 6 WHERE media_id = 1"
        )

    remote_changed = first.model_copy(update={"progress": 12})
    database.sync_provider_library("anilist", "AniList", [remote_changed])

    conflict = database.get_conflicts("pending")[0]
    assert database.resolve_conflict(conflict["id"], "resolved_remote", "12")

    updated = database.get_conflicts_by_id(conflict["id"])
    assert updated is not None
    assert updated["status"] == "resolved_remote"
    assert updated["resolution_value"] == "12"


def test_library_entries_has_date_columns(monkeypatch):
    database = memory_database(monkeypatch)
    with database.connect() as connection:
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(library_entries)")}
    assert "started_at" in columns
    assert "completed_at" in columns


def test_sync_library_stores_dates(monkeypatch):
    database = memory_database(monkeypatch)
    item = MediaItem(
        id=1,
        title="Test",
        status="COMPLETED",
        progress=12,
        started_at="2024-01-15",
        completed_at="2024-03-30",
    )
    database.sync_provider_library("anilist", "AniList", [item])
    with database.connect() as connection:
        row = connection.execute(
            "SELECT started_at, completed_at FROM library_entries"
        ).fetchone()
    assert row["started_at"] == "2024-01-15"
    assert row["completed_at"] == "2024-03-30"


def test_sync_library_preserves_existing_dates_on_resync(monkeypatch):
    database = memory_database(monkeypatch)
    # First sync: with dates
    item_with_dates = MediaItem(
        id=1,
        title="Test",
        status="COMPLETED",
        progress=12,
        started_at="2024-01-15",
        completed_at="2024-03-30",
    )
    database.sync_provider_library("anilist", "AniList", [item_with_dates])

    # Re-sync: without dates (NULL) — should not overwrite
    item_no_dates = MediaItem(
        id=1,
        title="Test",
        status="COMPLETED",
        progress=12,
    )
    database.sync_provider_library("anilist", "AniList", [item_no_dates])

    with database.connect() as connection:
        row = connection.execute(
            "SELECT started_at, completed_at FROM library_entries"
        ).fetchone()
    assert row["started_at"] == "2024-01-15"
    assert row["completed_at"] == "2024-03-30"


def test_default_nyaa_source_seeded(tmp_path):
    db = Database(tmp_path / "t.db")
    db.initialize()
    sources = db.list_torrent_sources()
    assert any("nyaa" in s["url"].lower() for s in sources)


def test_torrent_source_crud(tmp_path):
    db = Database(tmp_path / "t.db")
    db.initialize()
    sid = db.add_torrent_source("Test", "https://example.com/rss", True)
    assert any(s["id"] == sid and s["name"] == "Test" for s in db.list_torrent_sources())
    db.update_torrent_source(sid, "Test2", "https://example.com/rss2", False)
    row = next(s for s in db.list_torrent_sources() if s["id"] == sid)
    assert row["name"] == "Test2" and row["enabled"] == 0
    db.delete_torrent_source(sid)
    assert all(s["id"] != sid for s in db.list_torrent_sources())


def test_torrent_filter_crud(tmp_path):
    db = Database(tmp_path / "t.db")
    db.initialize()
    fid = db.add_torrent_filter("resolution", "equals", "1080p", "prefer", True, 0)
    rows = db.list_torrent_filters()
    assert any(f["id"] == fid and f["action"] == "prefer" for f in rows)
    db.delete_torrent_filter(fid)
    assert all(f["id"] != fid for f in db.list_torrent_filters())


def test_torrent_seen_flags(tmp_path):
    db = Database(tmp_path / "t.db")
    db.initialize()
    db.mark_torrent_seen("sig1", 42)
    assert "sig1" in db.list_seen_signatures()
    assert db.is_torrent_discarded("sig1") is False
    db.set_torrent_discarded("sig1", 42)
    assert db.is_torrent_discarded("sig1") is True
    # mark_torrent_seen no debe revertir discarded
    db.mark_torrent_seen("sig1", 42)
    assert db.is_torrent_discarded("sig1") is True


def test_get_local_series_matched_files_use_canonical_title(tmp_path):
    db = Database(tmp_path / "t.db"); db.initialize()
    db.sync_provider_library("anilist", "AniList", [
        MediaItem(id=1, title="Sousou no Frieren", status="CURRENT", progress=12)
    ])
    media_id = db.canonical_media_id("anilist", 1)
    db.replace_local_files([
        {"path": "/a/frieren-01.mkv", "media_id": media_id, "episode": 1, "parsed_title": "frieren"},
        {"path": "/a/frieren-02.mkv", "media_id": media_id, "episode": 2, "parsed_title": "frieren"},
    ])
    series = db.get_local_series()
    assert len(series) == 1
    s = series[0]
    assert s["matched"] is True
    assert s["episode_count"] == 2
    assert s["title"] == "Sousou no Frieren"


def test_get_local_series_groups_scanned_files(tmp_path):
    db = Database(tmp_path / "t.db"); db.initialize()
    # media canónica para matchear
    db.replace_local_files([
        {"path": "/a/Frieren - 01.mkv", "media_id": None, "episode": 1, "parsed_title": "Frieren"},
        {"path": "/a/Frieren - 02.mkv", "media_id": None, "episode": 2, "parsed_title": "Frieren"},
        {"path": "/a/Bocchi - 01.mkv", "media_id": None, "episode": 1, "parsed_title": "Bocchi"},
    ])
    series = db.get_local_series()
    by_title = {s["title"]: s for s in series}
    assert by_title["Frieren"]["episode_count"] == 2
    assert by_title["Bocchi"]["episode_count"] == 1
    assert all(s["matched"] is False for s in series)  # sin media_id


