from urllib.parse import urlencode

import httpx

from .config import Settings
from .http import RateLimitedClient
from .provider_mappings import (
    from_canonical_status,
    to_canonical_format,
    to_canonical_status,
)
from .models import (
    ActivityItem,
    FuzzyDate,
    GlobalSearchResponse,
    MediaDetails,
    MediaEntryUpdate,
    MediaItem,
    MediaListEntry,
    MediaStatistics,
    ProgressUpdate,
    SearchFilters,
    SearchResult,
    SeasonMedia,
    StatisticGroup,
    StatisticsResponse,
    UserPreferences,
    UserPreferencesUpdate,
)


def _fuzzy_date_to_str(d: dict | None) -> str | None:
    if not d or d.get("year") is None:
        return None
    return f"{d['year']:04d}-{d.get('month') or 1:02d}-{d.get('day') or 1:02d}"


API_URL = "https://graphql.anilist.co"
AUTHORIZE_URL = "https://anilist.co/api/v2/oauth/authorize"
TOKEN_URL = "https://anilist.co/api/v2/oauth/token"

VIEWER_QUERY = "query Viewer { Viewer { id name } }"

LIST_QUERY = """
query ViewerList($userId: Int!) {
  MediaListCollection(userId: $userId, type: ANIME, sort: UPDATED_TIME_DESC) {
    lists { entries {
      mediaId status progress score updatedAt
      startedAt { year month day }
      completedAt { year month day }
      media {
        id episodes format seasonYear siteUrl synonyms genres
        title { userPreferred romaji english native }
        coverImage { large }
      }
    } }
  }
}
"""

UPDATE_MUTATION = """
mutation UpdateProgress($mediaId: Int!, $progress: Int!, $status: MediaListStatus) {
  SaveMediaListEntry(mediaId: $mediaId, progress: $progress, status: $status) {
    id status progress
  }
}
"""

ACTIVITY_QUERY = """
query Activity($userId: Int!, $page: Int!, $perPage: Int!) {
  Page(page: $page, perPage: $perPage) {
    activities(userId: $userId, sort: ID_DESC, type: ANIME_LIST) {
      ... on ListActivity {
        id status progress createdAt
        media { id title { userPreferred } coverImage { medium } }
      }
    }
  }
}
"""

SEASON_QUERY = """
query Season($season: MediaSeason!, $year: Int!, $page: Int!, $perPage: Int!) {
  Page(page: $page, perPage: $perPage) {
    media(
      type: ANIME
      season: $season
      seasonYear: $year
      isAdult: false
      sort: [POPULARITY_DESC]
    ) {
      id format status episodes averageScore popularity
      startDate { year month day }
      title { userPreferred }
      coverImage { large }
      studios { nodes { name } }
      nextAiringEpisode { episode airingAt }
    }
  }
}
"""

STATISTICS_QUERY = """
query Statistics {
  Viewer {
    statistics {
      anime {
        count episodesWatched minutesWatched meanScore
        genres(limit: 10, sort: COUNT_DESC) { genre count }
        statuses(sort: COUNT_DESC) { status count }
        formats(sort: COUNT_DESC) { format count }
        releaseYears(sort: COUNT_DESC) { releaseYear count }
        studios(limit: 10, sort: COUNT_DESC) { studio count }
        countries(sort: COUNT_DESC) { country count }
      }
      manga {
        count chaptersRead meanScore
        genres(limit: 10, sort: COUNT_DESC) { genre count }
        statuses(sort: COUNT_DESC) { status count }
        formats(sort: COUNT_DESC) { format count }
        releaseYears(sort: COUNT_DESC) { releaseYear count }
        studios(limit: 10, sort: COUNT_DESC) { studio count }
        countries(sort: COUNT_DESC) { country count }
      }
    }
  }
}
"""

DETAIL_QUERY = """
query MediaDetails($id: Int!) {
  Viewer { id mediaListOptions { scoreFormat } }
  Media(id: $id, type: ANIME) {
    id siteUrl description(asHtml: false) format status source season seasonYear
    episodes duration genres countryOfOrigin averageScore synonyms bannerImage
    title { userPreferred romaji english native }
    coverImage { extraLarge color }
    studios { nodes { name } }
    nextAiringEpisode { episode airingAt }
  }
}
"""

ENTRY_QUERY = """
query MediaEntry($id: Int!, $userId: Int!) {
  MediaList(mediaId: $id, userId: $userId) {
    id status score progress repeat private notes
    startedAt { year month day }
    completedAt { year month day }
  }
}
"""

EDIT_ENTRY_MUTATION = """
mutation EditEntry(
  $mediaId: Int!
  $status: MediaListStatus
  $progress: Int
  $score: Float
  $repeat: Int
  $private: Boolean
  $notes: String
  $startedAt: FuzzyDateInput
  $completedAt: FuzzyDateInput
) {
  SaveMediaListEntry(
    mediaId: $mediaId
    status: $status
    progress: $progress
    score: $score
    repeat: $repeat
    private: $private
    notes: $notes
    startedAt: $startedAt
    completedAt: $completedAt
  ) { id status score progress repeat private notes startedAt { year month day } completedAt { year month day } }
}
"""

DELETE_ENTRY_MUTATION = """
mutation DeleteEntry($id: Int!) {
  DeleteMediaListEntry(id: $id) { deleted }
}
"""

MANGA_LIST_QUERY = """
query ViewerMangaList($userId: Int!) {
  MediaListCollection(userId: $userId, type: MANGA, sort: UPDATED_TIME_DESC) {
    lists { entries {
      mediaId status progress score updatedAt
      startedAt { year month day }
      completedAt { year month day }
      media {
        id chapters volumes format status siteUrl synonyms genres
        title { userPreferred romaji english native }
        coverImage { large }
      }
    } }
  }
}
"""

MANGA_DETAIL_QUERY = """
query MangaDetails($id: Int!) {
  Viewer { id mediaListOptions { scoreFormat } }
  Media(id: $id, type: MANGA) {
    id siteUrl description(asHtml: false) format status source
    chapters volumes genres countryOfOrigin averageScore synonyms bannerImage
    title { userPreferred romaji english native }
    coverImage { extraLarge color }
    studios { nodes { name } }
  }
}
"""

MANGA_ENTRY_QUERY = """
query MangaEntry($id: Int!, $userId: Int!) {
  MediaList(mediaId: $id, userId: $userId) {
    id status score progress repeat private notes
    startedAt { year month day }
    completedAt { year month day }
  }
}
"""

ALLOWED_ANIME_FORMATS = ["TV", "TV_SHORT", "MOVIE", "SPECIAL", "OVA", "ONA"]

SEARCH_QUERY = """
query Search($query: String!, $page: Int!, $perPage: Int!, $formats: [MediaFormat]) {
  Page(page: $page, perPage: $perPage) {
    media(type: ANIME, search: $query, isAdult: false, sort: [SEARCH_MATCH], format_in: $formats) {
      id format status episodes averageScore popularity
      title { userPreferred }
      coverImage { large }
    }
  }
}
"""

SEARCH_PAGINATED_QUERY = """
query SearchPaginated($query: String!, $page: Int!, $perPage: Int!, $formats: [MediaFormat]) {
  Page(page: $page, perPage: $perPage) {
    pageInfo { hasNextPage }
    media(type: ANIME, search: $query, isAdult: false, sort: [SEARCH_MATCH], format_in: $formats) {
      id format status episodes averageScore popularity
      title { userPreferred }
      coverImage { large }
    }
  }
}
"""

SEARCH_MANGA_QUERY = """
query SearchManga($query: String!, $page: Int!, $perPage: Int!) {
  Page(page: $page, perPage: $perPage) {
    media(type: MANGA, search: $query, isAdult: false, sort: [SEARCH_MATCH]) {
      id format status chapters volumes averageScore popularity
      title { userPreferred }
      coverImage { large }
    }
  }
}
"""

SEARCH_MANGA_PAGINATED_QUERY = """
query SearchMangaPaginated($query: String!, $page: Int!, $perPage: Int!) {
  Page(page: $page, perPage: $perPage) {
    pageInfo { hasNextPage }
    media(type: MANGA, search: $query, isAdult: false, sort: [SEARCH_MATCH]) {
      id format status chapters volumes averageScore popularity
      title { userPreferred }
      coverImage { large }
    }
  }
}
"""

POPULAR_QUERY = """
query Popular(
  $page: Int!,
  $perPage: Int!,
  $genre: String,
  $format: MediaFormat,
  $year: Int,
  $status: MediaStatus,
  $isAdult: Boolean,
  $sort: [MediaSort!]
) {
  Page(page: $page, perPage: $perPage) {
    pageInfo { hasNextPage }
    media(
      type: ANIME
      genre: $genre
      format: $format
      seasonYear: $year
      status: $status
      isAdult: $isAdult
      sort: $sort
    ) {
      id format status episodes averageScore popularity
      title { userPreferred }
      coverImage { large }
    }
  }
}
"""

POPULAR_MANGA_QUERY = """
query PopularManga(
  $page: Int!,
  $perPage: Int!,
  $genre: String,
  $format: MediaFormat,
  $status: MediaStatus,
  $isAdult: Boolean,
  $sort: [MediaSort!]
) {
  Page(page: $page, perPage: $perPage) {
    pageInfo { hasNextPage }
    media(
      type: MANGA
      genre: $genre
      format: $format
      status: $status
      isAdult: $isAdult
      sort: $sort
    ) {
      id format status chapters volumes averageScore popularity
      title { userPreferred }
      coverImage { large }
    }
  }
}
"""

PREFERENCES_QUERY = """
query Preferences {
  Viewer {
    name avatar { large }
    options { titleLanguage displayAdultContent }
    mediaListOptions { scoreFormat }
  }
}
"""

UPDATE_PREFERENCES_MUTATION = """
mutation UpdatePreferences(
  $titleLanguage: UserTitleLanguage
  $scoreFormat: ScoreFormat
  $displayAdultContent: Boolean
) {
  UpdateUser(
    titleLanguage: $titleLanguage
    scoreFormat: $scoreFormat
    displayAdultContent: $displayAdultContent
  ) {
    name avatar { large }
    options { titleLanguage displayAdultContent }
    mediaListOptions { scoreFormat }
  }
}
"""


class AniListError(RuntimeError):
    pass


_client = RateLimitedClient(requests_per_minute=90)


class AniListClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = _client

    def authorization_url(self, state: str) -> str:
        if not self.settings.anilist_client_id:
            raise AniListError("AniList client ID is not configured")
        query = {
            "client_id": self.settings.anilist_client_id,
            "redirect_uri": self.settings.anilist_redirect_uri,
            "response_type": "code",
            "state": state,
        }
        return f"{AUTHORIZE_URL}?{urlencode(query)}"

    async def exchange_code(self, code: str) -> str:
        if not self.settings.anilist_client_id or not self.settings.anilist_client_secret:
            raise AniListError("AniList OAuth credentials are not configured")
        payload = {
            "grant_type": "authorization_code",
            "client_id": self.settings.anilist_client_id,
            "client_secret": self.settings.anilist_client_secret,
            "redirect_uri": self.settings.anilist_redirect_uri,
            "code": code,
        }
        response = await self.client.post(TOKEN_URL, json=payload)
        return response.json()["access_token"]

    async def graphql(self, token: str, query: str, variables: dict | None = None) -> dict:
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        response = await self.client.post(
            API_URL, headers=headers, json={"query": query, "variables": variables or {}}
        )
        payload = response.json()
        if payload.get("errors"):
            raise AniListError(payload["errors"][0].get("message", "AniList request failed"))
        return payload["data"]

    async def media_list(self, token: str) -> list[MediaItem]:
        viewer = await self.graphql(token, VIEWER_QUERY)
        data = await self.graphql(token, LIST_QUERY, {"userId": viewer["Viewer"]["id"]})
        entries = [
            entry
            for media_list in data["MediaListCollection"]["lists"]
            for entry in media_list["entries"]
        ]
        return [
            MediaItem(
                id=entry["media"]["id"],
                title=entry["media"]["title"]["userPreferred"],
                status=to_canonical_status("anilist", entry["status"]).value,
                progress=entry["progress"],
                score=entry.get("score") or None,
                episodes=entry["media"]["episodes"],
                cover_image=entry["media"]["coverImage"]["large"],
                title_romaji=entry["media"]["title"].get("romaji"),
                title_english=entry["media"]["title"].get("english"),
                title_native=entry["media"]["title"].get("native"),
                synonyms=entry["media"].get("synonyms") or [],
                genres=entry["media"].get("genres") or [],
                year=entry["media"].get("seasonYear"),
                format=to_canonical_format("anilist", entry["media"].get("format")).value,
                site_url=entry["media"].get("siteUrl"),
                updated_at=entry.get("updatedAt"),
                started_at=_fuzzy_date_to_str(entry.get("startedAt")),
                completed_at=_fuzzy_date_to_str(entry.get("completedAt")),
            )
            for entry in entries
        ]

    async def search(self, token: str, query: str, limit: int = 10) -> list[SearchResult]:
        data = await self.graphql(
            token,
            SEARCH_QUERY,
            {"query": query, "page": 1, "perPage": limit, "formats": ALLOWED_ANIME_FORMATS},
        )
        return [
            SearchResult(
                id=item["id"],
                title=item["title"]["userPreferred"],
                format=to_canonical_format("anilist", item.get("format")).value,
                status=item.get("status"),
                episodes=item.get("episodes"),
                average_score=item.get("averageScore"),
                popularity=item.get("popularity") or 0,
                cover_image=item["coverImage"]["large"],
            )
            for item in data["Page"]["media"]
        ]

    async def search_manga(self, token: str, query: str, limit: int = 10) -> list[SearchResult]:
        data = await self.graphql(
            token,
            SEARCH_MANGA_QUERY,
            {"query": query, "page": 1, "perPage": limit},
        )
        return [
            SearchResult(
                id=item["id"],
                title=item["title"]["userPreferred"],
                format=to_canonical_format("anilist", item.get("format")).value,
                status=item.get("status"),
                chapters=item.get("chapters"),
                volumes=item.get("volumes"),
                average_score=item.get("averageScore"),
                popularity=item.get("popularity") or 0,
                cover_image=item["coverImage"]["large"],
            )
            for item in data["Page"]["media"]
        ]

    async def discover(self, token: str, filters: SearchFilters) -> GlobalSearchResponse:
        is_manga = filters.media_type == "MANGA"
        per_page = max(1, min(filters.per_page, 50))
        has_query = bool(filters.query and filters.query.strip())
        anilist_sort = ["SCORE_DESC"] if filters.sort == "SCORE" else ["POPULARITY_DESC"]
        if is_manga:
            if has_query:
                data = await self.graphql(
                    token,
                    SEARCH_MANGA_PAGINATED_QUERY,
                    {
                        "query": filters.query.strip(),
                        "page": filters.page,
                        "perPage": per_page,
                    },
                )
            else:
                data = await self.graphql(
                    token,
                    POPULAR_MANGA_QUERY,
                    {
                        "page": filters.page,
                        "perPage": per_page,
                        "genre": filters.genre,
                        "format": filters.format,
                        "status": filters.status,
                        "isAdult": filters.is_adult,
                        "sort": anilist_sort,
                    },
                )
        else:
            if has_query:
                data = await self.graphql(
                    token,
                    SEARCH_PAGINATED_QUERY,
                    {
                        "query": filters.query.strip(),
                        "page": filters.page,
                        "perPage": per_page,
                        "formats": ALLOWED_ANIME_FORMATS,
                    },
                )
            else:
                data = await self.graphql(
                    token,
                    POPULAR_QUERY,
                    {
                        "page": filters.page,
                        "perPage": per_page,
                        "genre": filters.genre,
                        "format": filters.format,
                        "year": filters.year,
                        "status": filters.status,
                        "isAdult": filters.is_adult,
                        "sort": anilist_sort,
                    },
                )
        page = data["Page"]
        return GlobalSearchResponse(
            results=[
                SearchResult(
                    id=item["id"],
                    title=item["title"]["userPreferred"],
                    format=to_canonical_format("anilist", item.get("format")).value,
                    status=item.get("status"),
                    episodes=None if is_manga else item.get("episodes"),
                    chapters=item.get("chapters") if is_manga else None,
                    volumes=item.get("volumes") if is_manga else None,
                    average_score=item.get("averageScore"),
                    popularity=item.get("popularity") or 0,
                    cover_image=item["coverImage"]["large"],
                )
                for item in page["media"]
            ],
            has_next_page=page["pageInfo"]["hasNextPage"],
        )

    async def update_progress(self, token: str, update: ProgressUpdate) -> dict:
        variables = {
            "mediaId": update.media_id,
            "progress": update.progress,
            "status": (
                from_canonical_status("anilist", update.status)
                if update.status is not None
                else None
            ),
        }
        return await self.graphql(
            token, UPDATE_MUTATION, {key: value for key, value in variables.items() if value is not None}
        )

    async def activity(self, token: str, page: int = 1, limit: int = 30) -> list[ActivityItem]:
        viewer = await self.graphql(token, VIEWER_QUERY)
        data = await self.graphql(
            token,
            ACTIVITY_QUERY,
            {"userId": viewer["Viewer"]["id"], "page": page, "perPage": limit},
        )
        return [
            ActivityItem(
                id=item["id"],
                status=item["status"],
                progress=item.get("progress"),
                created_at=item["createdAt"],
                media_id=item["media"]["id"],
                title=item["media"]["title"]["userPreferred"],
                cover_image=item["media"]["coverImage"]["medium"],
            )
            for item in data["Page"]["activities"]
            if item and item.get("media")
        ]

    async def season(
        self, token: str, season: str, year: int, page: int = 1, per_page: int = 50
    ) -> list[SeasonMedia]:
        data = await self.graphql(
            token,
            SEASON_QUERY,
            {"season": season, "year": year, "page": page, "perPage": per_page},
        )
        return [
            SeasonMedia(
                id=item["id"],
                title=item["title"]["userPreferred"],
                format=to_canonical_format("anilist", item.get("format")).value,
                status=item.get("status"),
                episodes=item.get("episodes"),
                average_score=item.get("averageScore"),
                popularity=item.get("popularity") or 0,
                start_date=FuzzyDate(**(item.get("startDate") or {})),
                cover_image=item["coverImage"]["large"],
                studios=[studio["name"] for studio in (item.get("studios") or {}).get("nodes", [])],
                next_episode=(item.get("nextAiringEpisode") or {}).get("episode"),
                next_airing_at=(item.get("nextAiringEpisode") or {}).get("airingAt"),
            )
            for item in data["Page"]["media"]
        ]

    def _build_statistics_response(self, data: dict) -> StatisticsResponse:
        def _groups(items: list, key: str) -> list[StatisticGroup]:
            return [StatisticGroup(label=str(item[key]), count=item["count"]) for item in items]

        anime = data["Viewer"]["statistics"]["anime"]
        manga = data["Viewer"]["statistics"]["manga"]
        return StatisticsResponse(
            anime=MediaStatistics(
                count=anime["count"],
                episodes_watched=anime["episodesWatched"],
                minutes_watched=anime["minutesWatched"],
                mean_score=anime["meanScore"],
                genres=_groups(anime["genres"], "genre"),
                statuses=_groups(anime["statuses"], "status"),
                formats=_groups(anime["formats"], "format"),
                release_years=_groups(anime["releaseYears"], "releaseYear"),
                studios=_groups(anime["studios"], "studio"),
                countries=_groups(anime["countries"], "country"),
            ),
            manga=MediaStatistics(
                count=manga["count"],
                episodes_watched=manga["chaptersRead"],
                minutes_watched=0,
                mean_score=manga["meanScore"],
                genres=_groups(manga["genres"], "genre"),
                statuses=_groups(manga["statuses"], "status"),
                formats=_groups(manga["formats"], "format"),
                release_years=_groups(manga["releaseYears"], "releaseYear"),
                studios=_groups(manga["studios"], "studio"),
                countries=_groups(manga["countries"], "country"),
            ),
        )

    async def statistics(self, token: str) -> StatisticsResponse:
        data = await self.graphql(token, STATISTICS_QUERY)
        return self._build_statistics_response(data)

    async def media_details(self, token: str, media_id: int) -> MediaDetails:
        data = await self.graphql(token, DETAIL_QUERY, {"id": media_id})
        media = data["Media"]
        try:
            entry_data = await self.graphql(
                token,
                ENTRY_QUERY,
                {"id": media_id, "userId": data["Viewer"]["id"]},
            )
            entry = entry_data.get("MediaList")
        except httpx.HTTPStatusError as error:
            if error.response.status_code != 404:
                raise
            entry = None
        next_airing = media.get("nextAiringEpisode") or {}
        return MediaDetails(
            id=media["id"],
            title=media["title"]["userPreferred"],
            title_romaji=media["title"].get("romaji"),
            title_english=media["title"].get("english"),
            title_native=media["title"].get("native"),
            synonyms=media.get("synonyms") or [],
            description=media.get("description"),
            site_url=media["siteUrl"],
            banner_image=media.get("bannerImage"),
            cover_image=media["coverImage"].get("extraLarge"),
            color=media["coverImage"].get("color"),
            format=to_canonical_format("anilist", media.get("format")).value,
            status=media.get("status"),
            source=media.get("source"),
            season=media.get("season"),
            season_year=media.get("seasonYear"),
            episodes=media.get("episodes"),
            duration=media.get("duration"),
            genres=media.get("genres") or [],
            studios=[studio["name"] for studio in media["studios"]["nodes"]],
            country=media.get("countryOfOrigin"),
            average_score=media.get("averageScore"),
            next_episode=next_airing.get("episode"),
            next_airing_at=next_airing.get("airingAt"),
            score_format=data["Viewer"]["mediaListOptions"]["scoreFormat"],
            list_entry=self._list_entry(entry) if entry else None,
        )

    async def edit_entry(
        self, token: str, media_id: int, update: MediaEntryUpdate
    ) -> MediaListEntry:
        values = update.model_dump(exclude_unset=True)
        variables = {"mediaId": media_id}
        graphql_names = {
            "started_at": "startedAt",
            "completed_at": "completedAt",
        }
        for key, value in values.items():
            if key == "status" and value is not None:
                value = from_canonical_status("anilist", value)
            variables[graphql_names.get(key, key)] = value
        data = await self.graphql(token, EDIT_ENTRY_MUTATION, variables)
        return self._list_entry(data["SaveMediaListEntry"])

    async def delete_entry(self, token: str, entry_id: int) -> bool:
        data = await self.graphql(token, DELETE_ENTRY_MUTATION, {"id": entry_id})
        return bool(data["DeleteMediaListEntry"]["deleted"])

    async def media_list_manga(self, token: str) -> list[MediaItem]:
        viewer = await self.graphql(token, VIEWER_QUERY)
        data = await self.graphql(
            token, MANGA_LIST_QUERY, {"userId": viewer["Viewer"]["id"]}
        )
        entries = [
            entry
            for media_list in data["MediaListCollection"]["lists"]
            for entry in media_list["entries"]
        ]
        return [
            MediaItem(
                id=entry["media"]["id"],
                title=entry["media"]["title"]["userPreferred"],
                status=to_canonical_status("anilist", entry["status"]).value,
                progress=entry["progress"],
                score=entry.get("score") or None,
                chapters=entry["media"].get("chapters"),
                volumes=entry["media"].get("volumes"),
                cover_image=entry["media"]["coverImage"]["large"],
                title_romaji=entry["media"]["title"].get("romaji"),
                title_english=entry["media"]["title"].get("english"),
                title_native=entry["media"]["title"].get("native"),
                synonyms=entry["media"].get("synonyms") or [],
                genres=entry["media"].get("genres") or [],
                format=to_canonical_format("anilist", entry["media"].get("format")).value,
                site_url=entry["media"].get("siteUrl"),
                media_type="MANGA",
                updated_at=entry.get("updatedAt"),
                started_at=_fuzzy_date_to_str(entry.get("startedAt")),
                completed_at=_fuzzy_date_to_str(entry.get("completedAt")),
            )
            for entry in entries
        ]

    async def manga_details(self, token: str, media_id: int) -> MediaDetails:
        data = await self.graphql(token, MANGA_DETAIL_QUERY, {"id": media_id})
        media = data["Media"]
        try:
            entry_data = await self.graphql(
                token,
                MANGA_ENTRY_QUERY,
                {"id": media_id, "userId": data["Viewer"]["id"]},
            )
            entry = entry_data.get("MediaList")
        except httpx.HTTPStatusError as error:
            if error.response.status_code != 404:
                raise
            entry = None
        return MediaDetails(
            id=media["id"],
            title=media["title"]["userPreferred"],
            title_romaji=media["title"].get("romaji"),
            title_english=media["title"].get("english"),
            title_native=media["title"].get("native"),
            synonyms=media.get("synonyms") or [],
            description=media.get("description"),
            site_url=media["siteUrl"],
            banner_image=media.get("bannerImage"),
            cover_image=media["coverImage"].get("extraLarge"),
            color=media["coverImage"].get("color"),
            format=to_canonical_format("anilist", media.get("format")).value,
            media_type="MANGA",
            status=media.get("status"),
            source=media.get("source"),
            chapters=media.get("chapters"),
            volumes=media.get("volumes"),
            genres=media.get("genres") or [],
            studios=[studio["name"] for studio in media["studios"]["nodes"]],
            country=media.get("countryOfOrigin"),
            average_score=media.get("averageScore"),
            score_format=data["Viewer"]["mediaListOptions"]["scoreFormat"],
            list_entry=self._list_entry(entry) if entry else None,
        )

    async def preferences(self, token: str) -> UserPreferences:
        data = await self.graphql(token, PREFERENCES_QUERY)
        return self._preferences(data["Viewer"])

    async def update_preferences(
        self, token: str, update: UserPreferencesUpdate
    ) -> UserPreferences:
        variables = {
            "titleLanguage": update.title_language,
            "scoreFormat": update.score_format,
            "displayAdultContent": update.display_adult_content,
        }
        data = await self.graphql(token, UPDATE_PREFERENCES_MUTATION, variables)
        return self._preferences(data["UpdateUser"])

    @staticmethod
    def _preferences(viewer: dict) -> UserPreferences:
        return UserPreferences(
            username=viewer["name"],
            avatar=(viewer.get("avatar") or {}).get("large"),
            title_language=viewer["options"]["titleLanguage"],
            score_format=viewer["mediaListOptions"]["scoreFormat"],
            display_adult_content=bool(viewer["options"]["displayAdultContent"]),
        )

    @staticmethod
    def _list_entry(entry: dict) -> MediaListEntry:
        def fuzzy_date(value: dict | None) -> FuzzyDate:
            return FuzzyDate(**(value or {}))

        return MediaListEntry(
            id=entry["id"],
            status=to_canonical_status("anilist", entry["status"]).value,
            score=entry.get("score") or 0,
            progress=entry.get("progress") or 0,
            repeat=entry.get("repeat") or 0,
            private=bool(entry.get("private")),
            notes=entry.get("notes"),
            started_at=fuzzy_date(entry.get("startedAt")),
            completed_at=fuzzy_date(entry.get("completedAt")),
        )
