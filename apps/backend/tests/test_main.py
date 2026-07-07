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
    _local_asset_url,
    _localize_media_details_assets,
    _missing_detail_assets,
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
    RecommendationItem,
    RelationEdge,
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


def test_local_asset_helpers_prefer_downloaded_files(monkeypatch):
    settings = Settings()
    details = MediaDetails(
        id=42,
        title="Example",
        synonyms=[],
        site_url="https://example.test/42",
        cover_image="https://remote/cover.jpg",
        banner_image="https://remote/banner.jpg",
        genres=[],
        studios=[],
        score_format="POINT_10",
        relations=[
            RelationEdge(id=7, title="Related", format="TV", relation_type="SEQUEL", cover_image="https://remote/rel.jpg")
        ],
        recommendations=[
            RecommendationItem(id=8, title="Recommended", format="TV", cover_image="https://remote/rec.jpg", rating=1)
        ],
    )

    def fake_find(_settings, _provider, _external_id, stem):
        if stem == "cover":
            return "cover.jpg"
        return "banner.png" if int(_external_id) == 42 else None

    monkeypatch.setattr("nyanko_api.main._find_local_asset_filename", fake_find)

    assert _local_asset_url(settings, "anilist", 42, "cover") == "http://127.0.0.1:8765/assets/anilist/42/cover.jpg"
    localized_details = _localize_media_details_assets(settings, "anilist", details)

    assert localized_details.cover_image == "http://127.0.0.1:8765/assets/anilist/42/cover.jpg"
    assert localized_details.banner_image == "http://127.0.0.1:8765/assets/anilist/42/banner.png"
    assert localized_details.relations[0].cover_image == "http://127.0.0.1:8765/assets/anilist/7/cover.jpg"
    assert localized_details.recommendations[0].cover_image == "http://127.0.0.1:8765/assets/anilist/8/cover.jpg"

    monkeypatch.setattr(
        "nyanko_api.main._find_local_asset_filename",
        lambda _settings, _provider, _external_id, stem: "cover.jpg" if stem == "cover" else None,
    )
    assert _missing_detail_assets(settings, "anilist", 42, details) is True


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
        "anilist:default:season:v3:WINTER:2024", [], 3600
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
async def test_confirming_learns_seasonal_episode_offset(database, monkeypatch):
    """Crunchyroll numera por temporada (Season 22 ep 76) pero AniList es absoluto (1152).
    Al confirmar el episodio absoluto, se aprende el offset ligado a la temporada."""
    class Provider:
        name = "anilist"
        display_name = "AniList"

        async def details(self, credential, media_id):
            return MediaDetails(
                id=media_id, title="One Piece", synonyms=[],
                site_url="https://anilist.co/anime/21", status="RELEASING",
                episodes=None, genres=[], studios=[], score_format="POINT_100",
            )

        updates = []

        async def update_progress(self, credential, update):
            self.updates.append(update)
            return None

    provider = Provider()
    monkeypatch.setattr("nyanko_api.main._get_provider", lambda settings, _provider: provider)
    account_id = database.ensure_account("anilist", "default")
    event_id = database.insert_playback_event(
        source="browser", raw_title="One Piece Season 22 Episode 76",
        anime_title="One Piece Season 22", episode=76, status="pending",
        provider_id="anilist", account_id=account_id,
    )

    await confirm_playback(
        PlaybackConfirmRequest(
            event_id=event_id, media_id=21, progress=1152,
            site_identifier="series:one-piece:s22", site_adapter="crunchyroll",
        ),
        token="token", settings=Settings(), database=database,
    )

    # offset = 1152 (absoluto confirmado) - 76 (detectado) = 1076, ligado a la temporada.
    assert database.get_media_mapping("crunchyroll", "series:one-piece:s22") == (21, 1076)


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


def test_bulk_update_applies_locally_and_enqueues(client, database):
    database.sync_provider_library("anilist", "AniList", [
        MediaItem(id=10, title="Frieren", status="CURRENT", progress=3, episodes=28),
    ])
    canonical = database.canonical_media_id("anilist", 10)

    resp = client.post(f"/api/library/bulk-update?media_id={canonical}", json={"progress": 4})
    assert resp.status_code == 200
    assert resp.json()["results"][0]["success"] is True

    # Efecto local inmediato…
    with database.connect() as connection:
        progress = connection.execute(
            "SELECT progress FROM remote_library_entries WHERE media_id = ?", (canonical,)
        ).fetchone()["progress"]
    assert progress == 4
    # …mutación encolada y visible en el overlay…
    pending = database.due_mutations(int(__import__("time").time()) + 1)
    assert len(pending) == 1
    assert pending[0]["kind"] == "edit_entry"
    assert database.pending_mutation_overrides("anilist", "default") == {"10": {"progress": 4}}
    # …y con evento en el historial.
    event = database.get_playback_event(pending[0]["event_id"])
    assert event["status"] == "pending"
    assert event["source"] == "edit"


def test_bulk_update_completed_fills_progress_and_dates(client, database):
    import json as _json
    from datetime import date as _date

    database.sync_provider_library("anilist", "AniList", [
        MediaItem(id=10, title="Frieren", status="CURRENT", progress=3, episodes=28),
    ])
    canonical = database.canonical_media_id("anilist", 10)

    resp = client.post(
        f"/api/library/bulk-update?media_id={canonical}", json={"status": "COMPLETED"}
    )
    assert resp.status_code == 200

    today = _date.today()
    fuzzy_today = {"year": today.year, "month": today.month, "day": today.day}
    payload = _json.loads(database.due_mutations(int(time.time()) + 1)[0]["payload"])
    assert payload["progress"] == 28          # completar rellena hasta el total
    assert payload["completed_at"] == fuzzy_today
    assert payload["started_at"] == fuzzy_today  # la entrada no tenía fecha de inicio

    # La copia local refleja las fechas al instante (como texto, el formato del
    # payload), sin esperar al resync.
    today_text = today.strftime("%Y-%m-%d")
    with database.connect() as connection:
        local = _json.loads(connection.execute(
            "SELECT original_payload FROM remote_library_entries WHERE media_id = ?",
            (canonical,),
        ).fetchone()["original_payload"])
    assert local["completed_at"] == today_text
    assert local["started_at"] == today_text

    # Y la vista combinada sigue validando como MediaItem (una fecha en formato
    # dict aquí rompía toda la biblioteca local).
    combined = database.get_combined_library("ANIME", "anilist", "default")
    item = MediaItem.model_validate(combined[0])
    assert item.completed_at == today_text


def test_mutation_worker_drains_and_confirms(client, database, monkeypatch):
    import nyanko_api.main as main_module
    from nyanko_api.config import Settings

    database.sync_provider_library("anilist", "AniList", [
        MediaItem(id=10, title="Frieren", status="CURRENT", progress=3, episodes=28),
    ])
    client.post("/api/library/bulk-update?media_id="
                f"{database.canonical_media_id('anilist', 10)}", json={"progress": 4})
    sent = []

    async def fake_send(settings, row):
        sent.append(row["kind"])

    monkeypatch.setattr(main_module, "_send_mutation", fake_send)
    worker = main_module.MutationWorker(Settings())
    worker._drain(database)

    assert sent == ["edit_entry"]
    assert database.due_mutations(int(__import__("time").time()) + 1) == []
    events = database.get_recent_playback_events()
    assert events[0]["status"] == "confirmed"


def test_mutation_worker_backoff_and_final_failure(client, database, monkeypatch):
    import nyanko_api.main as main_module
    from nyanko_api.config import Settings

    database.sync_provider_library("anilist", "AniList", [
        MediaItem(id=10, title="Frieren", status="CURRENT", progress=3, episodes=28),
    ])
    client.post("/api/library/bulk-update?media_id="
                f"{database.canonical_media_id('anilist', 10)}", json={"progress": 4})

    async def failing_send(settings, row):
        raise RuntimeError("proveedor caído")

    monkeypatch.setattr(main_module, "_send_mutation", failing_send)
    worker = main_module.MutationWorker(Settings())
    worker._drain(database)

    # Primer fallo: backoff, sigue pendiente pero no due.
    now = int(__import__("time").time())
    assert database.due_mutations(now) == []
    with database.connect() as connection:
        row = connection.execute("SELECT * FROM pending_mutations").fetchone()
    assert row["status"] == "pending" and row["attempts"] == 1

    # Agotar los reintentos → failed + evento failed + requeue posible.
    with database.connect() as connection:
        connection.execute(
            "UPDATE pending_mutations SET attempts = ?, next_attempt_at = 0",
            (main_module.MUTATION_MAX_ATTEMPTS - 1,),
        )
    worker._drain(database)
    with database.connect() as connection:
        row = connection.execute("SELECT * FROM pending_mutations").fetchone()
    assert row["status"] == "failed"
    event = database.get_playback_event(row["event_id"])
    assert event["status"] == "failed"
    assert database.requeue_mutation_by_event(row["event_id"]) is True


def test_auto_download_new_saves_torrent_files(monkeypatch, database, tmp_path):
    import nyanko_api.main as main_module
    from nyanko_api import torrents as torrents_mod

    database.set_setting("torrent_on_new", "download")
    database.set_setting("torrent_download_mode", "folder")
    database.set_setting("torrent_watch_folder", str(tmp_path))

    class FakeResponse:
        content = b"torrent-bytes"
        def raise_for_status(self): pass

    monkeypatch.setattr(main_module.httpx, "get", lambda *a, **k: FakeResponse())
    item = torrents_mod.FeedItem(
        signature="sig1", raw_title="[Grp] Frieren - 28.mkv", link="https://x/f.torrent",
        media_id=1, media_title="Frieren", episode=28, resolution="1080p",
        group="Grp", seeders=5, is_new=True,
    )
    downloaded = main_module._auto_download_new(database, [item])

    assert downloaded == 1
    assert (tmp_path / "sig1.torrent").read_bytes() == b"torrent-bytes"
    # Marcado como descargado: el próximo chequeo ya no lo tratará como nuevo.
    with database.connect() as connection:
        row = connection.execute(
            "SELECT downloaded FROM torrent_seen WHERE signature = 'sig1'"
        ).fetchone()
    assert row["downloaded"] == 1


def test_library_watcher_rescans_only_when_files_change(monkeypatch, database, tmp_path):
    import nyanko_api.main as main_module
    from nyanko_api.config import Settings

    (tmp_path / "Frieren - 01.mkv").write_bytes(b"x")
    database.add_library_folder(str(tmp_path), True)
    database.set_setting(main_module.SCAN_WATCH_KEY, "1")
    scans = []
    monkeypatch.setattr(main_module, "run_library_scan", lambda db: scans.append(1))

    watcher = main_module.LibraryWatcher(Settings())
    # Primera pasada: línea base, sin escaneo.
    watcher._signature = None
    signature = watcher._compute_signature(database)
    watcher._signature = signature
    assert watcher._compute_signature(database) == signature

    # Aparece un archivo → la firma cambia.
    (tmp_path / "Frieren - 02.mkv").write_bytes(b"y")
    assert watcher._compute_signature(database) != signature


def test_media_details_serves_local_skeleton_without_cache(client, database, monkeypatch):
    """Primer acceso al detalle sin caché: responde al instante con datos locales
    (portada, títulos, entrada editable) y baja el detalle completo en segundo plano."""
    class Provider:
        name = "anilist"
        display_name = "AniList"

        async def details(self, credential, media_id):
            return MediaDetails(
                id=media_id, title="Frieren", synonyms=[], site_url="https://x",
                genres=[], studios=[], score_format="POINT_100",
            )

    monkeypatch.setattr("nyanko_api.main._get_provider", lambda settings, _p: Provider())
    database.sync_provider_library("anilist", "AniList", [
        MediaItem(id=10, title="Frieren", status="CURRENT", progress=3,
                  episodes=28, cover_image="https://img/f.jpg"),
    ])

    resp = client.get("/api/media/10")
    assert resp.status_code == 200
    assert resp.headers["X-Cache-Status"] == "stale"
    body = resp.json()
    assert body["title"] == "Frieren"
    assert body["cover_image"] == "https://img/f.jpg"
    assert body["list_entry"]["progress"] == 3


def test_local_library_fallback_is_scoped_to_active_provider(database):
    """Sin caché de red, la vista por proveedor debe mostrar SOLO la biblioteca del
    proveedor activo, no la unión de todas las cuentas (regresión: se mezclaban las 3)."""
    from nyanko_api.config import Settings
    from nyanko_api.main import _local_library_items

    database.sync_provider_library("anilist", "AniList", [
        MediaItem(id=1, title="Frieren (AL)", status="CURRENT", progress=1, episodes=28),
    ])
    database.sync_provider_library("mal", "MyAnimeList", [
        MediaItem(id=100, title="Bleach (MAL)", status="CURRENT", progress=1, episodes=366),
    ])

    scoped = _local_library_items(database, Settings(), "anilist", "default", "ANIME", scoped=True)
    combined = _local_library_items(database, Settings(), "anilist", "default", "ANIME", scoped=False)

    assert {i.title for i in scoped} == {"Frieren (AL)"}
    assert {i.title for i in combined} == {"Frieren (AL)", "Bleach (MAL)"}


def test_warm_library_details_backfills_missing_via_batch(database, monkeypatch):
    """El warmer baja en segundo plano los detalles que faltan (para que la primera
    apertura de una card salga completa), en lote y sin re-pedir los ya persistidos."""
    import asyncio

    import nyanko_api.main as main_module
    from nyanko_api.providers import ProviderCapabilities

    batch_calls = []

    def make_details(media_id):
        return MediaDetails(
            id=media_id, title=f"Media {media_id}", synonyms=[], site_url="https://x",
            description="Sinopsis", genres=[], studios=["Ghibli"], score_format="POINT_100",
        )

    class Provider:
        name = "anilist"
        display_name = "AniList"
        capabilities = ProviderCapabilities(batch_details=True)

        async def details_batch(self, credential, media_ids):
            batch_calls.append(list(media_ids))
            return [make_details(mid) for mid in media_ids]

    monkeypatch.setattr(main_module, "_get_provider", lambda settings, _p: Provider())
    items = [
        MediaItem(id=10, title="Frieren", status="CURRENT", progress=3, episodes=28),
        MediaItem(id=11, title="Mononoke", status="COMPLETED", progress=1, episodes=1),
    ]
    database.sync_media_details("anilist", 11, make_details(11))  # el 11 ya está completo

    async def scenario():
        main_module._warm_library_details(
            database, Settings(), "anilist", "default", items, "token"
        )
        task = main_module._library_detail_warmers.get(
            (str(database.path), "anilist", "default", "ANIME")
        )
        assert task is not None
        await task

    asyncio.run(scenario())

    assert batch_calls == [[10]]  # solo el faltante, en una sola llamada por lotes
    canonical = database.canonical_media_id("anilist", 10)
    persisted = database.get_persisted_media_details("anilist", canonical)
    assert persisted is not None
    assert persisted.description == "Sinopsis"


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


def _async_return(value):
    """Wrap a value in an async callable — reuses the established mock pattern."""
    async def _inner(*a, **k):
        return value
    return _inner


@pytest.fixture
def client(database, monkeypatch):
    import nyanko_api.main as _main
    from fastapi.testclient import TestClient

    monkeypatch.setattr("nyanko_api.main.get_provider_credential", lambda provider, alias: "token")
    # Prevent the real background checker from spinning up against the on-disk DB.
    monkeypatch.setattr("nyanko_api.main.TorrentChecker.start", lambda self: None)
    app.dependency_overrides[get_database] = lambda: database
    database.add_torrent_source("test-feed", "https://test/rss", True)
    # Clear module-level caches so tests don't bleed into each other.
    _main._torrent_link_cache.clear()
    _main._torrent_item_cache.clear()
    _main._torrent_unread["count"] = 0
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.pop(get_database, None)


def test_local_library_endpoint(client):
    resp = client.get("/api/library/local")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_local_library_enriches_matched_series(client, database):
    from nyanko_api.models import MediaItem

    database.sync_provider_library("anilist", "AniList", [
        MediaItem(id=7, title="Sousou no Frieren", status="CURRENT", progress=1,
                  episodes=28, cover_image="https://img/frieren.jpg"),
    ])
    media_id = database.canonical_media_id("anilist", 7)
    database.replace_local_files([
        {"path": "/a/frieren-01.mkv", "media_id": media_id, "episode": 1, "parsed_title": "frieren"},
        {"path": "/a/frieren-02.mkv", "media_id": media_id, "episode": 2, "parsed_title": "frieren"},
        {"path": "/a/bocchi-01.mkv", "media_id": None, "episode": 1, "parsed_title": "bocchi"},
    ])
    items = {s["title"]: s for s in client.get("/api/library/local").json()}

    frieren = items["Sousou no Frieren"]
    assert frieren["external_id"] == 7
    assert frieren["cover_image"] == "https://img/frieren.jpg"
    assert frieren["progress"] == 1
    assert frieren["episodes"] == 28
    assert frieren["next_episode"] == 2  # progreso 1 → siguiente local sin ver
    assert frieren["next_path"] == "/a/frieren-02.mkv"

    bocchi = items["bocchi"]
    assert bocchi["matched"] is False
    assert bocchi["external_id"] is None
    assert bocchi["next_path"] is None  # sin media_id no hay episodio reproducible


def test_local_library_movie_without_episode_gets_play_button(client, database):
    from nyanko_api.models import MediaItem

    database.sync_provider_library("anilist", "AniList", [
        MediaItem(id=5, title="Kimi no Na wa.", status="PLANNING", progress=0, episodes=1),
    ])
    media_id = database.canonical_media_id("anilist", 5)
    # Película: el parser no extrae número de episodio.
    database.replace_local_files([
        {"path": "/a/kimi-no-na-wa.mkv", "media_id": media_id, "episode": None, "parsed_title": "Kimi no Na wa"},
    ])
    item = client.get("/api/library/local").json()[0]
    assert item["next_episode"] == 1
    assert item["next_path"] == "/a/kimi-no-na-wa.mkv"


def test_local_associate_and_unlink(client, database):
    from nyanko_api.models import MediaItem

    database.sync_provider_library("anilist", "AniList", [
        MediaItem(id=9, title="Dungeon Meshi", status="CURRENT", progress=0, episodes=24),
    ])
    canonical = database.canonical_media_id("anilist", 9)
    database.replace_local_files([
        {"path": "/a/dm-01.mkv", "media_id": None, "episode": 1, "parsed_title": "Dungeon Meshi"},
    ])

    resp = client.post("/api/library/local/associate",
                       json={"title": "Dungeon Meshi", "external_id": 9})
    assert resp.status_code == 204
    item = client.get("/api/library/local").json()[0]
    assert item["matched"] is True
    assert item["media_id"] == canonical
    # La corrección persiste con la clave normalizada que consulta el escaneo.
    assert database.get_local_match_overrides() == {normalize_title("Dungeon Meshi"): canonical}

    resp = client.post("/api/library/local/associate",
                       json={"title": item["title"], "from_media_id": canonical})
    assert resp.status_code == 204
    item = client.get("/api/library/local").json()[0]
    assert item["matched"] is False
    assert database.get_local_match_overrides() == {}


def test_local_associate_adds_to_list_when_canonical_exists_without_entry(client, database, monkeypatch):
    """Caso Dungeon Meshi: el id canónico ya existe (p. ej. por abrir el detalle) pero
    la obra no está en la lista. Asociar debe agregarla igualmente al proveedor."""
    from nyanko_api.models import MediaItem

    updates = []

    class Provider:
        name = "anilist"
        display_name = "AniList"

        async def update_progress(self, credential, update):
            updates.append(update)
            return {"id": 1}

    monkeypatch.setattr("nyanko_api.main._get_provider", lambda settings, _provider: Provider())
    # Canónico + identidad externa sin entrada de biblioteca (huérfano).
    database.sync_provider_library("anilist", "AniList", [
        MediaItem(id=9, title="Dungeon Meshi", status="CURRENT", progress=0, episodes=24),
    ])
    with database.connect() as connection:
        connection.execute("DELETE FROM remote_library_entries")
        connection.execute("DELETE FROM library_entries")
    database.replace_local_files([
        {"path": "/a/dm-01.mkv", "media_id": None, "episode": 1, "parsed_title": "Dungeon Meshi"},
    ])

    resp = client.post("/api/library/local/associate", json={
        "title": "Dungeon Meshi",
        "external_id": 9,
        "status": "CURRENT",
        "media": {"id": 9, "title": "Dungeon Meshi", "episodes": 24,
                  "cover_image": "https://img/dm.jpg", "format": "TV",
                  "status": "FINISHED", "average_score": 88, "popularity": 1000},
    })
    assert resp.status_code == 204
    assert len(updates) == 1 and updates[0].status == "CURRENT"
    item = client.get("/api/library/local").json()[0]
    assert item["matched"] is True
    assert item["cover_image"] == "https://img/dm.jpg"
    assert item["external_id"] == 9


def test_local_associate_adds_to_provider_when_missing(client, database, monkeypatch):
    """Asociar una obra del catálogo que no está en la lista la agrega al proveedor
    con el estado elegido y la registra localmente de inmediato."""
    updates = []

    class Provider:
        name = "anilist"
        display_name = "AniList"

        async def update_progress(self, credential, update):
            updates.append(update)
            return {"id": 1}

    monkeypatch.setattr("nyanko_api.main._get_provider", lambda settings, _provider: Provider())
    database.replace_local_files([
        {"path": "/a/dm-01.mkv", "media_id": None, "episode": 1, "parsed_title": "Dungeon Meshi"},
    ])

    resp = client.post("/api/library/local/associate", json={
        "title": "Dungeon Meshi",
        "external_id": 9,
        "status": "CURRENT",
        "media": {"id": 9, "title": "Dungeon Meshi", "episodes": 24,
                  "cover_image": "https://img/dm.jpg", "format": "TV",
                  "status": "FINISHED", "average_score": 88, "popularity": 1000},
    })
    assert resp.status_code == 204
    assert len(updates) == 1
    assert updates[0].media_id == 9
    assert updates[0].status == "CURRENT"

    canonical = database.canonical_media_id("anilist", 9)
    assert canonical is not None
    item = client.get("/api/library/local").json()[0]
    assert item["matched"] is True
    assert item["media_id"] == canonical
    assert item["cover_image"] == "https://img/dm.jpg"
    assert item["progress"] == 0
    assert database.get_local_match_overrides() == {normalize_title("Dungeon Meshi"): canonical}


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


def test_torrent_on_new_setting(client):
    body = client.get("/api/torrents/settings").json()
    body["on_new"] = "download"
    assert client.put("/api/torrents/settings", json=body).json()["on_new"] == "download"


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


def test_torrent_unread_counts_new(monkeypatch, tmp_path):
    import asyncio
    from nyanko_api import main as main_mod
    monkeypatch.setattr(main_mod, "_fetch_torrent_xml", lambda url: _NYAA_XML)
    # Use an isolated tmp database so the real disk DB is not polluted.
    db = main_mod.Database(tmp_path / "test.sqlite3")
    db.initialize()
    db.add_torrent_source("test-feed", "https://test/rss", True)
    # biblioteca cacheada para anilist/default
    db.set_cache(main_mod.account_cache_key("anilist", "default", "list"),
                 [MediaItem(id=1, title="Frieren", status="CURRENT", progress=27).model_dump(mode="json")],
                 300)
    db.ensure_account("anilist", "default")
    count = asyncio.run(main_mod._torrent_check_once(db))
    assert count >= 1


def test_torrent_feed_clears_unread_badge(client, monkeypatch):
    """Viewing the feed must reset the nav-badge count to 0."""
    import nyanko_api.main as _main
    monkeypatch.setattr("nyanko_api.main._fetch_torrent_xml", lambda url: _NYAA_XML)

    async def _mock_lib(*a, **k):
        return [MediaItem(id=1, title="Frieren", status="CURRENT", progress=27)]

    monkeypatch.setattr("nyanko_api.main._load_library_for_torrents", _mock_lib)

    # Simulate the background checker having set a non-zero unread count.
    _main._torrent_unread["count"] = 5

    client.get("/api/torrents/feed?refresh=true")
    assert client.get("/api/torrents/unread-count").json() == {"count": 0}


def test_torrent_filter_taiga_crud(client):
    body = {
        "name": "Solo SubsPlease 1080p", "action": "select", "match": "all", "scope": "all",
        "enabled": True,
        "conditions": [{"element": "group", "operator": "is", "value": "SubsPlease"},
                       {"element": "resolution", "operator": "equals", "value": "1080p"}],
        "anime_ids": [],
    }
    created = client.post("/api/torrents/filters", json=body).json()
    assert created["name"] == "Solo SubsPlease 1080p"
    assert created["action"] == "select"
    assert len(created["conditions"]) == 2
    fid = created["id"]
    listed = client.get("/api/torrents/filters").json()
    assert any(f["id"] == fid for f in listed)
    updated_body = {**body, "name": "Solo SubsPlease 1080p v2", "enabled": False}
    updated = client.put(f"/api/torrents/filters/{fid}", json=updated_body).json()
    assert updated["name"] == "Solo SubsPlease 1080p v2" and not updated["enabled"]
    assert client.delete(f"/api/torrents/filters/{fid}").status_code == 204
    assert all(f["id"] != fid for f in client.get("/api/torrents/filters").json())


def test_torrent_download_folder_mode_empty_watch_folder(client):
    """download_mode=folder with blank watch_folder must return 400, not write to CWD."""
    import nyanko_api.main as _main
    from nyanko_api import torrents as torrents_mod

    client.put("/api/torrents/settings", json={
        "auto_check": False, "interval_min": 60, "download_mode": "folder",
        "watch_folder": "", "preferred_resolution": "1080p",
    })
    # Inject a .torrent link into the cache (Wistoria item, source_id=1).
    sig = torrents_mod.signature(1, "https://nyaa.si/view/1000002")
    _main._torrent_link_cache[sig] = "https://nyaa.si/download/1000002.torrent"

    resp = client.post("/api/torrents/download", json={"signature": sig})
    assert resp.status_code == 400


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


def test_torrent_download_settings_roundtrip(client):
    body = client.get("/api/torrents/settings").json()
    body.update(folder_per_series=True, append_episode=True, client_path="C:/qbit.exe")
    out = client.put("/api/torrents/settings", json=body).json()
    assert out["folder_per_series"] and out["append_episode"] and out["client_path"] == "C:/qbit.exe"


def test_torrent_download_folder_per_series(client, monkeypatch, tmp_path):
    import nyanko_api.main as _main
    from nyanko_api import torrents as torrents_mod

    monkeypatch.setattr("nyanko_api.main._fetch_torrent_xml", lambda url: _NYAA_XML)
    monkeypatch.setattr("nyanko_api.main._load_library_for_torrents",
        _async_return([MediaItem(id=1, title="Frieren", status="CURRENT", progress=27)]))
    s = client.get("/api/torrents/settings").json()
    s.update(download_mode="folder", watch_folder=str(tmp_path), folder_per_series=True)
    client.put("/api/torrents/settings", json=s)
    # Populate feed cache; force a .torrent entry (fixture item 2 is .torrent, Frieren metadata)
    client.get("/api/torrents/feed?refresh=true")
    sig = torrents_mod.signature(1, "https://nyaa.si/view/1000002")
    _main._torrent_link_cache[sig] = "https://nyaa.si/download/1000002.torrent"
    _main._torrent_item_cache[sig] = {"media_title": "Frieren", "episode": 28}

    class _FakeResp:
        content = b"fake-torrent"
        def raise_for_status(self): pass

    monkeypatch.setattr("nyanko_api.main.httpx.get", lambda *a, **k: _FakeResp())
    res = client.post("/api/torrents/download", json={"signature": sig}).json()
    assert res["action"] == "saved"
    assert "Frieren" in res["path"]  # subfolder created



# --- AniList OAuth: authorization code grant (AniList no soporta flujo sin secreto) ---

def test_anilist_authorization_url_uses_code_grant():
    from nyanko_api.anilist import AniListClient
    from nyanko_api.config import Settings

    url = AniListClient(Settings(anilist_client_id="cid123")).authorization_url("st8")
    assert "response_type=code" in url
    assert "client_id=cid123" in url


def test_anilist_callback_rejects_bad_state(client, database):
    database.set_setting("oauth_state", "S1")
    database.set_setting("oauth_account_alias", "default")
    resp = client.get("/api/auth/callback", params={"code": "c", "state": "WRONG"})
    assert resp.status_code == 400
