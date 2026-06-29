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
    _coerce_fuzzy_date,
    _get_playback_preferences,
    _playback_ready_for_auto_confirm,
    _refresh_mal_if_needed,
    _set_playback_preferences,
    app,
    confirm_playback,
    get_database,
    match_playback,
    pending_local_episodes,
)
from nyanko_api.normalizer import normalize_title
from nyanko_api.myanimelist import MyAnimeListCredential
from nyanko_api.secrets import get_provider_credential, set_provider_credential
from nyanko_api.models import (
    MediaDetails,
    MediaItem,
    PlaybackConfirmRequest,
    PlaybackMatchRequest,
    PlaybackPreferences,
    SearchFilters,
    SearchResult,
)
from nyanko_api.providers import ProviderCapabilities


def _playback_prefs(**kwargs) -> PlaybackPreferences:
    return PlaybackPreferences(**kwargs)


def test_coerce_fuzzy_date_accepts_strings_dicts_and_empty():
    # Regression: a stored ISO-string date crashed MediaListEntry rebuild with a 502.
    assert _coerce_fuzzy_date("2026-06-29").model_dump() == {"year": 2026, "month": 6, "day": 29}
    assert _coerce_fuzzy_date("2026").model_dump() == {"year": 2026, "month": None, "day": None}
    assert _coerce_fuzzy_date({"year": 2024, "month": 1, "day": 2}).year == 2024
    assert _coerce_fuzzy_date(None).model_dump() == {"year": None, "month": None, "day": None}
    assert _coerce_fuzzy_date("").year is None


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


def test_display_episode_clamps_movies_and_overflow():
    from nyanko_api.main import _display_episode

    movie = MediaItem(id=1, title="One Piece Film Red", status="COMPLETED", progress=0, episodes=1, format="MOVIE")
    series = MediaItem(id=2, title="One Piece", status="CURRENT", progress=0, episodes=1000)

    assert _display_episode(2022, movie) is None  # movie: a year-as-episode is dropped
    assert _display_episode(5, series) == 5  # within range, unchanged
    assert _display_episode(1500, series) == 1000  # never exceed the catalogue total
    assert _display_episode(None, series) is None
    assert _display_episode(3, None) == 3  # no match: leave as-is


def test_pending_local_only_lists_unwatched_episodes(database):
    item = MediaItem(
        id=1, title="Frieren", status="CURRENT", progress=5, episodes=12, format="TV",
    )
    mapping = database.sync_provider_library("anilist", "AniList", [item])
    media_id = mapping["1"]
    database.replace_local_files([
        {"path": "F/05.mkv", "media_id": media_id, "episode": 5, "parsed_title": "frieren"},
        {"path": "F/06.mkv", "media_id": media_id, "episode": 6, "parsed_title": "frieren"},
        {"path": "F/07.mkv", "media_id": media_id, "episode": 7, "parsed_title": "frieren"},
    ])

    pending = pending_local_episodes(database=database)

    assert len(pending) == 1
    assert pending[0].media_id == media_id
    assert pending[0].external_id == 1  # provider id, for opening details (not the canonical id)
    assert pending[0].next_episode == 6  # episode 5 already watched (progress = 5)
    assert pending[0].next_path == "F/06.mkv"  # path of the next unwatched episode, for play
    assert pending[0].available_count == 2  # episodes 6 and 7


def test_pending_local_empty_when_caught_up(database):
    item = MediaItem(id=2, title="Bocchi", status="CURRENT", progress=12, episodes=12)
    mapping = database.sync_provider_library("anilist", "AniList", [item])
    database.replace_local_files([
        {"path": "B/12.mkv", "media_id": mapping["2"], "episode": 12, "parsed_title": "bocchi"},
    ])

    assert pending_local_episodes(database=database) == []


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

    # Auto-update a tracked series ~20s into the episode, out of the box.
    assert preferences.auto_confirm is True
    assert preferences.progress_policy == "seconds"
    assert preferences.progress_seconds == 20
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


@pytest.mark.asyncio
async def test_confirming_an_episode_remembers_the_series(database, monkeypatch):
    class Provider:
        name = "anilist"
        display_name = "AniList"

        async def details(self, credential, media_id):
            return MediaDetails(
                id=media_id, title="Slime", synonyms=[], site_url="https://anilist.co/anime/7",
                status="RELEASING", episodes=24, genres=[], studios=[], score_format="POINT_100",
            )

        updates = []

        async def update_progress(self, credential, update):
            self.updates.append(update)
            return None

    provider = Provider()
    monkeypatch.setattr("nyanko_api.main._get_provider", lambda settings, _provider: provider)
    account_id = database.ensure_account("anilist", "default")
    event_id = database.insert_playback_event(
        source="browser",
        raw_title="Slime Season 4 Episode 1",
        anime_title="That Time I Got Reincarnated as a Slime Season 4",
        episode=1,
        status="pending",
        provider_id="anilist",
        account_id=account_id,
    )

    await confirm_playback(
        PlaybackConfirmRequest(
            event_id=event_id,
            media_id=7,
            progress=1,
            site_identifier="crunchyroll:slime:season-4:4",
            site_adapter="crunchyroll",
        ),
        token="token",
        settings=Settings(),
        database=database,
    )

    # A series not yet on the list is added as "Watching", not left status-less.
    assert provider.updates[0].status == "CURRENT"

    # The next episode of the same series now resolves by both stable signals.
    assert database.get_media_mapping("crunchyroll", "crunchyroll:slime:season-4:4") == (7, 0)
    assert database.get_match_correction(
        normalize_title("That Time I Got Reincarnated as a Slime Season 4")
    ) == 7


@pytest.mark.asyncio
async def test_playback_match_resolves_series_by_title_search(database, monkeypatch):
    from nyanko_api.models import GlobalSearchResponse

    class Provider:
        name = "anilist"
        display_name = "AniList"

        async def library(self, credential):
            return []

        async def discover(self, credential, filters):
            return GlobalSearchResponse(
                results=[
                    SearchResult(
                        id=55,
                        title="Tensei Shitara Slime Datta Ken",
                        title_english="That Time I Got Reincarnated as a Slime",
                        format="TV",
                        status="RELEASING",
                    )
                ],
                has_next_page=False,
            )

        async def details(self, credential, media_id):
            return MediaDetails(
                id=media_id, title="Tensei Shitara Slime Datta Ken", synonyms=[],
                site_url="https://anilist.co/anime/55", status="RELEASING", episodes=24,
                genres=[], studios=[], score_format="POINT_100",
            )

        async def update_progress(self, credential, update):
            raise AssertionError("a series not on the list must not be auto-added")

    monkeypatch.setattr("nyanko_api.main._get_provider", lambda settings, provider: Provider())

    response = await match_playback(
        PlaybackMatchRequest(
            source="browser",
            raw_title="That Time I Got Reincarnated as a Slime Season 4 Episode 1",
            anime_title="That Time I Got Reincarnated as a Slime",
            episode=1,
            content_kind="episode",
            position_seconds=120,  # well past the 20s auto-confirm threshold
            site_adapter="crunchyroll",
            site_identifier="crunchyroll:slime:season-4:4",
        ),
        token="token",
        settings=Settings(),
        database=database,
    )

    # Found by catalogue search even though it isn't on the user's list…
    assert response.match is not None
    assert response.match.id == 55
    # …but a series off the list is never auto-confirmed, even watched past the threshold:
    # adding it stays a deliberate action.
    assert response.event_status == "pending"
    # …and the strong title match was cached for instant continuity next episode.
    assert database.get_media_mapping("crunchyroll", "crunchyroll:slime:season-4:4") == (55, 0)


@pytest.mark.anyio
async def test_playback_match_prefers_catalogue_over_weak_library_guess(database, monkeypatch):
    from nyanko_api.models import GlobalSearchResponse

    # The library holds an unrelated completed series; the user is watching something not
    # on their list. A weak local hit must NOT be assumed — the catalogue resolves the
    # real series instead (regression: Wistoria matched Vinland Saga Season 2 at 56%).
    class Provider:
        name = "anilist"
        display_name = "AniList"

        async def library(self, credential):
            return [
                MediaItem(
                    id=10, title="Vinland Saga Season 2", status="COMPLETED",
                    progress=24, episodes=24, title_english="Vinland Saga Season 2",
                )
            ]

        async def discover(self, credential, filters):
            return GlobalSearchResponse(
                results=[
                    SearchResult(
                        id=77, title="Wistoria: Wand and Sword",
                        title_english="Wistoria: Wand and Sword", format="TV", status="RELEASING",
                    )
                ],
                has_next_page=False,
            )

        async def details(self, credential, media_id):
            return MediaDetails(
                id=media_id, title="Wistoria: Wand and Sword", synonyms=[],
                site_url="https://anilist.co/anime/77", status="RELEASING", episodes=12,
                genres=[], studios=[], score_format="POINT_100",
            )

        async def update_progress(self, credential, update):
            raise AssertionError("a series not on the list must not be auto-added")

    monkeypatch.setattr("nyanko_api.main._get_provider", lambda settings, provider: Provider())

    response = await match_playback(
        PlaybackMatchRequest(
            source="browser",
            raw_title="Wistoria Wand and Sword 1",
            anime_title="Wistoria: Wand and Sword",
            season=1,
            episode=1,
            content_kind="episode",
            position_seconds=150,
            site_adapter="jkanime",
            site_identifier="jkanime:wistoria-wand-and-sword",
        ),
        token="token",
        settings=Settings(),
        database=database,
    )

    assert response.match is not None
    assert response.match.id == 77  # Wistoria, from the catalogue — not Vinland (id 10)
    assert response.event_status == "pending"  # off-list series never auto-confirmed
    assert all(item.id != 10 for item in response.suggestions)  # no irrelevant suggestion


@pytest.mark.anyio
async def test_playback_match_trusts_catalogue_when_local_rescore_fails(database, monkeypatch):
    from nyanko_api.models import GlobalSearchResponse

    # The provider matched the page's English title server-side, but its result carries only
    # the Romaji title (English is null on AniList for this entry). Local re-scoring can't
    # bridge "Wistoria…" → "Tsue to Tsurugi…", yet the catalogue hit must still win and be
    # offered for confirmation (regression: panel said "Sin coincidencia").
    class Provider:
        name = "anilist"
        display_name = "AniList"

        async def library(self, credential):
            return []

        async def discover(self, credential, filters):
            return GlobalSearchResponse(
                results=[
                    SearchResult(
                        id=77, title="Tsue to Tsurugi no Wistoria",
                        title_romaji="Tsue to Tsurugi no Wistoria", title_english=None,
                        format="TV", status="RELEASING",
                    )
                ],
                has_next_page=False,
            )

        async def details(self, credential, media_id):
            return MediaDetails(
                id=media_id, title="Tsue to Tsurugi no Wistoria", synonyms=[], site_url="x",
                status="RELEASING", episodes=12, genres=[], studios=[], score_format="POINT_100",
            )

        async def update_progress(self, credential, update):
            raise AssertionError("off-list series must not be auto-added")

    monkeypatch.setattr("nyanko_api.main._get_provider", lambda settings, provider: Provider())

    response = await match_playback(
        PlaybackMatchRequest(
            source="browser", raw_title="Wistoria: Wand and Sword",
            anime_title="Wistoria: Wand and Sword", season=1, episode=1,
            content_kind="episode", position_seconds=150, site_adapter="jkanime",
            site_identifier="jkanime:wistoria",
        ),
        token="token", settings=Settings(), database=database,
    )

    assert response.match is not None
    assert response.match.id == 77  # resolved via the provider's top hit despite weak local score
    assert response.match_score < 0.85  # confirm-required, never auto-saved
    assert response.event_status == "pending"


@pytest.mark.anyio
async def test_rewatch_final_episode_completes_and_bumps_counter(database, monkeypatch):
    from nyanko_api.models import FuzzyDate, MediaEntryUpdate, MediaListEntry

    _set_playback_preferences(database, _playback_prefs(auto_confirm=True, progress_policy="always"))
    calls: dict[str, object] = {}

    class Provider:
        name = "anilist"
        display_name = "AniList"

        async def library(self, credential):
            # Mid-rewatch: status REPEATING, one episode short of the finale.
            return [MediaItem(id=5, title="Cowboy Bebop", status="REPEATING", progress=25, episodes=26)]

        async def details(self, credential, media_id):
            return MediaDetails(
                id=media_id, title="Cowboy Bebop", synonyms=[], site_url="x",
                status="FINISHED", episodes=26, genres=[], studios=[], score_format="POINT_100",
                list_entry=MediaListEntry(
                    id=1, status="REPEATING", score=0, progress=25, repeat=2, private=False,
                    started_at=FuzzyDate(), completed_at=FuzzyDate(),
                ),
            )

        async def update_progress(self, credential, update):
            raise AssertionError("the rewatch finale must go through edit_entry, not update_progress")

        async def edit_entry(self, credential, external_id, update: MediaEntryUpdate):
            calls["edit"] = update
            return MediaListEntry(
                id=1, status="COMPLETED", score=0, progress=26, repeat=update.repeat or 0,
                private=False, started_at=FuzzyDate(), completed_at=FuzzyDate(),
            )

    monkeypatch.setattr("nyanko_api.main._get_provider", lambda settings, provider: Provider())

    response = await match_playback(
        PlaybackMatchRequest(
            source="browser", raw_title="Cowboy Bebop 26", anime_title="Cowboy Bebop",
            episode=26, content_kind="episode", position_seconds=120,
            site_adapter="animeflv", site_identifier="animeflv:cowboy-bebop",
        ),
        token="token", settings=Settings(), database=database,
    )

    assert response.event_status == "confirmed"
    edit = calls["edit"]
    assert edit.status == "COMPLETED"
    assert edit.progress == 26
    assert edit.repeat == 3  # 2 previous rewatches + this one


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


def test_bulk_update_rejects_media_unlinked_to_active_account(monkeypatch, database):
    from fastapi.testclient import TestClient

    class FakeProvider:
        name = "anilist"
        display_name = "AniList"
        capabilities = None

        async def edit_entry(self, credential, external_id, update):
            return None

    monkeypatch.setattr("nyanko_api.main._get_provider", lambda settings, provider: FakeProvider())
    monkeypatch.setattr("nyanko_api.main.get_provider_credential", lambda provider, alias: "token")

    database.ensure_provider("anilist", "AniList")
    database.ensure_account("anilist", "default")
    app.dependency_overrides[get_database] = lambda: database

    try:
        with TestClient(app) as client:
            response = client.post("/api/library/bulk-update?media_id=1", json={"progress": 5})
    finally:
        app.dependency_overrides.pop(get_database, None)

    assert response.status_code == 404
    assert "no está vinculado" in response.text


def test_library_combined_view_uses_local_canonical_entries(database):
    from fastapi.testclient import TestClient

    database.sync_provider_library(
        "anilist",
        "AniList",
        [
            MediaItem(
                id=10,
                title="Sousou no Frieren",
                status="CURRENT",
                progress=12,
                episodes=28,
            )
        ],
    )
    app.dependency_overrides[get_database] = lambda: database

    try:
        with TestClient(app) as client:
            response = client.get("/api/library?view=combined")
    finally:
        app.dependency_overrides.pop(get_database, None)

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["canonical_id"] == database.canonical_media_id("anilist", 10)
    assert payload[0]["provider"] == "anilist"


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
    from nyanko_api.models import GlobalSearchResponse

    class FakeProvider:
        name = "anilist"
        display_name = "AniList"
        capabilities = ProviderCapabilities()

        async def discover(self, credential, filters):
            return GlobalSearchResponse(
                results=[
                    SearchResult(
                        id=1,
                        title="Popular Anime",
                        format="TV",
                        status="RELEASING",
                        episodes=12,
                        average_score=80,
                        popularity=5000,
                        cover_image=None,
                    )
                ],
                has_next_page=False,
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
            response = client.get("/api/search/media?q=Popular")
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
            response = client.get("/api/search/media?q=Popular&media_type=MANGA")
    finally:
        app.dependency_overrides.pop(get_database, None)

    assert response.status_code == 200
    data = response.json()
    assert len(data["results"]) == 1
    assert data["results"][0]["title"] == "Popular Manga"
    assert data["has_next_page"] is True


def test_discover_media_filters_query_against_alternative_titles(monkeypatch, database, tmp_path):
    from fastapi.testclient import TestClient
    from nyanko_api.models import GlobalSearchResponse

    class FakeProvider:
        name = "anilist"
        display_name = "AniList"
        capabilities = ProviderCapabilities()

        async def discover(self, credential, filters):
            return GlobalSearchResponse(
                results=[
                    SearchResult(
                        id=1,
                        title="Frieren: Beyond Journey's End",
                        title_romaji="Sousou no Frieren",
                        title_native="葬送のフリーレン",
                        format="TV",
                        status="RELEASING",
                        episodes=28,
                        average_score=90,
                        popularity=1000,
                        cover_image=None,
                        year=2023,
                        genres=["Adventure"],
                    )
                ],
                has_next_page=False,
            )

    monkeypatch.setattr(
        "nyanko_api.main._get_provider", lambda settings, provider: FakeProvider()
    )
    monkeypatch.setattr(
        "nyanko_api.main.get_settings", lambda: Settings(data_dir=tmp_path)
    )
    mal_token = '{"access_token":"token","refresh_token":null,"expires_at":9999999999}'
    monkeypatch.setattr(
        "nyanko_api.main.get_provider_credential", lambda provider, alias: mal_token
    )
    app.dependency_overrides[get_database] = lambda: database

    try:
        with TestClient(app) as client:
            response = client.get("/api/search/media?q=%E8%91%AC%E9%80%81%E3%81%AE%E3%83%95%E3%83%AA%E3%83%BC%E3%83%AC%E3%83%B3")
    finally:
        app.dependency_overrides.pop(get_database, None)

    assert response.status_code == 200
    assert len(response.json()["results"]) == 1


def test_discover_media_applies_filters_to_provider_results(monkeypatch, database, tmp_path):
    from fastapi.testclient import TestClient
    from nyanko_api.models import GlobalSearchResponse

    class FakeProvider:
        name = "mal"
        display_name = "MyAnimeList"
        capabilities = ProviderCapabilities()

        async def discover(self, credential, filters):
            return GlobalSearchResponse(
                results=[
                    SearchResult(
                        id=1,
                        title="Keep",
                        format="TV",
                        status="RELEASING",
                        episodes=12,
                        average_score=80,
                        popularity=100,
                        cover_image=None,
                        year=2024,
                        genres=["Action"],
                    ),
                    SearchResult(
                        id=2,
                        title="Drop",
                        format="MOVIE",
                        status="FINISHED",
                        episodes=1,
                        average_score=70,
                        popularity=200,
                        cover_image=None,
                        year=2023,
                        genres=["Drama"],
                    ),
                ],
                has_next_page=False,
            )

    monkeypatch.setattr(
        "nyanko_api.main._get_provider", lambda settings, provider: FakeProvider()
    )
    monkeypatch.setattr(
        "nyanko_api.main.get_settings", lambda: Settings(data_dir=tmp_path)
    )
    mal_token = '{"access_token":"token","refresh_token":null,"expires_at":9999999999}'
    monkeypatch.setattr(
        "nyanko_api.main.get_provider_credential", lambda provider, alias: mal_token
    )
    app.dependency_overrides[get_database] = lambda: database

    try:
        with TestClient(app) as client:
            response = client.get("/api/search/media?q=&provider=mal&format=TV&status=RELEASING&year=2024&genre=Action")
    finally:
        app.dependency_overrides.pop(get_database, None)

    assert response.status_code == 200
    payload = response.json()
    assert [item["title"] for item in payload["results"]] == ["Keep"]


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


# ---------------------------------------------------------------------------
# Torrent routes
# ---------------------------------------------------------------------------

_NYAA_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:nyaa="https://nyaa.si/xmlns/nyaa">
  <channel>
    <title>Nyaa</title>
    <item>
      <title>[SubsPlease] Frieren - 28 (1080p) [F00BAR12].mkv</title>
      <link>magnet:?xt=urn:btih:AAA&amp;dn=Frieren</link>
      <guid>https://nyaa.si/view/1000001</guid>
      <nyaa:seeders>120</nyaa:seeders>
    </item>
    <item>
      <title>[Erai-raws] Wistoria - Wand and Sword - 08 [720p][HEVC].mkv</title>
      <link>https://nyaa.si/download/1000002.torrent</link>
      <guid>https://nyaa.si/view/1000002</guid>
      <nyaa:seeders>33</nyaa:seeders>
    </item>
    <item>
      <title>[Group] Some Show S02E03 [2160p].mkv</title>
      <link>magnet:?xt=urn:btih:CCC</link>
      <guid>https://nyaa.si/view/1000003</guid>
    </item>
  </channel>
</rss>"""


@pytest.fixture
def client(database, monkeypatch):
    import nyanko_api.main as _main
    from fastapi.testclient import TestClient

    monkeypatch.setattr("nyanko_api.main.get_provider_credential", lambda provider, alias: "token")
    app.dependency_overrides[get_database] = lambda: database
    database.add_torrent_source("test-feed", "https://test/rss", True)
    # Clear module-level cache so tests don't bleed into each other.
    _main._torrent_link_cache.clear()
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.pop(get_database, None)


def test_torrent_sources_crud(client):
    created = client.post("/api/torrents/sources",
                          json={"name": "S", "url": "https://x/rss"}).json()
    assert created["name"] == "S"
    sid = created["id"]
    listed = client.get("/api/torrents/sources").json()
    assert any(s["id"] == sid for s in listed)
    client.put(f"/api/torrents/sources/{sid}",
               json={"name": "S2", "url": "https://x/rss2", "enabled": False})
    assert client.delete(f"/api/torrents/sources/{sid}").status_code == 204


def test_torrent_settings_roundtrip(client):
    body = {"auto_check": False, "interval_min": 30, "download_mode": "folder",
            "watch_folder": "/tmp/t", "preferred_resolution": "720p"}
    updated = client.put("/api/torrents/settings", json=body).json()
    assert updated["interval_min"] == 30
    assert client.get("/api/torrents/settings").json()["download_mode"] == "folder"


def test_torrent_feed_filters_to_new_episodes(client, monkeypatch):
    # Library with Frieren on CURRENT, progress 27.
    monkeypatch.setattr("nyanko_api.main._fetch_torrent_xml", lambda url: _NYAA_XML)

    async def _mock_lib(*a, **k):
        return [MediaItem(id=1, title="Frieren", status="CURRENT", progress=27)]

    monkeypatch.setattr("nyanko_api.main._load_library_for_torrents", _mock_lib)
    feed = client.get("/api/torrents/feed?refresh=true").json()
    assert any(it["media_title"] == "Frieren" and it["episode"] == 28 for it in feed)


def test_torrent_discard_then_excluded(client, monkeypatch):
    monkeypatch.setattr("nyanko_api.main._fetch_torrent_xml", lambda url: _NYAA_XML)

    async def _mock_lib(*a, **k):
        return [MediaItem(id=1, title="Frieren", status="CURRENT", progress=27)]

    monkeypatch.setattr("nyanko_api.main._load_library_for_torrents", _mock_lib)
    feed = client.get("/api/torrents/feed?refresh=true").json()
    assert len(feed) > 0, "feed must be non-empty for this test"
    sig = feed[0]["signature"]
    assert client.post("/api/torrents/discard", json={"signature": sig}).status_code == 204
    feed2 = client.get("/api/torrents/feed?refresh=true").json()
    assert all(it["signature"] != sig for it in feed2)


def test_torrent_unread_count(client):
    assert client.get("/api/torrents/unread-count").json() == {"count": 0}


def test_torrent_feed_refresh_param_wires_through(client, database, monkeypatch):
    """refresh=true bypasses the library cache; refresh=false does not call provider.library."""
    import nyanko_api.main as _main

    # Warm the library cache so refresh=false has something to read.
    warm_item = MediaItem(id=1, title="Frieren", status="CURRENT", progress=27)
    key = _main.account_cache_key("anilist", "default", "list")
    database.set_cache(key, [warm_item.model_dump(mode="json")], 300)

    call_count = {"n": 0}

    class _FakeProvider:
        name = "anilist"

        async def library(self, token):
            call_count["n"] += 1
            return [warm_item]

    monkeypatch.setattr("nyanko_api.main._get_provider", lambda s, p: _FakeProvider())
    monkeypatch.setattr("nyanko_api.main._fetch_torrent_xml", lambda url: _NYAA_XML)

    # Cache hit — provider.library must NOT be called.
    client.get("/api/torrents/feed?refresh=false")
    assert call_count["n"] == 0, "refresh=false must read from cache, not call provider.library"

    # Force refresh — provider.library MUST be called.
    client.get("/api/torrents/feed?refresh=true")
    assert call_count["n"] == 1, "refresh=true must bypass cache and call provider.library"

