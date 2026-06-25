from urllib.parse import parse_qs, urlparse

import pytest

from nyanko_api.config import Settings
from nyanko_api.models import FuzzyDate, MediaEntryUpdate, ProgressUpdate
from nyanko_api.myanimelist import (
    MyAnimeListClient,
    MyAnimeListCredential,
    MyAnimeListError,
    _fuzzy_to_mal_date,
)


def mal_entry(media_id: int, status: str, progress: int) -> dict:
    return {
        "node": {
            "id": media_id,
            "title": f"Anime {media_id}",
            "num_episodes": 12,
            "main_picture": {"large": f"https://example.test/{media_id}.jpg"},
        },
        "list_status": {
            "status": status,
            "num_episodes_watched": progress,
        },
    }


def test_authorization_url_uses_pkce_and_redirect_uri():
    settings = Settings(mal_client_id="client-id", api_port=9876)
    url = MyAnimeListClient(settings).authorization_url("state-value", "verifier")
    parsed = urlparse(url)
    query = parse_qs(parsed.query)

    assert parsed.path == "/v1/oauth2/authorize"
    assert query["client_id"] == ["client-id"]
    assert query["state"] == ["state-value"]
    assert query["code_challenge"] == ["verifier"]
    assert query["code_challenge_method"] == ["plain"]
    assert query["redirect_uri"] == [
        "http://127.0.0.1:9876/api/auth/mal/callback"
    ]


def test_credential_round_trip():
    credential = MyAnimeListCredential(
        access_token="access", refresh_token="refresh", expires_at=123456789
    )

    assert MyAnimeListCredential.loads(credential.dumps()) == credential


def test_maps_mal_list_entry():
    item = MyAnimeListClient._media_item(mal_entry(7, "watching", 3))

    assert item.id == 7
    assert item.title == "Anime 7"
    assert item.status == "CURRENT"
    assert item.progress == 3
    assert item.episodes == 12


def test_rejects_unknown_mal_status():
    with pytest.raises(MyAnimeListError, match="Unsupported"):
        MyAnimeListClient._media_item(mal_entry(7, "unknown", 0))


@pytest.mark.asyncio
async def test_library_follows_pagination(monkeypatch):
    pages = [
        {"data": [mal_entry(1, "watching", 1)], "paging": {"next": "next"}},
        {"data": [mal_entry(2, "completed", 12)], "paging": {}},
    ]
    offsets: list[int] = []

    class Response:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def request(self, method, url, headers=None, params=None, **kwargs):
            assert method == "GET"
            assert url.endswith("/users/@me/animelist")
            assert headers["Authorization"] == "Bearer token"
            offsets.append(params["offset"])
            return Response(pages.pop(0))

    monkeypatch.setattr(
        "nyanko_api.http.httpx.AsyncClient", lambda **kwargs: Client()
    )

    items = await MyAnimeListClient(Settings()).library("token")

    assert [item.id for item in items] == [1, 2]
    assert [item.status for item in items] == ["CURRENT", "COMPLETED"]
    assert offsets == [0, 1]


def _make_async_client(responses: list[dict | None], expected: list[dict] | None = None):
    class Response:
        def __init__(self, payload, status_code: int = 200):
            self.payload = payload
            self.status_code = status_code

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    class Client:
        def __init__(self):
            self.calls: list[dict] = []

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def request(self, method, url, headers=None, params=None, **kwargs):
            self.calls.append({"method": method, "url": url, "params": params, **kwargs})
            payload = responses.pop(0)
            status = 204 if payload is None else 200
            return Response(payload, status_code=status)

    return Client()


@pytest.mark.asyncio
async def test_update_progress(monkeypatch):
    client = _make_async_client([{"status": "watching", "num_episodes_watched": 12}])
    monkeypatch.setattr("nyanko_api.http.httpx.AsyncClient", lambda **kwargs: client)

    result = await MyAnimeListClient(Settings()).update_progress(
        "token", ProgressUpdate(media_id=7, progress=12, status="CURRENT")
    )

    assert result["num_episodes_watched"] == 12
    assert client.calls[0]["method"] == "PATCH"
    assert client.calls[0]["url"].endswith("/anime/7/my_list_status")
    assert client.calls[0]["data"]["num_watched_episodes"] == 12
    assert client.calls[0]["data"]["status"] == "watching"


@pytest.mark.asyncio
async def test_edit_entry_converts_score(monkeypatch):
    client = _make_async_client([{
        "status": "completed",
        "score": 8,
        "num_episodes_watched": 12,
        "num_times_rewatched": 1,
    }])
    monkeypatch.setattr("nyanko_api.http.httpx.AsyncClient", lambda **kwargs: client)

    entry = await MyAnimeListClient(Settings()).edit_entry(
        "token", 7, MediaEntryUpdate(status="COMPLETED", progress=12, score=85)
    )

    assert entry.status == "COMPLETED"
    assert entry.score == 80
    assert entry.progress == 12
    assert client.calls[0]["data"]["score"] == 8


@pytest.mark.asyncio
async def test_delete_entry(monkeypatch):
    client = _make_async_client([None])
    monkeypatch.setattr("nyanko_api.http.httpx.AsyncClient", lambda **kwargs: client)

    deleted = await MyAnimeListClient(Settings()).delete_entry("token", 7)

    assert deleted is True
    assert client.calls[0]["method"] == "DELETE"
    assert client.calls[0]["url"].endswith("/anime/7/my_list_status")


@pytest.mark.asyncio
async def test_details(monkeypatch):
    client = _make_async_client([{
        "id": 7,
        "title": "Frieren",
        "media_type": "tv",
        "num_episodes": 28,
        "main_picture": {"large": "https://example.test/frieren.jpg"},
        "my_list_status": {
            "status": "watching",
            "score": 10,
            "num_episodes_watched": 12,
        },
    }])
    monkeypatch.setattr("nyanko_api.http.httpx.AsyncClient", lambda **kwargs: client)

    details = await MyAnimeListClient(Settings()).details("token", 7)

    assert details.title == "Frieren"
    assert details.format == "TV"
    assert details.list_entry is not None
    assert details.list_entry.status == "CURRENT"
    assert details.list_entry.score == 100


def test_fuzzy_to_mal_date_full():
    assert _fuzzy_to_mal_date(FuzzyDate(year=2024, month=3, day=15)) == "2024-03-15"


def test_fuzzy_to_mal_date_year_only():
    assert _fuzzy_to_mal_date(FuzzyDate(year=2024)) == "2024-01-01"


def test_fuzzy_to_mal_date_empty_clears():
    assert _fuzzy_to_mal_date(FuzzyDate()) == ""


def test_list_entry_reads_comments():
    status = {
        "status": "watching",
        "score": 7,
        "num_episodes_watched": 5,
        "comments": "muy bueno",
    }
    entry = MyAnimeListClient._list_entry(status)
    assert entry.notes == "muy bueno"
    assert entry.score == 70


@pytest.mark.asyncio
async def test_edit_entry_sends_optional_fields(monkeypatch):
    client = _make_async_client([{
        "status": "watching",
        "score": 0,
        "num_episodes_watched": 5,
        "num_times_rewatched": 2,
        "comments": "notas",
    }])
    monkeypatch.setattr("nyanko_api.http.httpx.AsyncClient", lambda **kwargs: client)

    update = MediaEntryUpdate(
        status="CURRENT",
        progress=5,
        repeat=2,
        notes="notas",
        started_at=FuzzyDate(year=2024, month=1, day=10),
        completed_at=FuzzyDate(),
    )
    await MyAnimeListClient(Settings()).edit_entry("token", 7, update)

    data = client.calls[0]["data"]
    assert data["num_times_rewatched"] == 2
    assert data["comments"] == "notas"
    assert data["start_date"] == "2024-01-10"
    assert data["finish_date"] == ""  # FuzzyDate() vacío → borrar fecha


@pytest.mark.asyncio
async def test_edit_entry_omits_none_optional_fields(monkeypatch):
    client = _make_async_client([{
        "status": "watching",
        "score": 0,
        "num_episodes_watched": 3,
    }])
    monkeypatch.setattr("nyanko_api.http.httpx.AsyncClient", lambda **kwargs: client)

    await MyAnimeListClient(Settings()).edit_entry(
        "token", 7, MediaEntryUpdate(progress=3)
    )

    data = client.calls[0]["data"]
    assert "num_times_rewatched" not in data
    assert "comments" not in data
    assert "start_date" not in data
    assert "finish_date" not in data


def test_mal_clients_share_rate_limiter():
    c1 = MyAnimeListClient(Settings())
    c2 = MyAnimeListClient(Settings())
    assert c1.client is c2.client


@pytest.mark.asyncio
async def test_discover_ranking_mode(monkeypatch):
    client = _make_async_client([{
        "data": [
            {
                "node": {
                    "id": 1,
                    "title": "Popular Anime",
                    "media_type": "tv",
                    "num_episodes": 12,
                    "status": "finished_airing",
                    "main_picture": {"large": "https://example.test/1.jpg"},
                    "mean_score": 8.5,
                }
            },
        ],
        "paging": {},
    }])
    monkeypatch.setattr("nyanko_api.http.httpx.AsyncClient", lambda **kwargs: client)

    from nyanko_api.models import SearchFilters
    result = await MyAnimeListClient(Settings()).discover("token", SearchFilters())

    assert len(result.results) == 1
    assert result.results[0].id == 1
    assert result.results[0].title == "Popular Anime"
    assert result.results[0].average_score == 85
    assert client.calls[0]["url"].endswith("/anime/ranking")
    assert client.calls[0]["params"]["ranking_type"] == "bypopularity"
    assert result.has_next_page is False


@pytest.mark.asyncio
async def test_discover_search_mode(monkeypatch):
    client = _make_async_client([{
        "data": [
            {
                "node": {
                    "id": 7,
                    "title": "Frieren",
                    "media_type": "tv",
                    "num_episodes": 28,
                    "status": "finished_airing",
                    "main_picture": {"large": "https://example.test/frieren.jpg"},
                    "mean_score": 9.0,
                }
            },
        ],
        "paging": {},
    }])
    monkeypatch.setattr("nyanko_api.http.httpx.AsyncClient", lambda **kwargs: client)

    from nyanko_api.models import SearchFilters
    result = await MyAnimeListClient(Settings()).discover("token", SearchFilters(query="frieren"))

    assert result.results[0].id == 7
    assert result.results[0].title == "Frieren"
    assert result.results[0].average_score == 90
    assert client.calls[0]["url"].endswith("/anime")
    assert client.calls[0]["params"]["q"] == "frieren"
