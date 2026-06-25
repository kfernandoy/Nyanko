from __future__ import annotations

import json
import time
from dataclasses import dataclass
from urllib.parse import urlencode

from .config import Settings
from .http import RateLimitedClient
from .models import (
    FuzzyDate,
    MediaDetails,
    MediaEntryUpdate,
    MediaItem,
    MediaListEntry,
    ProgressUpdate,
    SearchFilters,
    SearchResult,
)
from .provider_mappings import (
    ScoreFormat,
    convert_score,
    from_canonical_status,
    to_canonical_format,
    to_canonical_status,
)


AUTHORIZE_URL = "https://myanimelist.net/v1/oauth2/authorize"
TOKEN_URL = "https://myanimelist.net/v1/oauth2/token"
API_URL = "https://api.myanimelist.net/v2"
LIST_FIELDS = (
    "list_status,num_episodes,main_picture,alternative_titles,media_type,status,start_date"
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


class MyAnimeListClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = RateLimitedClient(requests_per_minute=60)

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
        response = await self.client.post(TOKEN_URL, data=data)
        return MyAnimeListCredential.from_token_response(response.json())

    async def refresh(self, credential: MyAnimeListCredential) -> MyAnimeListCredential:
        if not credential.refresh_token:
            raise MyAnimeListError("MyAnimeList refresh token is missing")
        data = {
            **self._oauth_client_data(),
            "grant_type": "refresh_token",
            "refresh_token": credential.refresh_token,
        }
        response = await self.client.post(TOKEN_URL, data=data)
        return MyAnimeListCredential.from_token_response(response.json())

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
        self, access_token: str, external_id: int, update: MediaEntryUpdate
    ) -> MediaListEntry:
        headers = {"Authorization": f"Bearer {access_token}"}
        data: dict[str, object] = {}
        if update.status is not None:
            data["status"] = from_canonical_status("mal", update.status)
        if update.progress is not None:
            data["num_watched_episodes"] = update.progress
        if update.score is not None:
            score = convert_score(
                update.score, ScoreFormat.POINT_100, ScoreFormat.POINT_10
            )
            data["score"] = int(score) if score is not None else 0
        if update.repeat is not None:
            data["num_times_rewatched"] = update.repeat
        if update.notes is not None:
            data["comments"] = update.notes
        if update.started_at is not None:
            data["start_date"] = _fuzzy_to_mal_date(update.started_at)
        if update.completed_at is not None:
            data["finish_date"] = _fuzzy_to_mal_date(update.completed_at)
        response = await self.client.patch(
            f"{API_URL}/anime/{external_id}/my_list_status",
            headers=headers,
            data=data,
        )
        return self._list_entry(response.json())

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
                "fields": "id,title,main_picture,media_type,status,num_episodes",
            },
        )
        return [
            SearchResult(
                id=item["node"]["id"],
                title=item["node"]["title"],
                format=to_canonical_format(
                    "mal", item["node"].get("media_type")
                ).value,
                status=item["node"].get("status"),
                episodes=item["node"].get("num_episodes"),
                cover_image=(item["node"].get("main_picture") or {}).get("medium"),
            )
            for item in response.json().get("data", [])
        ]

    async def discover(
        self, access_token: str, filters: SearchFilters
    ) -> SearchResult:
        raise MyAnimeListError("MyAnimeList discovery is not enabled")

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
        return MediaItem(
            id=node["id"],
            title=node["title"],
            status=status,
            progress=list_status.get("num_episodes_watched", 0),
            episodes=node.get("num_episodes"),
            cover_image=picture.get("large") or picture.get("medium"),
            title_english=alternative_titles.get("en") or None,
            title_native=alternative_titles.get("ja") or None,
            synonyms=alternative_titles.get("synonyms") or [],
            year=year,
            format=to_canonical_format("mal", node.get("media_type")).value,
            site_url=f"https://myanimelist.net/anime/{node['id']}",
        )

    @staticmethod
    def _list_entry(status: dict) -> MediaListEntry:
        score = status.get("score") or 0
        return MediaListEntry(
            id=0,
            status=to_canonical_status("mal", status["status"]).value,
            score=score * 10,
            progress=status.get("num_episodes_watched", 0),
            repeat=status.get("num_times_rewatched", 0),
            private=False,
            notes=status.get("comments") or None,
            started_at=_parse_mal_date(status.get("start_date")),
            completed_at=_parse_mal_date(status.get("finish_date")),
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
