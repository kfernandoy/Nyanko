from __future__ import annotations

import json
import time
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

from .config import Settings
from .http import RateLimitedClient
from .normalizer import airing_season_from_date
from .models import (
    FuzzyDate,
    GlobalSearchResponse,
    MediaDetails,
    MediaEntryUpdate,
    MediaItem,
    MediaListEntry,
    ProgressUpdate,
    SearchFilters,
    SearchResult,
    UserPreferences,
)
from .provider_mappings import (
    ScoreFormat,
    convert_score,
    from_canonical_status,
    to_canonical_format,
    to_canonical_status,
)

TITLE_FIELDS = "alternative_titles"

AUTHORIZE_URL = "https://myanimelist.net/v1/oauth2/authorize"
TOKEN_URL = "https://myanimelist.net/v1/oauth2/token"
API_URL = "https://api.myanimelist.net/v2"
# Estado de emisión de MAL → enum canónico (estilo AniList), para filtros de torrents.
_MAL_AIRING = {
    "currently_airing": "RELEASING",
    "finished_airing": "FINISHED",
    "not_yet_aired": "NOT_YET_RELEASED",
}
LIST_FIELDS = (
    "list_status{score,num_episodes_watched,status,start_date,finish_date},"
    "num_episodes,main_picture,alternative_titles,media_type,status,start_date,genres,mean"
)
MANGA_LIST_FIELDS = (
    "list_status{score,num_chapters_read,num_volumes_read,status,start_date,finish_date},"
    "num_chapters,num_volumes,main_picture,alternative_titles,media_type,status,start_date,genres,mean"
)


class MyAnimeListError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class MyAnimeListCredential:
    access_token: str
    refresh_token: str | None
    expires_at: int

    @classmethod
    def from_token_response(cls, payload: dict) -> "MyAnimeListCredential":
        if "access_token" not in payload:
            code = payload.get("error", "unknown")
            hint = payload.get("message") or payload.get("error_description") or ""
            raise MyAnimeListError(f"MAL rechazó el token ({code}){': ' + hint if hint else ''}")
        return cls(
            access_token=payload["access_token"],
            refresh_token=payload.get("refresh_token"),
            expires_at=int(time.time()) + int(payload.get("expires_in", 3600)),
        )

    @classmethod
    def loads(cls, value: str) -> "MyAnimeListCredential":
        try:
            payload = json.loads(value)
            return cls(
                access_token=payload["access_token"],
                refresh_token=payload.get("refresh_token"),
                expires_at=int(payload["expires_at"]),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise MyAnimeListError("Invalid MyAnimeList credential") from error

    def dumps(self) -> str:
        return json.dumps(
            {
                "access_token": self.access_token,
                "refresh_token": self.refresh_token,
                "expires_at": self.expires_at,
            },
            separators=(",", ":"),
        )

    @property
    def needs_refresh(self) -> bool:
        return self.expires_at <= int(time.time()) + 60


# Valor inicial y techo. MAL no manda X-RateLimit-Limit: sin cabecera el presupuesto no se
# toca y el ritmo sigue siendo exactamente este.
_client = RateLimitedClient(requests_per_minute=60)


class MyAnimeListClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = _client

    def authorization_url(self, state: str, code_challenge: str) -> str:
        if not self.settings.mal_client_id:
            raise MyAnimeListError("MyAnimeList client ID is not configured")
        query = {
            "response_type": "code",
            "client_id": self.settings.mal_client_id,
            "redirect_uri": self.settings.mal_redirect_uri,
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "plain",
        }
        return f"{AUTHORIZE_URL}?{urlencode(query)}"

    def _oauth_client_data(self) -> dict[str, str]:
        if not self.settings.mal_client_id:
            raise MyAnimeListError("MyAnimeList client ID is not configured")
        data = {"client_id": self.settings.mal_client_id}
        if self.settings.mal_client_secret:
            data["client_secret"] = self.settings.mal_client_secret
        return data

    async def exchange_code(self, code: str, code_verifier: str) -> MyAnimeListCredential:
        data = {
            **self._oauth_client_data(),
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.settings.mal_redirect_uri,
            "code_verifier": code_verifier,
        }
        try:
            response = await self.client.post(TOKEN_URL, data=data)
        except httpx.HTTPStatusError as error:
            raise MyAnimeListError(
                f"MyAnimeList rechazó el intercambio OAuth ({error.response.status_code}): "
                f"{_mal_error_message(error.response)}"
            ) from error
        return MyAnimeListCredential.from_token_response(response.json())

    async def refresh(self, credential: MyAnimeListCredential) -> MyAnimeListCredential:
        if not credential.refresh_token:
            raise MyAnimeListError("MyAnimeList refresh token is missing")
        data = {
            **self._oauth_client_data(),
            "grant_type": "refresh_token",
            "refresh_token": credential.refresh_token,
        }
        try:
            response = await self.client.post(TOKEN_URL, data=data)
        except httpx.HTTPStatusError as error:
            raise MyAnimeListError(
                f"MyAnimeList rechazó el refresh token ({error.response.status_code}): "
                f"{_mal_error_message(error.response)}"
            ) from error
        return MyAnimeListCredential.from_token_response(response.json())

    async def user_info(self, access_token: str) -> dict:
        headers = {"Authorization": f"Bearer {access_token}"}
        response = await self.client.get(
            f"{API_URL}/users/@me",
            headers=headers,
            params={"fields": "anime_statistics"},
        )
        return response.json()

    async def library(self, access_token: str) -> list[MediaItem]:
        headers = {"Authorization": f"Bearer {access_token}"}
        items: list[MediaItem] = []
        offset = 0
        limit = 100
        for _ in range(100):
            response = await self.client.get(
                f"{API_URL}/users/@me/animelist",
                headers=headers,
                params={
                    "fields": LIST_FIELDS,
                    "limit": limit,
                    "offset": offset,
                },
            )
            payload = response.json()
            page = payload.get("data", [])
            items.extend(self._media_item(entry) for entry in page)
            if not payload.get("paging", {}).get("next"):
                break
            offset += len(page)
        return items

    async def library_manga(self, access_token: str) -> list[MediaItem]:
        headers = {"Authorization": f"Bearer {access_token}"}
        items: list[MediaItem] = []
        offset = 0
        limit = 100
        for _ in range(100):
            response = await self.client.get(
                f"{API_URL}/users/@me/mangalist",
                headers=headers,
                params={"fields": MANGA_LIST_FIELDS, "limit": limit, "offset": offset},
            )
            payload = response.json()
            page = payload.get("data", [])
            items.extend(self._manga_item(entry) for entry in page)
            if not payload.get("paging", {}).get("next"):
                break
            offset += len(page)
        return items

    async def manga_details(self, access_token: str, external_id: int) -> MediaDetails:
        headers = {"Authorization": f"Bearer {access_token}"}
        response = await self.client.get(
            f"{API_URL}/manga/{external_id}",
            headers=headers,
            params={
                "fields": "id,title,main_picture,alternative_titles,media_type,status,num_chapters,num_volumes,start_date,synopsis,genres,my_list_status",
            },
        )
        node = response.json()
        list_status = node.get("my_list_status") or {}
        picture = node.get("main_picture") or {}
        alt = node.get("alternative_titles") or {}
        start_date = node.get("start_date") or ""
        year = int(start_date[:4]) if len(start_date) >= 4 and start_date[:4].isdigit() else None
        return MediaDetails(
            id=node["id"],
            title=node["title"],
            title_english=alt.get("en") or None,
            title_native=alt.get("ja") or None,
            synonyms=alt.get("synonyms") or [],
            description=node.get("synopsis"),
            site_url=f"https://myanimelist.net/manga/{node['id']}",
            cover_image=picture.get("large") or picture.get("medium"),
            media_type="MANGA",
            format=to_canonical_format("mal", node.get("media_type")).value,
            status=node.get("status"),
            episodes=None,
            chapters=node.get("num_chapters"),
            volumes=node.get("num_volumes"),
            season_year=year,
            score_format="POINT_10",
            list_entry=self._list_entry(list_status, manga=True) if list_status else None,
            genres=[g["name"] for g in node.get("genres") or [] if g.get("name")],
            studios=[],
        )

    async def preferences(self, access_token: str) -> UserPreferences:
        info = await self.user_info(access_token)
        return UserPreferences(
            username=info.get("name") or "",
            avatar=info.get("picture") or None,
            title_language="ENGLISH",
            score_format="POINT_10",
            display_adult_content=False,
        )

    async def update_progress(
        self, access_token: str, update: ProgressUpdate
    ) -> dict:
        headers = {"Authorization": f"Bearer {access_token}"}
        data: dict[str, object] = {
            "num_watched_episodes": update.progress,
        }
        if update.status is not None:
            data["status"] = from_canonical_status("mal", update.status)
        response = await self.client.patch(
            f"{API_URL}/anime/{update.media_id}/my_list_status",
            headers=headers,
            data=data,
        )
        return response.json()

    async def edit_entry(
        self, access_token: str, external_id: int, update: MediaEntryUpdate, media_type: str = "ANIME"
    ) -> MediaListEntry:
        headers = {"Authorization": f"Bearer {access_token}"}
        manga = media_type == "MANGA"
        data: dict[str, object] = {}
        if update.status is not None:
            status = from_canonical_status("mal", update.status)
            data["status"] = {"watching": "reading", "plan_to_watch": "plan_to_read"}.get(status, status) if manga else status
        if update.progress is not None:
            data["num_chapters_read" if manga else "num_watched_episodes"] = update.progress
        if update.score is not None:
            score = convert_score(
                update.score, ScoreFormat.POINT_100, ScoreFormat.POINT_10
            )
            data["score"] = int(score) if score is not None else 0
        if update.repeat is not None:
            data["num_times_reread" if manga else "num_times_rewatched"] = update.repeat
        if update.notes is not None:
            data["comments"] = update.notes
        if update.started_at is not None:
            data["start_date"] = _fuzzy_to_mal_date(update.started_at)
        if update.completed_at is not None:
            data["finish_date"] = _fuzzy_to_mal_date(update.completed_at)
        kind = "manga" if manga else "anime"
        response = await self.client.patch(
            f"{API_URL}/{kind}/{external_id}/my_list_status",
            headers=headers,
            data=data,
        )
        return self._list_entry(response.json(), manga=manga)

    async def delete_entry(self, access_token: str, external_id: int) -> bool:
        headers = {"Authorization": f"Bearer {access_token}"}
        response = await self.client.delete(
            f"{API_URL}/anime/{external_id}/my_list_status",
            headers=headers,
        )
        return response.status_code in {200, 204}

    async def details(self, access_token: str, external_id: int) -> MediaDetails:
        headers = {"Authorization": f"Bearer {access_token}"}
        response = await self.client.get(
            f"{API_URL}/anime/{external_id}",
            headers=headers,
            params={
                "fields": "id,title,main_picture,alternative_titles,media_type,status,num_episodes,start_date,synopsis,my_list_status",
            },
        )
        node = response.json()
        list_status = node.get("my_list_status") or {}
        picture = node.get("main_picture") or {}
        alternative_titles = node.get("alternative_titles") or {}
        start_date = node.get("start_date") or ""
        year = (
            int(start_date[:4])
            if len(start_date) >= 4 and start_date[:4].isdigit()
            else None
        )
        list_entry = None
        if list_status:
            list_entry = self._list_entry(list_status)
        return MediaDetails(
            id=node["id"],
            title=node["title"],
            title_english=alternative_titles.get("en") or None,
            title_native=alternative_titles.get("ja") or None,
            synonyms=alternative_titles.get("synonyms") or [],
            description=node.get("synopsis"),
            site_url=f"https://myanimelist.net/anime/{node['id']}",
            cover_image=picture.get("large") or picture.get("medium"),
            format=to_canonical_format("mal", node.get("media_type")).value,
            status=node.get("status"),
            episodes=node.get("num_episodes"),
            season_year=year,
            score_format="POINT_10",
            list_entry=list_entry,
            genres=[],
            studios=[],
        )

    async def search(
        self, access_token: str, query: str, limit: int = 10
    ) -> list[SearchResult]:
        headers = {"Authorization": f"Bearer {access_token}"}
        response = await self.client.get(
            f"{API_URL}/anime",
            headers=headers,
            params={
                "q": query,
                "limit": limit,
                "fields": f"id,title,main_picture,media_type,status,num_episodes,start_date,{TITLE_FIELDS}",
            },
        )
        return [_mal_search_result(item["node"]) for item in response.json().get("data", [])]

    async def discover(self, access_token: str, filters: SearchFilters) -> GlobalSearchResponse:
        per_page = min(max(1, filters.per_page), 100)
        headers = {"Authorization": f"Bearer {access_token}"}
        fields = f"id,title,main_picture,media_type,status,num_episodes,mean,start_date,genres,{TITLE_FIELDS}"
        fetch_limit = min(100, max(per_page * max(filters.page, 1) * 3, per_page))
        # MyAnimeList hides nsfw entries by default; opt in only when adult is requested.
        nsfw = "true" if filters.is_adult else "false"

        if filters.query and filters.query.strip():
            response = await self.client.get(
                f"{API_URL}/anime",
                headers=headers,
                params={"q": filters.query.strip(), "limit": fetch_limit, "fields": fields, "nsfw": nsfw},
            )
            data = response.json()
            raw_items = [entry["node"] for entry in data.get("data", [])]
        else:
            ranking_type = "all" if filters.sort == "SCORE" else "bypopularity"
            response = await self.client.get(
                f"{API_URL}/anime/ranking",
                headers=headers,
                params={"ranking_type": ranking_type, "limit": fetch_limit, "offset": 0, "fields": fields, "nsfw": nsfw},
            )
            data = response.json()
            raw_items = [entry["node"] for entry in data.get("data", [])]
        results = [_mal_search_result(item) for item in raw_items]
        results = _filter_search_results(results, filters)
        if filters.sort == "SCORE":
            results.sort(key=lambda item: ((item.average_score or 0), item.popularity, item.title.casefold()), reverse=True)
        else:
            results.sort(key=lambda item: (item.popularity, item.average_score or 0, item.title.casefold()), reverse=True)
        start = (filters.page - 1) * per_page
        end = start + per_page
        return GlobalSearchResponse(
            results=results[start:end],
            has_next_page=end < len(results),
        )

    @staticmethod
    def _media_item(entry: dict) -> MediaItem:
        node = entry["node"]
        list_status = entry["list_status"]
        try:
            status = to_canonical_status("mal", list_status["status"]).value
        except ValueError as error:
            raise MyAnimeListError(str(error)) from error
        picture = node.get("main_picture") or {}
        alternative_titles = node.get("alternative_titles") or {}
        start_date = node.get("start_date") or ""
        year = int(start_date[:4]) if len(start_date) >= 4 and start_date[:4].isdigit() else None
        raw_score = list_status.get("score") or 0
        return MediaItem(
            id=node["id"],
            title=node["title"],
            status=status,
            progress=list_status.get("num_episodes_watched", 0),
            score=raw_score * 10 if raw_score else None,
            episodes=node.get("num_episodes"),
            cover_image=picture.get("large") or picture.get("medium"),
            title_english=alternative_titles.get("en") or None,
            title_native=alternative_titles.get("ja") or None,
            synonyms=alternative_titles.get("synonyms") or [],
            year=year,
            season=airing_season_from_date(start_date),
            format=to_canonical_format("mal", node.get("media_type")).value,
            media_status=_MAL_AIRING.get(node.get("status") or ""),
            site_url=f"https://myanimelist.net/anime/{node['id']}",
            genres=[g["name"] for g in node.get("genres") or [] if g.get("name")],
            started_at=list_status.get("start_date") or None,
            completed_at=list_status.get("finish_date") or None,
        )

    @staticmethod
    def _list_entry(status: dict, manga: bool = False) -> MediaListEntry:
        score = status.get("score") or 0
        progress = status.get("num_chapters_read", 0) if manga else status.get("num_episodes_watched", 0)
        repeat = status.get("num_times_reread", 0) if manga else status.get("num_times_rewatched", 0)
        return MediaListEntry(
            id=0,
            status=to_canonical_status("mal", status["status"]).value,
            score=score * 10,
            progress=progress,
            repeat=repeat,
            private=False,
            notes=status.get("comments") or None,
            started_at=_parse_mal_date(status.get("start_date")),
            completed_at=_parse_mal_date(status.get("finish_date")),
        )

    @staticmethod
    def _manga_item(entry: dict) -> MediaItem:
        node = entry["node"]
        list_status = entry["list_status"]
        try:
            status = to_canonical_status("mal", list_status["status"]).value
        except ValueError as error:
            raise MyAnimeListError(str(error)) from error
        picture = node.get("main_picture") or {}
        alt = node.get("alternative_titles") or {}
        start_date = node.get("start_date") or ""
        year = int(start_date[:4]) if len(start_date) >= 4 and start_date[:4].isdigit() else None
        raw_score = list_status.get("score") or 0
        return MediaItem(
            id=node["id"],
            title=node["title"],
            status=status,
            progress=list_status.get("num_chapters_read", 0),
            score=raw_score * 10 if raw_score else None,
            episodes=None,
            chapters=node.get("num_chapters"),
            volumes=node.get("num_volumes"),
            cover_image=picture.get("large") or picture.get("medium"),
            title_english=alt.get("en") or None,
            title_native=alt.get("ja") or None,
            synonyms=alt.get("synonyms") or [],
            year=year,
            format=to_canonical_format("mal", node.get("media_type")).value,
            site_url=f"https://myanimelist.net/manga/{node['id']}",
            genres=[g["name"] for g in node.get("genres") or [] if g.get("name")],
            started_at=list_status.get("start_date") or None,
            completed_at=list_status.get("finish_date") or None,
        )


def _fuzzy_to_mal_date(date: FuzzyDate) -> str:
    if date.year is None:
        return ""
    return f"{date.year:04d}-{date.month or 1:02d}-{date.day or 1:02d}"


def _parse_mal_date(value: str | None) -> FuzzyDate:
    if not value:
        return FuzzyDate()
    parts = value.split("-")
    return FuzzyDate(
        year=_int_or_none(parts[0]),
        month=_int_or_none(parts[1]) if len(parts) > 1 else None,
        day=_int_or_none(parts[2]) if len(parts) > 2 else None,
    )


def _int_or_none(value: str) -> int | None:
    try:
        return int(value)
    except ValueError:
        return None


def _mal_search_result(node: dict) -> SearchResult:
    picture = node.get("main_picture") or {}
    raw_score = node.get("mean") or 0
    alt_titles = node.get("alternative_titles") or {}
    start_date = node.get("start_date") or ""
    year = int(start_date[:4]) if len(start_date) >= 4 and start_date[:4].isdigit() else None
    return SearchResult(
        id=node["id"],
        title=node["title"],
        title_english=alt_titles.get("en") or None,
        title_native=alt_titles.get("ja") or None,
        synonyms=alt_titles.get("synonyms") or [],
        format=to_canonical_format("mal", node.get("media_type")).value,
        status=node.get("status"),
        episodes=node.get("num_episodes"),
        cover_image=picture.get("large") or picture.get("medium"),
        average_score=int(raw_score * 10) if raw_score else None,
        popularity=0,
        year=year,
        genres=[genre["name"] for genre in node.get("genres") or [] if genre.get("name")],
    )


def _mal_error_message(response: httpx.Response) -> str:
    try:
        payload = response.json()
        if isinstance(payload, dict):
            return payload.get("message") or payload.get("error_description") or payload.get("error") or response.text
    except ValueError:
        pass
    return response.text or "sin detalle"


def _filter_search_results(results: list[SearchResult], filters: SearchFilters) -> list[SearchResult]:
    query = (filters.query or "").strip()
    normalized_query = query.casefold()
    genre = (filters.genre or "").strip().casefold()
    filtered: list[SearchResult] = []
    for item in results:
        titles = [
            item.title,
            item.title_romaji,
            item.title_english,
            item.title_native,
            *(item.synonyms or []),
        ]
        if normalized_query and not any(
            normalized_query in title.casefold() for title in titles if title
        ):
            continue
        if filters.format and item.format != filters.format:
            continue
        if filters.status and item.status != filters.status:
            continue
        if filters.year is not None and item.year != filters.year:
            continue
        if genre and not any(genre == value.casefold() for value in item.genres or []):
            continue
        filtered.append(item)
    return filtered
