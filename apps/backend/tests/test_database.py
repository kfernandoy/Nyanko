import asyncio
import sqlite3
from contextlib import contextmanager
from pathlib import Path

import pytest
from pydantic import BaseModel

from nyanko_api.database import Database
from nyanko_api.main import _cache_refreshes, cached_list, cached_value
from nyanko_api.models import MediaDetails, MediaItem, TrailerInfo


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
    assert version == 11
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


def test_sync_provider_library_keeps_primary_title_on_resync(monkeypatch):
    # El INSERT OR IGNORE anterior nunca restauraba is_primary tras el UPDATE a 0,
    # y a partir del segundo sync la base quedaba sin ningún título primario.
    database = memory_database(monkeypatch)
    item = MediaItem(id=42, title="Example", status="CURRENT", progress=3, episodes=12)
    database.sync_provider_library("anilist", "AniList", [item])
    database.sync_provider_library("anilist", "AniList", [item])
    with database.connect() as connection:
        primary = connection.execute(
            "SELECT COUNT(*) FROM media_titles WHERE is_primary = 1"
        ).fetchone()[0]
    assert primary == 1


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


    # Proveedores independientes: el titulo compartido no se fusiona entre proveedores.


def test_sync_media_details_persists_full_local_copy(monkeypatch):
    database = memory_database(monkeypatch)
    item = MediaItem(id=42, title="Example", status="CURRENT", progress=3, episodes=12)
    mapping = database.sync_provider_library("anilist", "AniList", [item])
    media_id = mapping["42"]
    details = MediaDetails(
        id=42,
        title="Example",
        title_romaji="Example Romaji",
        title_english="Example English",
        title_native="Example Native",
        synonyms=["Alt Title"],
        description="Persistent description",
        site_url="https://example.test/anime/42",
        banner_image="https://img.test/banner.jpg",
        cover_image="https://img.test/cover.jpg",
        format="TV",
        media_type="ANIME",
        status="RELEASING",
        source="MANGA",
        season="SPRING",
        season_year=2026,
        episodes=12,
        genres=["Drama"],
        studios=["Studio Test"],
        country="JP",
        average_score=88,
        score_format="POINT_100",
        trailer=TrailerInfo(id="abc123", site="youtube"),
    )

    database.sync_media_details("anilist", 42, details)
    database.set_media_asset_paths(
        "anilist",
        42,
        cover_image_local="/assets/anilist/42/cover.jpg",
        banner_image_local="/assets/anilist/42/banner.jpg",
    )
    persisted = database.get_persisted_media_details("anilist", media_id)

    assert persisted is not None
    assert persisted.description == "Persistent description"
    assert persisted.cover_image == "/assets/anilist/42/cover.jpg"
    assert persisted.banner_image == "/assets/anilist/42/banner.jpg"
    assert persisted.studios == ["Studio Test"]
    assert persisted.trailer is not None and persisted.trailer.id == "abc123"
    assert persisted.canonical_id == media_id

    # Proveedores independientes: el título compartido NO se fusiona entre proveedores.


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


def test_media_mapping_conserva_la_tupla_de_anime_y_anade_el_offset_de_manga(monkeypatch):
    database = memory_database(monkeypatch)

    database.set_media_mapping("crunchyroll", "abc", 7, 3)
    mapping_anime = database.get_media_mapping("crunchyroll", "abc")
    assert mapping_anime == (7, 3)
    assert len(mapping_anime) == 2

    database.set_media_mapping(
        "local_archive",
        "0:Berserk",
        42,
        chapter_offset=100,
        manga_link=True,
    )
    assert database.get_media_mapping_full("local_archive", "0:Berserk") == {
        "media_id": 42,
        "episode_offset": 0,
        "chapter_offset": 100,
    }


def test_el_guarda_impide_reapuntar_un_vinculo_confirmado(monkeypatch):
    database = memory_database(monkeypatch)

    with pytest.raises(ValueError, match="local_archive"):
        database.set_media_mapping("local_archive", "0:Berserk", 999)
    assert database.get_media_mapping_full("local_archive", "0:Berserk") is None

    database.set_media_mapping(
        "local_archive",
        "0:Berserk",
        42,
        chapter_offset=100,
        manga_link=True,
    )
    with pytest.raises(ValueError, match="local_archive"):
        database.set_media_mapping("local_archive", "0:Berserk", 999)
    assert database.get_media_mapping_full("local_archive", "0:Berserk") == {
        "media_id": 42,
        "episode_offset": 0,
        "chapter_offset": 100,
    }

    with pytest.raises(ValueError, match="crunchyroll"):
        database.set_media_mapping("crunchyroll", "abc", 7, manga_link=True)


def test_el_borrado_respeta_el_namespace_y_es_idempotente(monkeypatch):
    database = memory_database(monkeypatch)
    database.set_media_mapping(
        "local_archive",
        "0:Berserk",
        42,
        chapter_offset=100,
        manga_link=True,
    )

    with pytest.raises(ValueError, match="local_archive"):
        database.delete_media_mapping("local_archive", "0:Berserk")
    assert database.get_media_mapping_full("local_archive", "0:Berserk") is not None

    database.delete_media_mapping("local_archive", "0:Berserk", manga_link=True)
    database.delete_media_mapping("local_archive", "0:Berserk", manga_link=True)
    assert database.get_media_mapping_full("local_archive", "0:Berserk") is None

    database.set_media_mapping("crunchyroll", "abc", 777, 3)
    with pytest.raises(ValueError, match="crunchyroll"):
        database.delete_media_mapping("crunchyroll", "abc", manga_link=True)
    assert database.get_media_mapping("crunchyroll", "abc") == (777, 3)


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


def test_torrent_source_kind(tmp_path):
    db = Database(tmp_path / "t.db")
    db.initialize()
    sid = db.add_torrent_source("Buscar", "https://x/?q=%title%", True, kind="search")
    row = next(s for s in db.list_torrent_sources() if s["id"] == sid)
    assert row["kind"] == "search"
    # el seed Nyaa por defecto es 'release'
    assert any(s["kind"] == "release" for s in db.list_torrent_sources())


def test_torrent_filter_taiga_crud(tmp_path):
    db = Database(tmp_path / "t.db")
    db.initialize()
    fid = db.add_torrent_filter(
        name="Solo 1080 de SubsPlease", action="select", match="all", scope="all",
        enabled=True,
        conditions=[{"element": "resolution", "operator": "equals", "value": "1080p"},
                    {"element": "group", "operator": "is", "value": "SubsPlease"}],
        anime_ids=[],
    )
    f = next(x for x in db.list_torrent_filters() if x["id"] == fid)
    assert f["action"] == "select" and f["match"] == "all"
    assert len(f["conditions"]) == 2 and f["anime_ids"] == []
    db.delete_torrent_filter(fid)
    assert all(x["id"] != fid for x in db.list_torrent_filters())


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
    db = Database(tmp_path / "t.db")
    db.initialize()
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
    db = Database(tmp_path / "t.db")
    db.initialize()
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




# --- Asociación por referencia externa confiable (idMal de AniList) ---

def test_anilist_id_mal_prelinks_mal_identity(monkeypatch):
    # AniList publica idMal: un sync posterior de MAL debe reutilizar la misma obra
    # canónica en vez de crear un duplicado.
    database = memory_database(monkeypatch)
    anilist_item = MediaItem(
        id=101, title="Frieren", status="CURRENT", progress=3, episodes=28, id_mal=52991,
    )
    mapping = database.sync_provider_library("anilist", "AniList", [anilist_item])
    canonical = mapping["101"]

    assert database.canonical_media_id("mal", 52991) == canonical

    mal_item = MediaItem(id=52991, title="Sousou no Frieren", status="CURRENT", progress=5, episodes=28)
    mal_mapping = database.sync_provider_library("mal", "MyAnimeList", [mal_item])
    assert mal_mapping["52991"] == canonical
    with database.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM media").fetchone()[0] == 1


def test_id_mal_does_not_steal_existing_mal_identity(monkeypatch):
    # Si MAL sincronizó primero, su identidad ya apunta a su propia fila: el idMal de
    # AniList no debe re-apuntarla (quedan dos filas, como antes de esta mejora).
    database = memory_database(monkeypatch)
    mal_item = MediaItem(id=52991, title="Sousou no Frieren", status="CURRENT", progress=5, episodes=28)
    mal_mapping = database.sync_provider_library("mal", "MyAnimeList", [mal_item])

    anilist_item = MediaItem(
        id=101, title="Frieren", status="CURRENT", progress=3, episodes=28, id_mal=52991,
    )
    anilist_mapping = database.sync_provider_library("anilist", "AniList", [anilist_item])

    assert database.canonical_media_id("mal", 52991) == mal_mapping["52991"]
    assert anilist_mapping["101"] != mal_mapping["52991"]


def test_id_mal_ignored_for_manga(monkeypatch):
    # Los ids de anime y manga de MAL comparten espacio numérico; hasta que la identidad
    # incluya media_type, el pre-enlace se limita a anime.
    database = memory_database(monkeypatch)
    manga = MediaItem(
        id=30002, title="Berserk", status="CURRENT", progress=10,
        chapters=380, media_type="MANGA", id_mal=2,
    )
    database.sync_provider_library("anilist", "AniList", [manga], media_type="MANGA")
    assert database.canonical_media_id("mal", 2) is None


def test_backfill_ligero_no_borra_los_personajes_ya_cacheados(monkeypatch):
    """Un detalle LIGERO (sin characters/staff/relations/recommendations) no debe pisar
    los que ya estaban cacheados.

    El backfill baja `_ANIME_LIST_FIELDS`, que omite esos cuatro bloques (son el 95% del
    coste de la request y no se pintan en la grid). Llegan como listas vacías. Sin la
    guarda del CASE WHEN en sync_media_details, cada pasada del backfill BORRARÍA el
    reparto y las relaciones que la apertura de ficha había cacheado — pérdida de datos
    silenciosa, y la ficha se quedaría vacía al reabrirla.
    """
    from nyanko_api.models import CharacterEdge, CharacterName, CharacterNode, RelationEdge

    database = memory_database(monkeypatch)
    item = MediaItem(id=42, title="Example", status="CURRENT", progress=3, episodes=12)
    database.sync_provider_library("anilist", "AniList", [item])
    media_id = database.sync_provider_library("anilist", "AniList", [item])["42"]

    base = dict(
        id=42,
        title="Example",
        media_type="ANIME",
        score_format="POINT_100",
        synonyms=[],
        site_url="https://example.test/anime/42",
        genres=[],
        studios=[],
    )

    # 1. La apertura de ficha cachea el detalle COMPLETO (con reparto y relaciones).
    completo = MediaDetails(
        **base,
        characters=[
            CharacterEdge(role="MAIN", node=CharacterNode(name=CharacterName(full="Nyanko")))
        ],
        relations=[
            RelationEdge(id=99, title="Example 2", format="TV", relation_type="SEQUEL")
        ],
    )
    database.sync_media_details("anilist", 42, completo)

    guardado = database.get_persisted_media_details("anilist", media_id)
    assert len(guardado.characters) == 1
    assert len(guardado.relations) == 1

    # 2. Pasa el backfill con un detalle LIGERO: los cuatro bloques vienen vacíos.
    ligero = MediaDetails(**base, description="texto refrescado por el backfill")
    assert ligero.characters == [] and ligero.relations == []
    database.sync_media_details("anilist", 42, ligero)

    # 3. El reparto y las relaciones SIGUEN AHÍ; lo demás sí se refrescó.
    tras_backfill = database.get_persisted_media_details("anilist", media_id)
    assert len(tras_backfill.characters) == 1, (
        "el backfill ligero borró los personajes cacheados: pérdida de datos"
    )
    assert len(tras_backfill.relations) == 1, (
        "el backfill ligero borró las relaciones cacheadas: pérdida de datos"
    )
    assert tras_backfill.description == "texto refrescado por el backfill"


# --- Schema v8: chapter_progress (docs/specs/progress-model.md) ---


def _degrade_to_v7(path: Path) -> None:
    """Convierte una BD v8 recién creada en una v7 realista: quita la columna nueva y
    baja la versión. Es la única forma honesta de probar la migración — un fixture
    escrito a mano no comparte el esquema con el de producción."""
    connection = sqlite3.connect(path)
    connection.execute("ALTER TABLE library_entries DROP COLUMN chapter_progress")
    connection.execute("DELETE FROM schema_migrations")
    connection.execute("INSERT INTO schema_migrations(version) VALUES (7)")
    connection.commit()
    connection.close()


def test_canonical_schema_version_is_11():
    from nyanko_api.database import CANONICAL_SCHEMA_VERSION

    assert CANONICAL_SCHEMA_VERSION == 11


def test_new_database_has_chapter_progress_as_real(monkeypatch):
    database = memory_database(monkeypatch)
    with database.connect() as connection:
        columns = {
            row["name"]: row["type"]
            for row in connection.execute("PRAGMA table_info(library_entries)").fetchall()
        }
    assert columns["chapter_progress"] == "REAL"
    # progress sigue siendo el entero que el proveedor acepta: v8 es ADITIVA.
    assert columns["progress"] == "INTEGER"


def test_v7_database_migrates_additively_without_losing_rows(tmp_path):
    path = tmp_path / "nyanko.sqlite3"
    Database(path).initialize()
    _degrade_to_v7(path)

    connection = sqlite3.connect(path)
    connection.execute("INSERT INTO media(id) VALUES (1), (2)")
    connection.execute(
        "INSERT INTO library_entries(media_id, status, progress) "
        "VALUES (1, 'CURRENT', 10), (2, 'COMPLETED', 24)"
    )
    connection.commit()
    connection.close()

    Database(path).initialize()

    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    try:
        columns = {
            row["name"]: row["type"]
            for row in connection.execute("PRAGMA table_info(library_entries)").fetchall()
        }
        assert columns["chapter_progress"] == "REAL"
        rows = connection.execute(
            "SELECT progress, chapter_progress FROM library_entries ORDER BY media_id"
        ).fetchall()
        # Las filas viejas siguen ahí, con su progress intacto y chapter_progress a NULL.
        assert len(rows) == 2
        assert [row["progress"] for row in rows] == [10, 24]
        assert all(row["chapter_progress"] is None for row in rows)
        version = connection.execute("SELECT MAX(version) AS v FROM schema_migrations").fetchone()["v"]
        assert version == 11
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        connection.close()

    # Subir CANONICAL_SCHEMA_VERSION es lo que arma el backup: es el único rollback que hay.
    backups = list(tmp_path.glob("nyanko.backup-v11-*.sqlite3"))
    assert len(backups) == 1, f"sin backup pre-migración: {list(tmp_path.iterdir())}"
    backup = sqlite3.connect(backups[0])
    try:
        # El backup es la BD DE ANTES: sin la columna nueva y con las filas.
        names = {row[1] for row in backup.execute("PRAGMA table_info(library_entries)").fetchall()}
        assert "chapter_progress" not in names
        assert backup.execute("SELECT COUNT(*) FROM library_entries").fetchone()[0] == 2
    finally:
        backup.close()


# --- Schema v10: library_folders.kind (anime/manga/ambas) ---


def _degrade_to_v9(path: Path) -> None:
    """Convierte una BD v10 recién creada en una v9 realista: quita la columna nueva y
    baja la versión. Es la única forma honesta de probar la migración — un fixture
    escrito a mano no comparte el esquema con el de producción."""
    connection = sqlite3.connect(path)
    connection.execute("ALTER TABLE library_folders DROP COLUMN kind")
    connection.execute("DELETE FROM schema_migrations")
    connection.execute("INSERT INTO schema_migrations(version) VALUES (9)")
    connection.commit()
    connection.close()


def test_new_database_has_library_folder_kind_defaulting_to_ambas(monkeypatch):
    database = memory_database(monkeypatch)
    with database.connect() as connection:
        names = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(library_folders)").fetchall()
        }
        assert "kind" in names
        # Un escritor que no manda tipo (un renderer viejo, un INSERT a pelo) cae en
        # 'ambas': el comportamiento de hoy. Fallar a 'anime'/'manga' volvería la
        # carpeta invisible para un mundo EN SILENCIO — el bug que se está arreglando.
        connection.execute("INSERT INTO library_folders(path, recursive) VALUES ('/sin/tipo', 1)")
        kind = connection.execute(
            "SELECT kind FROM library_folders WHERE path = '/sin/tipo'"
        ).fetchone()["kind"]
    assert kind == "ambas"


def test_v9_library_folders_migran_a_ambas(tmp_path):
    path = tmp_path / "nyanko.sqlite3"
    Database(path).initialize()
    _degrade_to_v9(path)

    connection = sqlite3.connect(path)
    connection.execute(
        "INSERT INTO library_folders(path, recursive) VALUES ('/anime/series', 1), ('/manga/tomos', 0)"
    )
    connection.commit()
    connection.close()

    Database(path).initialize()

    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            "SELECT path, recursive, kind FROM library_folders ORDER BY path"
        ).fetchall()
        # Las carpetas de una biblioteca de producción HOY sirven para las dos cosas:
        # migrarlas a otra cosa sería pérdida de datos silenciosa (Core Value).
        assert len(rows) == 2
        assert [row["path"] for row in rows] == ["/anime/series", "/manga/tomos"]
        assert [row["kind"] for row in rows] == ["ambas", "ambas"]
        assert [bool(row["recursive"]) for row in rows] == [True, False]
        version = connection.execute("SELECT MAX(version) AS v FROM schema_migrations").fetchone()["v"]
        assert version == 11
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        connection.close()

    # Subir CANONICAL_SCHEMA_VERSION es lo que arma el backup: es el único rollback que hay.
    backups = list(tmp_path.glob("nyanko.backup-v11-*.sqlite3"))
    assert len(backups) == 1, f"sin backup pre-migración: {list(tmp_path.iterdir())}"
    backup = sqlite3.connect(backups[0])
    try:
        # El backup es la BD DE ANTES: sin la columna nueva y con las filas.
        names = {row[1] for row in backup.execute("PRAGMA table_info(library_folders)").fetchall()}
        assert "kind" not in names
        assert backup.execute("SELECT COUNT(*) FROM library_folders").fetchone()[0] == 2
    finally:
        backup.close()


def _degrade_to_v10(path: Path) -> None:
    """Quita solo chapter_offset para reproducir una BD v10 con el esquema real."""
    with sqlite3.connect(path) as connection:
        connection.execute("ALTER TABLE media_mappings DROP COLUMN chapter_offset")
        connection.execute("DELETE FROM schema_migrations")
        connection.execute("INSERT INTO schema_migrations(version) VALUES (10)")


def _recuentos_por_tabla(connection: sqlite3.Connection) -> dict[str, int]:
    tablas = [
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
        if row[0] != "schema_migrations"
    ]
    return {
        tabla: connection.execute(f'SELECT COUNT(*) FROM "{tabla}"').fetchone()[0]
        for tabla in tablas
    }


def test_nueva_database_declara_chapter_offset_entero_no_nulo_con_default_cero(monkeypatch):
    database = memory_database(monkeypatch)

    with database.connect() as connection:
        columnas = {
            row["name"]: row
            for row in connection.execute("PRAGMA table_info(media_mappings)").fetchall()
        }

    assert columnas["chapter_offset"]["type"] == "INTEGER"
    assert columnas["chapter_offset"]["notnull"] == 1
    assert columnas["chapter_offset"]["dflt_value"] == "0"


def test_v10_media_mappings_migra_sin_perder_filas_y_con_backup(tmp_path):
    path = tmp_path / "nyanko.sqlite3"
    Database(path).initialize()
    _degrade_to_v10(path)

    with sqlite3.connect(path) as connection:
        connection.execute(
            "INSERT INTO media_mappings(provider, site_identifier, media_id, episode_offset) "
            "VALUES ('crunchyroll', 'abc', 777, 3)"
        )
        recuentos_antes = _recuentos_por_tabla(connection)

    Database(path).initialize()

    with sqlite3.connect(path) as connection:
        columnas = {
            row[1]: row
            for row in connection.execute("PRAGMA table_info(media_mappings)").fetchall()
        }
        fila = connection.execute(
            "SELECT media_id, episode_offset, chapter_offset FROM media_mappings "
            "WHERE provider = 'crunchyroll' AND site_identifier = 'abc'"
        ).fetchone()
        assert columnas["chapter_offset"][2] == "INTEGER"
        assert columnas["chapter_offset"][3] == 1
        assert columnas["chapter_offset"][4] == "0"
        assert fila == (777, 3, 0)
        assert _recuentos_por_tabla(connection) == recuentos_antes
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] == 11

    backups = list(tmp_path.glob("nyanko.backup-v11-*.sqlite3"))
    assert len(backups) == 1, f"sin backup pre-migración: {list(tmp_path.iterdir())}"
    with sqlite3.connect(backups[0]) as backup:
        columnas_backup = {
            row[1] for row in backup.execute("PRAGMA table_info(media_mappings)").fetchall()
        }
        assert "chapter_offset" not in columnas_backup
        assert _recuentos_por_tabla(backup) == recuentos_antes
        assert backup.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] == 10


def test_set_chapter_progress_keeps_the_pair_coherent(monkeypatch):
    database = memory_database(monkeypatch)
    with database.connect() as connection:
        connection.execute("INSERT INTO media(id) VALUES (1)")
        connection.execute(
            "INSERT INTO library_entries(media_id, status, progress) VALUES (1, 'CURRENT', 9)"
        )

    database.set_chapter_progress(1, 10.5)

    with database.connect() as connection:
        row = connection.execute(
            "SELECT progress, chapter_progress FROM library_entries WHERE media_id = 1"
        ).fetchone()
    # El decimal sobrevive en local; el proveedor solo verá el floor.
    assert row["chapter_progress"] == 10.5
    assert row["progress"] == 10


def test_tracker_progress_reads_the_tracker_not_the_local_entry(monkeypatch):
    database = memory_database(monkeypatch)
    account_id = database.ensure_account("anilist", "default")
    with database.connect() as connection:
        connection.execute("INSERT INTO media(id) VALUES (1)")
        # A propósito DISTINTOS: el local ya lo movió la UI de forma optimista.
        connection.execute(
            "INSERT INTO library_entries(media_id, status, progress) VALUES (1, 'CURRENT', 3)"
        )
        connection.execute(
            "INSERT INTO remote_library_entries"
            "(account_id, media_id, status, progress, original_payload) "
            "VALUES (?, 1, 'CURRENT', 7, '{}')",
            (account_id,),
        )

    assert database.tracker_progress(1, account_id) == 7, "leyó el progreso LOCAL, no el del tracker"
    # Sin fila del tracker: desconocido. La guarda de progress.next_progress falla cerrado.
    assert database.tracker_progress(999, account_id) is None
