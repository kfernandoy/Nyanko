import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

import pytest
from pydantic import ValidationError

from nyanko_api.config import Settings
from nyanko_api.database import Database
from nyanko_api.main import (
    _build_sync_status,
    _get_playback_preferences,
    _playback_ready_for_auto_confirm,
    _refresh_mal_if_needed,
    _set_playback_preferences,
    app,
    get_database,
    match_playback,
)
from nyanko_api.myanimelist import MyAnimeListCredential
from nyanko_api.secrets import get_provider_credential, set_provider_credential
from nyanko_api.models import (
    MediaDetails,
    MediaItem,
    PlaybackMatchRequest,
    PlaybackPreferences,
    SearchFilters,
    SearchResult,
)
from nyanko_api.providers import ProviderCapabilities


def _playback_prefs(**kwargs) -> PlaybackPreferences:
    return PlaybackPreferences(**kwargs)


@pytest.fixture
def database(monkeypatch):
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


def test_sync_status_returns_null_when_cache_is_empty(database):
    status = _build_sync_status(database, "anilist", "default", "WINTER", 2024)

    assert status.library.updated_at is None
    assert status.library.stale is False
    assert status.activity.updated_at is None
    assert status.statistics.updated_at is None
    assert status.season.updated_at is None


def test_sync_status_returns_cached_timestamps(database):
    before = int(time.time())
    database.set_cache("anilist:default:list", [], 3600)
    database.set_cache("anilist:default:activity", [], 3600)
    database.set_cache("anilist:default:statistics", {"count": 0}, 3600)
    database.set_cache(
        "anilist:default:season:WINTER:2024", [], 3600
    )

    status = _build_sync_status(database, "anilist", "default", "WINTER", 2024)

    assert status.library.updated_at is not None and status.library.updated_at >= before
    assert status.library.stale is False
    assert status.activity.updated_at is not None and status.activity.updated_at >= before
    assert status.statistics.updated_at is not None and status.statistics.updated_at >= before
    assert status.season.updated_at is not None and status.season.updated_at >= before


def test_playback_preferences_defaults(database):
    preferences = _get_playback_preferences(database)

    assert preferences.auto_confirm is False
    assert preferences.confidence_threshold == 0.85


def test_playback_preferences_round_trip(database):
    _set_playback_preferences(
        database, PlaybackPreferences(auto_confirm=True, confidence_threshold=0.75)
    )

    preferences = _get_playback_preferences(database)

    assert preferences.auto_confirm is True
    assert preferences.confidence_threshold == 0.75


def test_playback_history_accepts_failed_status(database):
    database.insert_playback_event(
        source="test", raw_title="test", anime_title="Test", episode=1, status="failed"
    )
    database.insert_playback_event(
        source="test", raw_title="test2", anime_title="Test 2", episode=2, status="confirmed"
    )

    events = database.get_recent_playback_events(limit=10, status="failed")

    assert len(events) == 1
    assert events[0]["status"] == "failed"


@pytest.mark.asyncio
async def test_playback_match_remembers_site_identifier(database, monkeypatch):
    class Provider:
        name = "anilist"
        display_name = "AniList"

        async def library(self, credential):
            return [
                MediaItem(
                    id=42,
                    title="Frieren",
                    status="CURRENT",
                    progress=0,
                    episodes=28,
                )
            ]

    monkeypatch.setattr("nyanko_api.main._get_provider", lambda settings, provider: Provider())

    first = await match_playback(
        PlaybackMatchRequest(
            source="browser",
            raw_title="Frieren Episode 12",
            anime_title="Frieren",
            episode=12,
            site_adapter="crunchyroll",
            site_identifier="crunchyroll:series:frieren",
        ),
        token="token",
        settings=Settings(),
        database=database,
    )
    second = await match_playback(
        PlaybackMatchRequest(
            source="browser",
            raw_title="Unrelated Episode 13",
            episode=13,
            site_adapter="crunchyroll",
            site_identifier="crunchyroll:series:frieren",
        ),
        token="token",
        settings=Settings(),
        database=database,
    )

    assert first.match is not None and first.match.id == 42
    assert database.get_media_mapping(
        "crunchyroll", "crunchyroll:series:frieren"
    ) == (42, 0)
    assert second.match is not None and second.match.id == 42
    assert second.match_score == 1.0


@pytest.mark.asyncio
async def test_playback_match_uses_mapped_anilist_media_outside_library(database, monkeypatch):
    class Provider:
        name = "anilist"
        display_name = "AniList"

        async def library(self, credential):
            return []

        async def details(self, credential, media_id):
            return MediaDetails(
                id=media_id,
                title="Frieren",
                synonyms=[],
                site_url="https://anilist.co/anime/99",
                status="FINISHED",
                episodes=28,
                genres=[],
                studios=[],
                score_format="POINT_100",
            )

    database.set_media_mapping("crunchyroll", "crunchyroll:series:frieren", 99)
    monkeypatch.setattr(
        "nyanko_api.main._get_provider", lambda settings, provider: Provider()
    )

    response = await match_playback(
        PlaybackMatchRequest(
            source="browser",
            raw_title="Unrelated Episode 13",
            episode=13,
            site_adapter="crunchyroll",
            site_identifier="crunchyroll:series:frieren",
        ),
        token="token",
        settings=Settings(),
        database=database,
    )

    assert response.match is not None
    assert response.match.id == 99
    assert response.match.title == "Frieren"
    assert response.match_score == 1.0


def test_sync_status_marks_expired_cache_as_stale(database):
    database.set_cache("anilist:default:list", [], -1)

    status = _build_sync_status(database, "anilist", "default", "WINTER", 2024)

    assert status.library.updated_at is not None
    assert status.library.stale is True


def test_playback_ready_for_auto_confirm_allows_sources_without_timing():
    request = PlaybackMatchRequest(
        source="active-window", raw_title="Frieren - 12", content_kind="episode"
    )
    assert _playback_ready_for_auto_confirm(request, _playback_prefs(auto_confirm=True)) is True


def test_bulk_update_skips_import_accounts_and_unlinked_media(monkeypatch, database):
    from fastapi.testclient import TestClient

    class FakeProvider:
        name = "anilist"
        display_name = "AniList"
        capabilities = None

        async def edit_entry(self, credential, external_id, update):
            return None

    _mal_json = '{"access_token":"t","refresh_token":null,"expires_at":9999999999}'
    monkeypatch.setattr("nyanko_api.main._get_provider", lambda settings, provider: FakeProvider())
    monkeypatch.setattr(
        "nyanko_api.main.get_provider_credential",
        lambda provider, alias: _mal_json if provider == "mal" else "token",
    )

    database.ensure_provider("anilist", "AniList")
    database.ensure_account("anilist", "default")
    database.ensure_provider("mal", "MyAnimeList")
    mal_account = database.ensure_account("mal", "default")
    database.update_account(mal_account, sync_direction="import")

    with TestClient(app) as client:
        response = client.post("/api/library/bulk-update?media_id=1", json={"progress": 5})

    assert response.status_code == 502
    assert "No se pudo guardar" in response.text


def test_playback_ready_for_auto_confirm_blocks_non_episodes():
    request = PlaybackMatchRequest(
        source="browser", raw_title="Frieren - 12", content_kind="trailer"
    )
    assert _playback_ready_for_auto_confirm(request, _playback_prefs(auto_confirm=True)) is False


def test_playback_ready_for_auto_confirm_allows_finished_playback():
    request = PlaybackMatchRequest(
        source="vlc",
        raw_title="Frieren - 12",
        content_kind="episode",
        position_seconds=30,
        duration_seconds=30,
        finished=True,
    )
    assert _playback_ready_for_auto_confirm(request, _playback_prefs(auto_confirm=True)) is True


def test_playback_ready_for_auto_confirm_respects_end_policy():
    request = PlaybackMatchRequest(
        source="vlc",
        raw_title="Frieren - 12",
        content_kind="episode",
        position_seconds=5,
        duration_seconds=100,
    )
    prefs = _playback_prefs(auto_confirm=True, progress_policy="end")
    assert _playback_ready_for_auto_confirm(request, prefs) is False

    request.position_seconds = 96
    assert _playback_ready_for_auto_confirm(request, prefs) is True

    request.position_seconds = 40
    request.duration_seconds = 95
    assert _playback_ready_for_auto_confirm(request, prefs) is True


def test_playback_ready_for_auto_confirm_respects_other_policies():
    base = PlaybackMatchRequest(
        source="vlc",
        raw_title="Frieren - 12",
        content_kind="episode",
        position_seconds=30,
        duration_seconds=100,
    )
    assert _playback_ready_for_auto_confirm(base, _playback_prefs(auto_confirm=True, progress_policy="always")) is True
    assert _playback_ready_for_auto_confirm(base, _playback_prefs(auto_confirm=True, progress_policy="never")) is False
    assert _playback_ready_for_auto_confirm(base, _playback_prefs(auto_confirm=True, progress_policy="start")) is True
    assert _playback_ready_for_auto_confirm(base, _playback_prefs(auto_confirm=True, progress_policy="middle")) is False
    base.position_seconds = 60
    assert _playback_ready_for_auto_confirm(base, _playback_prefs(auto_confirm=True, progress_policy="middle")) is True
    base.position_seconds = 30
    assert _playback_ready_for_auto_confirm(base, _playback_prefs(auto_confirm=True, progress_policy="seconds", progress_seconds=45)) is False
    assert _playback_ready_for_auto_confirm(base, _playback_prefs(auto_confirm=True, progress_policy="seconds", progress_seconds=20)) is True


def test_media_list_manga_endpoint(monkeypatch, database):
    from fastapi.testclient import TestClient

    class FakeProvider:
        name = "anilist"
        display_name = "AniList"
        capabilities = ProviderCapabilities(manga=True)

        async def library_manga(self, credential):
            return [
                MediaItem(
                    id=1,
                    title="Berserk",
                    status="CURRENT",
                    progress=5,
                    chapters=10,
                    volumes=2,
                    media_type="MANGA",
                )
            ]

    monkeypatch.setattr(
        "nyanko_api.main._get_provider", lambda settings, provider: FakeProvider()
    )
    monkeypatch.setattr(
        "nyanko_api.main.get_provider_credential", lambda provider, alias: "token"
    )
    app.dependency_overrides[get_database] = lambda: database

    try:
        with TestClient(app) as client:
            response = client.get("/api/library/manga")
    finally:
        app.dependency_overrides.pop(get_database, None)

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["media_type"] == "MANGA"
    assert data[0]["chapters"] == 10


def test_media_list_manga_rejects_provider_without_manga(monkeypatch, database):
    from fastapi.testclient import TestClient

    class FakeProvider:
        name = "mal"
        display_name = "MyAnimeList"
        capabilities = ProviderCapabilities(manga=False)

    _valid_mal = '{"access_token":"t","refresh_token":null,"expires_at":9999999999}'
    monkeypatch.setattr(
        "nyanko_api.main._get_provider", lambda settings, provider: FakeProvider()
    )
    monkeypatch.setattr(
        "nyanko_api.main.get_provider_credential", lambda provider, alias: _valid_mal
    )
    app.dependency_overrides[get_database] = lambda: database

    try:
        with TestClient(app) as client:
            response = client.get("/api/library/manga?provider=mal")
    finally:
        app.dependency_overrides.pop(get_database, None)

    assert response.status_code == 400


def test_manga_details_endpoint(monkeypatch, database):
    from fastapi.testclient import TestClient

    class FakeProvider:
        name = "anilist"
        display_name = "AniList"
        capabilities = ProviderCapabilities(manga=True)

        async def manga_details(self, credential, media_id):
            return MediaDetails(
                id=media_id,
                title="Berserk",
                synonyms=[],
                site_url="https://anilist.co/manga/1",
                status="FINISHED",
                media_type="MANGA",
                chapters=10,
                volumes=2,
                genres=[],
                studios=[],
                score_format="POINT_100",
            )

    monkeypatch.setattr(
        "nyanko_api.main._get_provider", lambda settings, provider: FakeProvider()
    )
    monkeypatch.setattr(
        "nyanko_api.main.get_provider_credential", lambda provider, alias: "token"
    )
    app.dependency_overrides[get_database] = lambda: database

    try:
        with TestClient(app) as client:
            response = client.get("/api/media/1/manga")
    finally:
        app.dependency_overrides.pop(get_database, None)

    assert response.status_code == 200
    data = response.json()
    assert data["media_type"] == "MANGA"
    assert data["chapters"] == 10


def test_search_manga_endpoint(monkeypatch, database):
    from fastapi.testclient import TestClient

    class FakeProvider:
        name = "anilist"
        display_name = "AniList"
        capabilities = ProviderCapabilities(manga=True)

        async def search_manga(self, credential, query, limit=10):
            return [
                SearchResult(
                    id=1,
                    title="Berserk",
                    format="MANGA",
                    status="FINISHED",
                    chapters=10,
                    volumes=2,
                    average_score=88,
                    popularity=1000,
                    cover_image=None,
                )
            ]

    monkeypatch.setattr(
        "nyanko_api.main._get_provider", lambda settings, provider: FakeProvider()
    )
    monkeypatch.setattr(
        "nyanko_api.main.get_provider_credential", lambda provider, alias: "token"
    )
    app.dependency_overrides[get_database] = lambda: database

    try:
        with TestClient(app) as client:
            response = client.get("/api/search/manga?q=Berserk")
    finally:
        app.dependency_overrides.pop(get_database, None)

    assert response.status_code == 200
    data = response.json()
    assert len(data["results"]) == 1
    assert data["results"][0]["title"] == "Berserk"


def test_search_manga_rejects_provider_without_manga(monkeypatch, database):
    from fastapi.testclient import TestClient

    class FakeProvider:
        name = "mal"
        display_name = "MyAnimeList"
        capabilities = ProviderCapabilities(manga=False)

    _valid_mal = '{"access_token":"t","refresh_token":null,"expires_at":9999999999}'
    monkeypatch.setattr(
        "nyanko_api.main._get_provider", lambda settings, provider: FakeProvider()
    )
    monkeypatch.setattr(
        "nyanko_api.main.get_provider_credential", lambda provider, alias: _valid_mal
    )
    app.dependency_overrides[get_database] = lambda: database

    try:
        with TestClient(app) as client:
            response = client.get("/api/search/manga?q=Berserk&provider=mal")
    finally:
        app.dependency_overrides.pop(get_database, None)

    assert response.status_code == 400


def test_discover_media_defaults_to_anime(monkeypatch, database):
    from fastapi.testclient import TestClient

    class FakeProvider:
        name = "anilist"
        display_name = "AniList"
        capabilities = ProviderCapabilities()

        async def discover(self, credential, filters):
            return {
                "results": [
                    SearchResult(
                        id=1,
                        title="Popular Anime",
                        format="TV",
                        status="RELEASING",
                        episodes=12,
                        average_score=80,
                        popularity=5000,
                        cover_image=None,
                    ).model_dump()
                ],
                "has_next_page": False,
            }

    monkeypatch.setattr(
        "nyanko_api.main._get_provider", lambda settings, provider: FakeProvider()
    )
    monkeypatch.setattr(
        "nyanko_api.main.get_provider_credential", lambda provider, alias: "token"
    )
    app.dependency_overrides[get_database] = lambda: database

    try:
        with TestClient(app) as client:
            response = client.get("/api/search/media?q=Naruto")
    finally:
        app.dependency_overrides.pop(get_database, None)

    assert response.status_code == 200
    data = response.json()
    assert len(data["results"]) == 1
    assert data["results"][0]["title"] == "Popular Anime"


def test_discover_media_supports_manga(monkeypatch, database):
    from fastapi.testclient import TestClient
    from nyanko_api.models import GlobalSearchResponse

    class FakeProvider:
        name = "anilist"
        display_name = "AniList"
        capabilities = ProviderCapabilities(manga=True)

        async def discover(self, credential, filters):
            assert filters.media_type == "MANGA"
            return GlobalSearchResponse(
                results=[
                    SearchResult(
                        id=2,
                        title="Popular Manga",
                        format="MANGA",
                        status="RELEASING",
                        chapters=100,
                        volumes=10,
                        average_score=85,
                        popularity=3000,
                        cover_image=None,
                    )
                ],
                has_next_page=True,
            )

    monkeypatch.setattr(
        "nyanko_api.main._get_provider", lambda settings, provider: FakeProvider()
    )
    monkeypatch.setattr(
        "nyanko_api.main.get_provider_credential", lambda provider, alias: "token"
    )
    app.dependency_overrides[get_database] = lambda: database

    try:
        with TestClient(app) as client:
            response = client.get("/api/search/media?q=Berserk&media_type=MANGA")
    finally:
        app.dependency_overrides.pop(get_database, None)

    assert response.status_code == 200
    data = response.json()
    assert len(data["results"]) == 1
    assert data["results"][0]["title"] == "Popular Manga"
    assert data["has_next_page"] is True


def test_discover_media_rejects_invalid_media_type(database, monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setattr(
        "nyanko_api.main.get_provider_credential", lambda provider, alias: "token"
    )
    app.dependency_overrides[get_database] = lambda: database

    try:
        with TestClient(app) as client:
            response = client.get("/api/search/media?q=Test&media_type=BOOK")
    finally:
        app.dependency_overrides.pop(get_database, None)

    assert response.status_code == 422


def _mal_credential(expired: bool) -> str:
    expires_at = int(time.time()) - 100 if expired else int(time.time()) + 86400
    return MyAnimeListCredential(
        access_token="old-token",
        refresh_token="refresh-token",
        expires_at=expires_at,
    ).dumps()


@pytest.mark.asyncio
async def test_refresh_mal_if_needed_skips_non_mal():
    token = _mal_credential(expired=True)
    result = await _refresh_mal_if_needed("anilist", "default", token, Settings())
    assert result == token


@pytest.mark.asyncio
async def test_refresh_mal_if_needed_no_op_when_valid():
    token = _mal_credential(expired=False)
    result = await _refresh_mal_if_needed("mal", "default", token, Settings())
    assert result == token


@pytest.mark.asyncio
async def test_refresh_mal_if_needed_refreshes_expired(monkeypatch):
    new_cred = MyAnimeListCredential(
        access_token="new-token",
        refresh_token="new-refresh",
        expires_at=int(time.time()) + 86400,
    )

    class FakeMALClient:
        async def refresh(self, credential):
            assert credential.refresh_token == "refresh-token"
            return new_cred

    monkeypatch.setattr("nyanko_api.main.MyAnimeListClient", lambda settings: FakeMALClient())

    expired_token = _mal_credential(expired=True)
    set_provider_credential("mal", "default", expired_token)

    result = await _refresh_mal_if_needed("mal", "default", expired_token, Settings())

    assert MyAnimeListCredential.loads(result).access_token == "new-token"
    stored = get_provider_credential("mal", "default")
    assert MyAnimeListCredential.loads(stored).access_token == "new-token"


def test_search_filters_rejects_invalid_sort():
    with pytest.raises(ValidationError):
        SearchFilters(sort="INVALID")


def test_search_filters_accepts_valid_sort():
    assert SearchFilters(sort="POPULARITY").sort == "POPULARITY"
    assert SearchFilters(sort="SCORE").sort == "SCORE"
    assert SearchFilters().sort == "POPULARITY"
