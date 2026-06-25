import pytest
from pydantic import ValidationError

from nyanko_api.anilist import AniListClient
from nyanko_api.config import Settings
from nyanko_api.models import MediaEntryUpdate, MediaItem, SearchFilters, UserPreferencesUpdate


def test_maps_user_preferences():
    preferences = AniListClient._preferences(
        {
            "name": "nyanko-user",
            "avatar": {"large": "https://example.test/avatar.png"},
            "options": {"titleLanguage": "ROMAJI", "displayAdultContent": False},
            "mediaListOptions": {"scoreFormat": "POINT_10_DECIMAL"},
        }
    )

    assert preferences.username == "nyanko-user"
    assert preferences.title_language == "ROMAJI"
    assert preferences.score_format == "POINT_10_DECIMAL"
    assert preferences.display_adult_content is False


def test_media_item_accepts_score_and_updated_at():
    item = MediaItem(
        id=1,
        title="Test",
        status="CURRENT",
        progress=3,
        score=85,
        updated_at=1718000000,
    )

    assert item.score == 85
    assert item.updated_at == 1718000000


@pytest.mark.asyncio
async def test_media_list_maps_score_and_updated_at(monkeypatch):
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

        async def request(self, method, url, headers=None, json=None, **kwargs):
            assert method == "POST"
            if "query Viewer {" in json["query"]:
                return Response({"data": {"Viewer": {"id": 1}}})
            return Response({
                "data": {
                    "MediaListCollection": {
                        "lists": [{
                            "entries": [{
                                "mediaId": 42,
                                "status": "CURRENT",
                                "progress": 7,
                                "score": 85,
                                "updatedAt": 1718000000,
                                "media": {
                                    "id": 42,
                                    "episodes": 12,
                                    "format": "TV",
                                    "seasonYear": 2024,
                                    "siteUrl": "https://anilist.co/anime/42",
                                    "synonyms": [],
                                    "title": {
                                        "userPreferred": "Test Anime",
                                        "romaji": None,
                                        "english": None,
                                        "native": None,
                                    },
                                    "coverImage": {"large": "https://example.test/cover.jpg"},
                                },
                            }],
                        }],
                    },
                },
            })

    monkeypatch.setattr(
        "nyanko_api.http.httpx.AsyncClient", lambda **kwargs: Client()
    )

    items = await AniListClient(Settings()).media_list("token")

    assert len(items) == 1
    assert items[0].score == 85
    assert items[0].updated_at == 1718000000


@pytest.mark.asyncio
async def test_season_uses_page_and_per_page(monkeypatch):
    captured: dict = {}

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

        async def request(self, method, url, headers=None, json=None, **kwargs):
            assert method == "POST"
            captured["variables"] = json.get("variables", {})
            return Response({"data": {"Page": {"media": []}}})

    monkeypatch.setattr(
        "nyanko_api.http.httpx.AsyncClient", lambda **kwargs: Client()
    )

    await AniListClient(Settings()).season(
        "token", "SPRING", 2024, page=2, per_page=25
    )

    assert captured["variables"]["page"] == 2
    assert captured["variables"]["perPage"] == 25


@pytest.mark.asyncio
async def test_activity_uses_page_and_per_page(monkeypatch):
    captured: dict = {}

    async def graphql(_token, query, variables=None):
        if "query Viewer" in query:
            return {"Viewer": {"id": 1}}
        captured.update(variables or {})
        return {"Page": {"activities": []}}

    client = AniListClient(Settings())
    monkeypatch.setattr(client, "graphql", graphql)

    await client.activity("token", page=2, limit=20)

    assert captured["page"] == 2
    assert captured["perPage"] == 20


@pytest.mark.asyncio
async def test_season_maps_studios_and_airing_schedule(monkeypatch):
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

        async def request(self, method, url, headers=None, json=None, **kwargs):
            assert method == "POST"
            return Response({
                "data": {
                    "Page": {
                        "media": [{
                            "id": 7,
                            "title": {"userPreferred": "Airing Show"},
                            "format": "TV",
                            "status": "RELEASING",
                            "episodes": 12,
                            "averageScore": 80,
                            "popularity": 100,
                            "startDate": {"year": 2024, "month": 4, "day": 5},
                            "coverImage": {"large": "https://example.test/cover.jpg"},
                            "studios": {"nodes": [{"name": "MAPPA"}, {"name": "Wit Studio"}]},
                            "nextAiringEpisode": {"episode": 3, "airingAt": 1718000000},
                        }],
                    },
                },
            })

    monkeypatch.setattr(
        "nyanko_api.http.httpx.AsyncClient", lambda **kwargs: Client()
    )

    items = await AniListClient(Settings()).season("token", "SPRING", 2024)

    assert len(items) == 1
    assert items[0].studios == ["MAPPA", "Wit Studio"]
    assert items[0].next_episode == 3
    assert items[0].next_airing_at == 1718000000


def test_rejects_invalid_preference_enums():
    with pytest.raises(ValidationError):
        UserPreferencesUpdate(
            title_language="INVALID",
            score_format="POINT_10",
            display_adult_content=False,
        )


@pytest.mark.asyncio
async def test_edit_entry_sends_explicit_null_to_clear_date(monkeypatch):
    captured: dict = {}

    async def graphql(_token, _query, variables=None):
        captured.update(variables or {})
        return {
            "SaveMediaListEntry": {
                "id": 1,
                "status": "CURRENT",
                "score": 0,
                "progress": 1,
                "repeat": 0,
                "private": False,
                "notes": None,
                "startedAt": None,
                "completedAt": None,
            }
        }

    client = AniListClient(Settings())
    monkeypatch.setattr(client, "graphql", graphql)

    await client.edit_entry("token", 1, MediaEntryUpdate(started_at=None))

    assert captured["startedAt"] is None
    assert "completedAt" not in captured


@pytest.mark.asyncio
async def test_discover_returns_paginated_results(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "data": {
                    "Page": {
                        "pageInfo": {"hasNextPage": True},
                        "media": [{
                            "id": 7,
                            "format": "TV",
                            "status": "RELEASING",
                            "episodes": 12,
                            "averageScore": 80,
                            "popularity": 100,
                            "title": {"userPreferred": "Discovery Anime"},
                            "coverImage": {"large": "https://example.test/cover.png"},
                        }],
                    }
                }
            }

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def request(self, method, url, headers=None, json=None, **kwargs):
            return Response()

    monkeypatch.setattr("nyanko_api.http.httpx.AsyncClient", lambda **kwargs: Client())

    response = await AniListClient(Settings()).discover(
        "token",
        SearchFilters(query="test", page=1, per_page=10, genre="Action", format="TV", year=2024, status="RELEASING"),
    )

    assert response.has_next_page is True
    assert len(response.results) == 1
    assert response.results[0].title == "Discovery Anime"


@pytest.mark.asyncio
async def test_discover_without_query_sorts_by_popularity(monkeypatch):
    captured: dict = {}

    async def graphql(_token, query, variables=None):
        captured["query"] = query
        captured.update(variables or {})
        return {"Page": {"pageInfo": {"hasNextPage": False}, "media": []}}

    client = AniListClient(Settings())
    monkeypatch.setattr(client, "graphql", graphql)

    await client.discover("token", SearchFilters())

    assert "POPULARITY_DESC" in captured["query"]
    assert "search:" not in captured["query"]
    assert captured.get("query") is None or captured.get("query") == ""


def test_anilist_clients_share_rate_limiter():
    c1 = AniListClient(Settings())
    c2 = AniListClient(Settings())
    assert c1.client is c2.client
