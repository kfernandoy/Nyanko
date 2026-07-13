from __future__ import annotations

import json
import time
from dataclasses import dataclass

import httpx

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
    UserPreferencesUpdate,
)
from .provider_mappings import (
    ScoreFormat,
    convert_score,
)

TOKEN_URL = "https://kitsu.io/api/oauth/token"
API_URL = "https://kitsu.app/api/edge"

# kitsu.app is behind Cloudflare, which serves a "Just a moment" bot challenge to
# clients with a default httpx User-Agent. A browser-like UA gets past the basic check.
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

_KITSU_STATUS_MAP = {
    "current": "CURRENT",
    "planned": "PLANNING",
    "completed": "COMPLETED",
    "on_hold": "PAUSED",
    "dropped": "DROPPED",
}

_TO_KITSU_STATUS = {v: k for k, v in _KITSU_STATUS_MAP.items()}

# Estado de emisión de Kitsu → enum canónico (estilo AniList), para filtros de torrents.
_KITSU_AIRING = {
    "current": "RELEASING",
    "finished": "FINISHED",
    "upcoming": "NOT_YET_RELEASED",
    "unreleased": "NOT_YET_RELEASED",
    "tba": "NOT_YET_RELEASED",
}

_KITSU_TITLE_LANG = {"canonical": "ROMAJI", "romanized": "ROMAJI", "english": "ENGLISH"}
_TO_KITSU_TITLE_LANG = {"ROMAJI": "romanized", "ENGLISH": "english", "NATIVE": "canonical"}


class KitsuError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class KitsuCredential:
    access_token: str
    refresh_token: str | None
    expires_at: int

    @classmethod
    def from_token_response(cls, payload: dict) -> "KitsuCredential":
        if "access_token" not in payload:
            code = payload.get("error", "unknown")
            hint = payload.get("error_description") or ""
            raise KitsuError(f"Kitsu rechazó el token ({code}){': ' + hint if hint else ''}")
        return cls(
            access_token=payload["access_token"],
            refresh_token=payload.get("refresh_token"),
            expires_at=int(time.time()) + int(payload.get("expires_in", 3600)),
        )

    @classmethod
    def loads(cls, value: str) -> "KitsuCredential":
        try:
            payload = json.loads(value)
            return cls(
                access_token=payload["access_token"],
                refresh_token=payload.get("refresh_token"),
                expires_at=int(payload["expires_at"]),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise KitsuError("Invalid Kitsu credential") from error

    def dumps(self) -> str:
        return json.dumps(
            {"access_token": self.access_token, "refresh_token": self.refresh_token, "expires_at": self.expires_at},
            separators=(",", ":"),
        )

    @property
    def needs_refresh(self) -> bool:
        return self.expires_at <= int(time.time()) + 60


# Valor inicial y techo. Kitsu no manda X-RateLimit-Limit: sin cabecera el presupuesto no
# se toca y el ritmo sigue siendo exactamente este.
_client = RateLimitedClient(requests_per_minute=50)


class KitsuClient:
    def __init__(self):
        self.client = _client

    async def login(self, username: str, password: str) -> KitsuCredential:
        try:
            response = await self.client.post(TOKEN_URL, headers={"User-Agent": _USER_AGENT}, data={
                "grant_type": "password",
                "username": username,
                "password": password,
            })
        except httpx.HTTPStatusError as error:
            raise KitsuError(
                f"Kitsu rechazó las credenciales ({error.response.status_code}): {error.response.text[:200]}"
            ) from error
        return KitsuCredential.from_token_response(response.json())

    async def refresh(self, credential: KitsuCredential) -> KitsuCredential:
        if not credential.refresh_token:
            raise KitsuError("Kitsu refresh token is missing")
        try:
            response = await self.client.post(TOKEN_URL, headers={"User-Agent": _USER_AGENT}, data={
                "grant_type": "refresh_token",
                "refresh_token": credential.refresh_token,
            })
        except httpx.HTTPStatusError as error:
            raise KitsuError(
                f"Kitsu rechazó el refresh ({error.response.status_code}): {error.response.text[:200]}"
            ) from error
        return KitsuCredential.from_token_response(response.json())

    async def _current_user_id(self, access_token: str) -> str:
        headers = _auth_headers(access_token)
        response = await self.client.get(f"{API_URL}/users?filter[self]=true", headers=headers)
        data = response.json().get("data") or []
        if not data:
            raise KitsuError("No se pudo obtener el perfil de Kitsu")
        return str(data[0]["id"])

    async def user_info(self, access_token: str) -> dict:
        headers = _auth_headers(access_token)
        response = await self.client.get(
            f"{API_URL}/users",
            headers=headers,
            params={
                "filter[self]": "true",
                "fields[users]": "name,slug,avatar,ratingSystem,titleLanguagePreference,sfwFilter",
            },
        )
        data = response.json().get("data") or []
        return data[0] if data else {}

    async def library(self, access_token: str) -> list[MediaItem]:
        user_id = await self._current_user_id(access_token)
        headers = _auth_headers(access_token)
        items: list[MediaItem] = []
        url: str | None = (
            f"{API_URL}/library-entries"
            f"?filter[userId]={user_id}&filter[kind]=anime"
            f"&include=anime&fields[anime]=canonicalTitle,titles,posterImage,episodeCount,startDate,averageRating,categories,subtype"
            f"&page[limit]=500"
        )
        for _ in range(20):
            if not url:
                break
            response = await self.client.get(url, headers=headers)
            payload = response.json()
            included = {inc["id"]: inc for inc in (payload.get("included") or []) if inc.get("type") == "anime"}
            for entry in (payload.get("data") or []):
                item = _entry_to_media_item(entry, included)
                if item:
                    items.append(item)
            url = (payload.get("links") or {}).get("next")
        return items

    async def search(self, access_token: str, query: str, limit: int = 10) -> list[SearchResult]:
        headers = _auth_headers(access_token)
        response = await self.client.get(
            f"{API_URL}/anime",
            headers=headers,
            params={
                "filter[text]": query,
                "page[limit]": min(limit, 20),
                "fields[anime]": "canonicalTitle,titles,posterImage,episodeCount,startDate,averageRating,subtype,status",
            },
        )
        return [_anime_to_search_result(item) for item in (response.json().get("data") or [])]

    async def discover(self, access_token: str, filters: SearchFilters) -> GlobalSearchResponse:
        headers = _auth_headers(access_token)
        per_page = min(max(1, filters.per_page), 20)
        params: dict[str, str | int] = {
            "page[limit]": per_page,
            "page[offset]": (filters.page - 1) * per_page,
            "fields[anime]": "canonicalTitle,titles,posterImage,episodeCount,startDate,averageRating,subtype,status,categories",
        }
        if filters.query and filters.query.strip():
            params["filter[text]"] = filters.query.strip()
        if filters.sort == "SCORE":
            params["sort"] = "-averageRating"
        else:
            params["sort"] = "popularityRank"
        if filters.year:
            params["filter[seasonYear]"] = str(filters.year)
        if not filters.is_adult:
            # Kitsu has no global SFW flag per request; cap the age rating instead.
            params["filter[ageRating]"] = "G,PG,R"
        response = await self.client.get(f"{API_URL}/anime", headers=headers, params=params)
        payload = response.json()
        results = [_anime_to_search_result(item) for item in (payload.get("data") or [])]
        has_next = bool((payload.get("links") or {}).get("next"))
        return GlobalSearchResponse(results=results, has_next_page=has_next)

    async def details(self, access_token: str, external_id: int) -> MediaDetails:
        headers = _auth_headers(access_token)
        response = await self.client.get(
            f"{API_URL}/anime/{external_id}",
            headers=headers,
            params={"include": "categories", "fields[anime]": "canonicalTitle,titles,posterImage,coverImage,synopsis,episodeCount,startDate,averageRating,subtype,status,categories"},
        )
        node = response.json().get("data") or {}
        attrs = node.get("attributes") or {}
        included = response.json().get("included") or []
        genres = [inc["attributes"]["title"] for inc in included if inc.get("type") == "categories" and (inc.get("attributes") or {}).get("title")]
        return MediaDetails(
            id=int(node.get("id", external_id)),
            title=attrs.get("canonicalTitle") or str(external_id),
            title_english=(attrs.get("titles") or {}).get("en") or None,
            title_native=(attrs.get("titles") or {}).get("ja_jp") or None,
            synonyms=list((attrs.get("titles") or {}).values()),
            description=attrs.get("synopsis"),
            site_url=f"https://kitsu.app/anime/{node.get('id', external_id)}",
            cover_image=((attrs.get("posterImage") or {}).get("large") or (attrs.get("posterImage") or {}).get("medium")),
            banner_image=((attrs.get("coverImage") or {}).get("large") or None),
            format=_kitsu_subtype_to_format(attrs.get("subtype")),
            status=attrs.get("status"),
            episodes=attrs.get("episodeCount"),
            season_year=_parse_year(attrs.get("startDate")),
            average_score=_parse_score(attrs.get("averageRating")),
            genres=genres,
            studios=[],
            score_format="POINT_10",
            list_entry=None,
        )

    async def preferences(self, access_token: str) -> UserPreferences:
        user = await self.user_info(access_token)
        attrs = user.get("attributes") or {}
        avatar = attrs.get("avatar") or {}
        return UserPreferences(
            username=attrs.get("name") or attrs.get("slug") or "",
            avatar=avatar.get("medium") or avatar.get("small") or avatar.get("original"),
            title_language=_KITSU_TITLE_LANG.get(attrs.get("titleLanguagePreference"), "ROMAJI"),
            score_format="POINT_10",
            display_adult_content=not attrs.get("sfwFilter", True),
        )

    async def update_preferences(self, access_token: str, update: UserPreferencesUpdate) -> UserPreferences:
        user_id = await self._current_user_id(access_token)
        headers = {**_auth_headers(access_token), "Content-Type": "application/vnd.api+json"}
        attrs = {
            "titleLanguagePreference": _TO_KITSU_TITLE_LANG.get(update.title_language, "canonical"),
            "sfwFilter": not update.display_adult_content,
        }
        body = {"data": {"id": user_id, "type": "users", "attributes": attrs}}
        try:
            await self.client.patch(f"{API_URL}/users/{user_id}", headers=headers, json=body)
        except httpx.HTTPStatusError as exc:
            raise KitsuError(_kitsu_http_error("guardar preferencias", exc.response)) from exc
        return await self.preferences(access_token)

    async def update_progress(self, access_token: str, update: ProgressUpdate) -> dict:
        entry_id = await self._find_entry_id(access_token, update.media_id)
        if entry_id:
            return await self._patch_entry(access_token, entry_id, {"progress": update.progress})
        return await self._create_entry(access_token, update.media_id, {"progress": update.progress, "status": "current"})

    async def edit_entry(self, access_token: str, external_id: int, update: MediaEntryUpdate) -> MediaListEntry:
        entry_id = await self._find_entry_id(access_token, external_id)
        attrs: dict = {}
        if update.status is not None:
            attrs["status"] = _TO_KITSU_STATUS.get(update.status, "current")
        if update.progress is not None:
            attrs["progress"] = update.progress
        if update.score is not None:
            kitsu_score = convert_score(update.score, ScoreFormat.POINT_100, ScoreFormat.POINT_10)
            if kitsu_score:
                attrs["ratingTwenty"] = int(kitsu_score * 2)
        if update.repeat is not None:
            attrs["reconsumeCount"] = update.repeat
        if update.notes is not None:
            attrs["notes"] = update.notes
        if entry_id:
            payload = await self._patch_entry(access_token, entry_id, attrs)
        else:
            payload = await self._create_entry(access_token, external_id, attrs)
        return _kitsu_entry_to_list_entry(payload.get("data") or {})

    async def delete_entry(self, access_token: str, external_id: int) -> bool:
        entry_id = await self._find_entry_id(access_token, external_id)
        if not entry_id:
            return False
        headers = _auth_headers(access_token)
        try:
            response = await self.client.delete(f"{API_URL}/library-entries/{entry_id}", headers=headers)
            return response.status_code in {200, 204}
        except httpx.HTTPStatusError:
            return False

    async def _find_entry_id(self, access_token: str, media_id: int) -> str | None:
        user_id = await self._current_user_id(access_token)
        headers = _auth_headers(access_token)
        response = await self.client.get(
            f"{API_URL}/library-entries",
            headers=headers,
            params={"filter[userId]": user_id, "filter[animeId]": str(media_id), "page[limit]": 1},
        )
        data = response.json().get("data") or []
        return str(data[0]["id"]) if data else None

    async def _patch_entry(self, access_token: str, entry_id: str, attrs: dict) -> dict:
        headers = {**_auth_headers(access_token), "Content-Type": "application/vnd.api+json"}
        body = {"data": {"id": entry_id, "type": "libraryEntries", "attributes": attrs}}
        try:
            response = await self.client.patch(
                f"{API_URL}/library-entries/{entry_id}", headers=headers, json=body
            )
        except httpx.HTTPStatusError as exc:
            raise KitsuError(_kitsu_http_error("actualizar entrada", exc.response)) from exc
        return response.json()

    async def _create_entry(self, access_token: str, anime_id: int, attrs: dict) -> dict:
        headers = {**_auth_headers(access_token), "Content-Type": "application/vnd.api+json"}
        body = {
            "data": {
                "type": "libraryEntries",
                "attributes": attrs,
                "relationships": {
                    "anime": {"data": {"id": str(anime_id), "type": "anime"}},
                    "user": {"data": {"id": await self._current_user_id(access_token), "type": "users"}},
                },
            }
        }
        response = await self.client.post(f"{API_URL}/library-entries", headers=headers, json=body)
        return response.json()


def _auth_headers(access_token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/vnd.api+json",
        "User-Agent": _USER_AGENT,
    }


def _kitsu_http_error(action: str, response: httpx.Response) -> str:
    body = response.text or ""
    if "<!DOCTYPE html" in body[:200] or "Just a moment" in body[:600]:
        return (
            f"Kitsu bloqueó la solicitud al {action} (Cloudflare, {response.status_code}). "
            "Inténtalo de nuevo en unos minutos."
        )
    return f"Kitsu {response.status_code} al {action}: {body[:300]}"


def _parse_year(start_date: str | None) -> int | None:
    if not start_date or len(start_date) < 4:
        return None
    try:
        return int(start_date[:4])
    except ValueError:
        return None


def _parse_score(rating: str | None) -> int | None:
    if not rating:
        return None
    try:
        return int(float(rating))
    except ValueError:
        return None


def _kitsu_subtype_to_format(subtype: str | None) -> str | None:
    return {
        "TV": "TV", "movie": "MOVIE", "OVA": "OVA", "ONA": "ONA",
        "special": "SPECIAL", "music": "MUSIC",
    }.get(subtype or "", subtype)


def _entry_to_media_item(entry: dict, included: dict) -> MediaItem | None:
    attrs = entry.get("attributes") or {}
    anime_id = ((entry.get("relationships") or {}).get("anime") or {}).get("data", {}).get("id")
    anime = included.get(anime_id) if anime_id else None
    if not anime:
        return None
    anime_attrs = anime.get("attributes") or {}
    raw_status = attrs.get("status") or ""
    canonical_status = _KITSU_STATUS_MAP.get(raw_status, "CURRENT")
    picture = anime_attrs.get("posterImage") or {}
    start_date = anime_attrs.get("startDate") or ""
    return MediaItem(
        id=int(anime_id),
        title=anime_attrs.get("canonicalTitle") or anime_id,
        status=canonical_status,
        progress=attrs.get("progress") or 0,
        score=_rating_twenty_to_score(attrs.get("ratingTwenty")),
        episodes=anime_attrs.get("episodeCount"),
        cover_image=picture.get("large") or picture.get("medium"),
        year=_parse_year(start_date),
        season=airing_season_from_date(start_date),
        format=_kitsu_subtype_to_format(anime_attrs.get("subtype")),
        media_status=_KITSU_AIRING.get(anime_attrs.get("status") or ""),
        site_url=f"https://kitsu.app/anime/{anime_id}",
    )


def _anime_to_search_result(item: dict) -> SearchResult:
    attrs = item.get("attributes") or {}
    picture = attrs.get("posterImage") or {}
    return SearchResult(
        id=int(item.get("id", 0)),
        title=attrs.get("canonicalTitle") or "",
        title_english=(attrs.get("titles") or {}).get("en") or None,
        title_native=(attrs.get("titles") or {}).get("ja_jp") or None,
        synonyms=[],
        format=_kitsu_subtype_to_format(attrs.get("subtype")),
        status=attrs.get("status"),
        episodes=attrs.get("episodeCount"),
        cover_image=picture.get("large") or picture.get("medium"),
        average_score=_parse_score(attrs.get("averageRating")),
        popularity=0,
        year=_parse_year(attrs.get("startDate")),
    )


def _rating_twenty_to_score(rating: int | None) -> float | None:
    if rating is None:
        return None
    return (rating / 20) * 100


def _kitsu_entry_to_list_entry(data: dict) -> MediaListEntry:
    attrs = data.get("attributes") or {}
    raw_status = attrs.get("status") or "current"
    canonical_status = _KITSU_STATUS_MAP.get(raw_status, "CURRENT")
    rating_twenty = attrs.get("ratingTwenty")
    score = (rating_twenty / 20) * 100 if rating_twenty else 0.0
    return MediaListEntry(
        id=0,
        status=canonical_status,
        score=score,
        progress=attrs.get("progress") or 0,
        repeat=attrs.get("reconsumeCount") or 0,
        private=attrs.get("private") or False,
        notes=attrs.get("notes") or None,
        started_at=FuzzyDate(),
        completed_at=FuzzyDate(),
    )
