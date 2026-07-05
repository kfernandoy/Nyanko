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


@pytest.mark.asyncio
async def test_exchange_code_uses_broker_without_local_secret(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"access_token": "broker-token"}

    calls: list[tuple[str, dict]] = []

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def request(self, method, url, json=None, **kwargs):
            calls.append((url, json))
            return Response()

    monkeypatch.setattr("nyanko_api.http.httpx.AsyncClient", lambda **kwargs: Client())
    settings = Settings(
        anilist_client_id="123",
        anilist_client_secret=None,
        anilist_token_broker_url="https://proj.supabase.co/functions/v1/anilist-token",
    )

    token = await AniListClient(settings).exchange_code("the-code")

    assert token == "broker-token"
    url, payload = calls[0]
    assert url == "https://proj.supabase.co/functions/v1/anilist-token"
    # El broker recibe solo código y redirect: el secreto nunca sale de la función.
    assert payload == {
        "code": "the-code",
        "redirect_uri": settings.anilist_redirect_uri,
    }


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
                    "Viewer": {"mediaListOptions": {"scoreFormat": "POINT_10_DECIMAL"}},
                    "MediaListCollection": {
                        "lists": [{
                            "entries": [{
                                "mediaId": 42,
                                "status": "CURRENT",
                                "progress": 7,
                                "score": 8.5,
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
        if "query ScoreFormat" in _query:
            return {"Viewer": {"mediaListOptions": {"scoreFormat": "POINT_10"}}}
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
async def test_edit_entry_converts_canonical_score_to_provider_scale(monkeypatch):
    captured: dict = {}

    async def graphql(_token, query, variables=None):
        if "query ScoreFormat" in query:
            return {"Viewer": {"mediaListOptions": {"scoreFormat": "POINT_10_DECIMAL"}}}
        captured.update(variables or {})
        return {
            "SaveMediaListEntry": {
                "id": 1,
                "status": "CURRENT",
                "score": 8.5,
                "progress": 7,
                "repeat": 0,
                "private": False,
                "notes": None,
                "startedAt": None,
                "completedAt": None,
            }
        }

    client = AniListClient(Settings())
    monkeypatch.setattr(client, "graphql", graphql)

    entry = await client.edit_entry("token", 1, MediaEntryUpdate(score=85))

    assert captured["score"] == 8.5
    assert entry.score == 85


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
        captured["graphql_query"] = query
        captured.update(variables or {})
        return {"Page": {"pageInfo": {"hasNextPage": False}, "media": []}}

    client = AniListClient(Settings())
    monkeypatch.setattr(client, "graphql", graphql)

    from nyanko_api.models import SearchFilters
    await client.discover("token", SearchFilters())

    assert captured.get("sort") == ["POPULARITY_DESC"]
    assert "search:" not in captured["graphql_query"]
    assert captured.get("query") is None or captured.get("query") == ""


def test_anilist_clients_share_rate_limiter():
    c1 = AniListClient(Settings())
    c2 = AniListClient(Settings())
    assert c1.client is c2.client


@pytest.mark.asyncio
async def test_discover_sort_score_uses_score_desc(monkeypatch):
    captured: dict = {}

    async def graphql(_token, query, variables=None):
        captured["graphql_query"] = query
        captured.update(variables or {})
        return {"Page": {"pageInfo": {"hasNextPage": False}, "media": []}}

    client = AniListClient(Settings())
    monkeypatch.setattr(client, "graphql", graphql)

    from nyanko_api.models import SearchFilters
    await client.discover("token", SearchFilters(sort="SCORE"))

    assert captured.get("sort") == ["SCORE_DESC"]


def test_media_list_includes_dates():
    from nyanko_api.anilist import _fuzzy_date_to_str

    assert _fuzzy_date_to_str({"year": 2024, "month": 1, "day": 15}) == "2024-01-15"
    assert _fuzzy_date_to_str({"year": 2024, "month": None, "day": None}) == "2024-01-01"
    assert _fuzzy_date_to_str({"year": None, "month": None, "day": None}) is None
    assert _fuzzy_date_to_str(None) is None


def test_statistics_returns_statistics_response():
    from nyanko_api.models import StatisticsResponse
    from nyanko_api.anilist import AniListClient

    raw = {
        "Viewer": {
            "statistics": {
                "anime": {
                    "count": 42,
                    "episodesWatched": 500,
                    "minutesWatched": 12000,
                    "meanScore": 75.0,
                    "genres": [{"genre": "Action", "count": 10}],
                    "statuses": [{"status": "COMPLETED", "count": 30}],
                    "formats": [{"format": "TV", "count": 35}],
                    "releaseYears": [{"releaseYear": 2023, "count": 8}],
                    "studios": [{"studio": {"id": 1, "name": "MAPPA"}, "count": 3}],
                    "countries": [{"country": "JP", "count": 40}],
                },
                "manga": {
                    "count": 5,
                    "chaptersRead": 120,
                    "volumesRead": 10,
                    "meanScore": 80.0,
                    "genres": [{"genre": "Romance", "count": 3}],
                    "statuses": [{"status": "COMPLETED", "count": 3}],
                    "formats": [{"format": "MANGA", "count": 5}],
                    "releaseYears": [{"releaseYear": 2022, "count": 2}],
                    "studios": [],
                    "countries": [{"country": "JP", "count": 5}],
                },
            }
        }
    }

    client = AniListClient.__new__(AniListClient)
    result = client._build_statistics_response(raw)

    assert isinstance(result, StatisticsResponse)
    assert result.anime.count == 42
    assert result.anime.formats[0].label == "TV"
    assert result.anime.release_years[0].label == "2023"
    assert result.anime.studios[0].label == "MAPPA"
    assert result.manga.count == 5
    assert result.manga.episodes_watched == 120


from nyanko_api.models import (
    CharacterEdge,
    CharacterName,
    CharacterNode,
    MediaDetails,
    RecommendationItem,
    RelationEdge,
    StaffEdge,
    TrailerInfo,
    VoiceActorNode,
)


def test_character_edge_parses_name_role_and_va():
    edge = CharacterEdge(
        node=CharacterNode(name=CharacterName(full="Naruto Uzumaki")),
        role="MAIN",
        voice_actors=[VoiceActorNode(name=CharacterName(full="Junko Takeuchi"))],
    )
    assert edge.node.name.full == "Naruto Uzumaki"
    assert edge.role == "MAIN"
    assert edge.voice_actors[0].name.full == "Junko Takeuchi"


def test_staff_edge_parses():
    edge = StaffEdge(
        node=CharacterNode(name=CharacterName(full="Hayato Date")),
        role="Director",
    )
    assert edge.node.name.full == "Hayato Date"
    assert edge.role == "Director"


def test_relation_edge_parses():
    edge = RelationEdge(id=1735, title="Naruto: Shippuden", format="TV", relation_type="SEQUEL")
    assert edge.id == 1735
    assert edge.relation_type == "SEQUEL"


def test_recommendation_item_parses():
    item = RecommendationItem(id=11061, title="Hunter x Hunter (2011)", rating=42)
    assert item.id == 11061
    assert item.rating == 42


def test_trailer_info_parses():
    trailer = TrailerInfo(id="dQw4w9WgXcQ", site="youtube")
    assert trailer.site == "youtube"


def test_media_details_extra_fields_default_empty():
    details = MediaDetails(
        id=1,
        title="Test",
        synonyms=[],
        site_url="https://anilist.co/anime/1",
        genres=[],
        studios=[],
        score_format="POINT_10",
    )
    assert details.characters == []
    assert details.staff == []
    assert details.relations == []
    assert details.recommendations == []
    assert details.trailer is None


def test_parse_relations_maps_edges():
    media = {
        "relations": {
            "edges": [
                {
                    "relationType": "SEQUEL",
                    "node": {"id": 1735, "format": "TV", "title": {"userPreferred": "Naruto: Shippuden"}},
                }
            ]
        }
    }
    result = AniListClient._parse_relations(media)
    assert len(result) == 1
    assert result[0].id == 1735
    assert result[0].relation_type == "SEQUEL"
    assert result[0].title == "Naruto: Shippuden"
    assert result[0].format == "TV"


def test_parse_relations_handles_missing():
    assert AniListClient._parse_relations({}) == []
    assert AniListClient._parse_relations({"relations": None}) == []


def test_parse_recommendations_filters_null_media():
    media = {
        "recommendations": {
            "nodes": [
                {
                    "rating": 42,
                    "mediaRecommendation": {
                        "id": 11061,
                        "format": "TV",
                        "title": {"userPreferred": "HxH"},
                        "coverImage": {"large": "https://example.com/img.jpg"},
                    },
                },
                {"rating": 0, "mediaRecommendation": None},
            ]
        }
    }
    result = AniListClient._parse_recommendations(media)
    assert len(result) == 1
    assert result[0].id == 11061
    assert result[0].rating == 42
    assert result[0].cover_image == "https://example.com/img.jpg"


def test_parse_characters_maps_role_and_first_va():
    media = {
        "characters": {
            "edges": [
                {
                    "role": "MAIN",
                    "node": {
                        "name": {"full": "Naruto Uzumaki"},
                        "image": {"medium": "https://example.com/char.jpg"},
                    },
                    "voiceActors": [
                        {"name": {"full": "Junko Takeuchi"}, "image": {"medium": "https://example.com/va.jpg"}},
                        {"name": {"full": "Other VA"}, "image": {"medium": "https://example.com/va2.jpg"}},
                    ],
                }
            ]
        }
    }
    result = AniListClient._parse_characters(media)
    assert len(result) == 1
    assert result[0].node.name.full == "Naruto Uzumaki"
    assert result[0].role == "MAIN"
    assert len(result[0].voice_actors) == 1  # solo el primero
    assert result[0].voice_actors[0].name.full == "Junko Takeuchi"


def test_parse_staff_maps_role():
    media = {
        "staff": {
            "edges": [
                {
                    "role": "Director",
                    "node": {
                        "name": {"full": "Hayato Date"},
                        "image": {"medium": "https://example.com/staff.jpg"},
                    },
                }
            ]
        }
    }
    result = AniListClient._parse_staff(media)
    assert len(result) == 1
    assert result[0].node.name.full == "Hayato Date"
    assert result[0].role == "Director"
