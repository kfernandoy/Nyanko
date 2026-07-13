from urllib.parse import urlencode

import httpx

from .config import Settings
from .http import RateLimitedClient
from .provider_mappings import (
    ScoreFormat,
    convert_score,
    from_canonical_status,
    to_canonical_format,
    to_canonical_status,
)
from .models import (
    ActivityItem,
    CharacterEdge,
    CharacterImage,
    CharacterName,
    CharacterNode,
    FuzzyDate,
    GlobalSearchResponse,
    MediaDetails,
    MediaEntryUpdate,
    MediaItem,
    MediaListEntry,
    MediaStatistics,
    ProgressUpdate,
    RecommendationItem,
    RelationEdge,
    SearchFilters,
    SearchResult,
    SeasonMedia,
    StaffEdge,
    StatisticGroup,
    StatisticsResponse,
    TrailerInfo,
    UserPreferences,
    UserPreferencesUpdate,
    VoiceActorNode,
)


def _fuzzy_date_to_str(d: dict | None) -> str | None:
    if not d or d.get("year") is None:
        return None
    return f"{d['year']:04d}-{d.get('month') or 1:02d}-{d.get('day') or 1:02d}"


API_URL = "https://graphql.anilist.co"
AUTHORIZE_URL = "https://anilist.co/api/v2/oauth/authorize"
TOKEN_URL = "https://anilist.co/api/v2/oauth/token"

VIEWER_QUERY = "query Viewer { Viewer { id name } }"
SCORE_FORMAT_QUERY = "query ScoreFormat { Viewer { mediaListOptions { scoreFormat } } }"

LIST_QUERY = """
query ViewerList($userId: Int!) {
  Viewer { mediaListOptions { scoreFormat } }
  MediaListCollection(userId: $userId, type: ANIME, sort: UPDATED_TIME_DESC) {
    lists { entries {
      mediaId status progress score updatedAt
      startedAt { year month day }
      completedAt { year month day }
      media {
        id idMal episodes format season seasonYear siteUrl synonyms genres status updatedAt
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
      id format status episodes averageScore popularity genres
      description(asHtml: false)
      startDate { year month day }
      title { userPreferred }
      coverImage { large color }
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
        studios(limit: 10, sort: COUNT_DESC) { studio { id name } count }
        countries(sort: COUNT_DESC) { country count }
      }
      manga {
        count chaptersRead meanScore
        genres(limit: 10, sort: COUNT_DESC) { genre count }
        statuses(sort: COUNT_DESC) { status count }
        formats(sort: COUNT_DESC) { format count }
        releaseYears(sort: COUNT_DESC) { releaseYear count }
        studios(limit: 10, sort: COUNT_DESC) { studio { id name } count }
        countries(sort: COUNT_DESC) { country count }
      }
    }
  }
}
"""

# Campos del detalle de anime, compartidos por la query individual y la de lote
# (id_in) que usa el backfill — así ambas piden exactamente lo mismo sin duplicar.
_ANIME_DETAIL_FIELDS = """
    id updatedAt siteUrl description(asHtml: false) format status source season seasonYear
    episodes duration genres countryOfOrigin averageScore synonyms bannerImage
    title { userPreferred romaji english native }
    coverImage { extraLarge color }
    studios { nodes { name } }
    nextAiringEpisode { episode airingAt }
    trailer { id site }
    characters(sort: [ROLE, RELEVANCE], perPage: 10) {
      edges {
        role
        node { name { full } image { medium } }
        voiceActors(language: JAPANESE) { name { full } image { medium } }
      }
    }
    staff(sort: RELEVANCE, perPage: 8) {
      edges {
        role
        node { name { full } image { medium } }
      }
    }
    relations {
      edges {
        relationType
        node { id format title { userPreferred } coverImage { large } }
      }
    }
    recommendations(sort: RATING_DESC, perPage: 6) {
      nodes {
        rating
        mediaRecommendation {
          id format title { userPreferred } coverImage { large }
        }
      }
    }
"""

DETAIL_QUERY = (
    "query MediaDetails($id: Int!) {\n"
    "  Viewer { id mediaListOptions { scoreFormat } }\n"
    "  Media(id: $id, type: ANIME) {" + _ANIME_DETAIL_FIELDS + "  }\n"
    "}\n"
)

# Campos del LOTE del backfill: todo lo que la grid pinta, SIN los cuatro bloques de
# conexiones (characters/staff/relations/recommendations). Esos cuatro son el 95% del
# coste y NO se ven en la grid: solo hacen falta al abrir una ficha, y ahí se bajan.
#
# El porqué, medido contra AniList el 2026-07-12 con 50 ids:
#   completa (con los 4 bloques) : 17-25 s · 434 KB
#   esta                         :  1,3-2,5 s · 91,6 KB
# Diez veces menos. Sobre una biblioteca de 1.811 títulos son ~2 min en vez de ~15.
#
# OJO — el comentario original decía "probado ~3.5s / 434 KB" para la query completa, y
# era cierto cuando se escribió. AniList se ha degradado desde entonces (~6x más lenta, y
# su rate limit bajó de 90 a 30 req/min: la cabecera X-RateLimit-Limit ahora dice 30).
# El backfill no se rompió por un cambio nuestro: se rompió porque el proveedor cambió
# bajo nuestros pies. Si AniList se recupera, esta query ligera sigue siendo la correcta
# — pedir 4x más datos de los que se pintan nunca fue buena idea.
_ANIME_LIST_FIELDS = """
    id updatedAt siteUrl description(asHtml: false) format status source season seasonYear
    episodes duration genres countryOfOrigin averageScore synonyms bannerImage
    title { userPreferred romaji english native }
    coverImage { extraLarge color }
    studios { nodes { name } }
    nextAiringEpisode { episode airingAt }
    trailer { id site }
"""

BATCH_DETAIL_QUERY = (
    "query BatchMediaDetails($ids: [Int]) {\n"
    "  Viewer { mediaListOptions { scoreFormat } }\n"
    "  Page(perPage: 50) {\n"
    "    media(id_in: $ids, type: ANIME) {" + _ANIME_LIST_FIELDS + "    }\n"
    "  }\n"
    "}\n"
)

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
  Viewer { mediaListOptions { scoreFormat } }
  MediaListCollection(userId: $userId, type: MANGA, sort: UPDATED_TIME_DESC) {
    lists { entries {
      mediaId status progress score updatedAt
      startedAt { year month day }
      completedAt { year month day }
      media {
        id chapters volumes format status siteUrl synonyms genres updatedAt
        title { userPreferred romaji english native }
        coverImage { large }
      }
    } }
  }
}
"""

_MANGA_DETAIL_FIELDS = """
    id updatedAt siteUrl description(asHtml: false) format status source
    chapters volumes genres countryOfOrigin averageScore synonyms bannerImage
    title { userPreferred romaji english native }
    coverImage { extraLarge color }
    studios { nodes { name } }
    staff(sort: RELEVANCE, perPage: 8) {
      edges {
        role
        node { name { full } image { medium } }
      }
    }
    relations {
      edges {
        relationType
        node { id format title { userPreferred } coverImage { large } }
      }
    }
    recommendations(sort: RATING_DESC, perPage: 6) {
      nodes {
        rating
        mediaRecommendation {
          id format title { userPreferred } coverImage { large }
        }
      }
    }
"""

MANGA_DETAIL_QUERY = (
    "query MangaDetails($id: Int!) {\n"
    "  Viewer { id mediaListOptions { scoreFormat } }\n"
    "  Media(id: $id, type: MANGA) {" + _MANGA_DETAIL_FIELDS + "  }\n"
    "}\n"
)

# Igual que BATCH_DETAIL_QUERY (anime) pero para manga: sin la MediaList por item (la
# entrada del usuario se reconstruye desde la biblioteca local al servir el detalle), y
# sin los bloques de conexiones (staff/relations/recommendations) por el mismo motivo que
# el anime: no se pintan en la grid y multiplican el coste de la request. Se bajan al
# abrir la ficha.
_MANGA_LIST_FIELDS = """
    id updatedAt siteUrl description(asHtml: false) format status source
    chapters volumes genres countryOfOrigin averageScore synonyms bannerImage
    title { userPreferred romaji english native }
    coverImage { extraLarge color }
    studios { nodes { name } }
"""

MANGA_BATCH_DETAIL_QUERY = (
    "query BatchMangaDetails($ids: [Int]) {\n"
    "  Viewer { mediaListOptions { scoreFormat } }\n"
    "  Page(perPage: 50) {\n"
    "    media(id_in: $ids, type: MANGA) {" + _MANGA_LIST_FIELDS + "    }\n"
    "  }\n"
    "}\n"
)

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
      id format status episodes averageScore popularity seasonYear genres synonyms
      title { userPreferred romaji english native }
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
      id format status episodes averageScore popularity seasonYear genres synonyms
      title { userPreferred romaji english native }
      coverImage { large }
    }
  }
}
"""

SEARCH_MANGA_QUERY = """
query SearchManga($query: String!, $page: Int!, $perPage: Int!) {
  Page(page: $page, perPage: $perPage) {
    media(type: MANGA, search: $query, isAdult: false, sort: [SEARCH_MATCH]) {
      id format status chapters volumes averageScore popularity seasonYear genres synonyms
      title { userPreferred romaji english native }
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
      id format status chapters volumes averageScore popularity seasonYear genres synonyms
      title { userPreferred romaji english native }
      coverImage { large }
    }
  }
}
"""

_POPULAR_ANIME_FIELDS = "id format status episodes averageScore popularity seasonYear genres synonyms"
_POPULAR_MANGA_FIELDS = "id format status chapters volumes averageScore popularity seasonYear genres synonyms"

# AniList's null handling for filter args is inconsistent (e.g. `status: null` and
# `format: null` combined return nothing), so only declare/apply the filters that are
# actually set. type/sort are always included; `isAdult: false` is added only to exclude
# adult content (omitting it returns both, which is how we "include adult").
_POPULAR_FILTER_DEFS = {
    "genre": ("$genre: String", "genre: $genre"),
    "format": ("$format: MediaFormat", "format: $format"),
    "year": ("$year: Int", "seasonYear: $year"),
    "status": ("$status: MediaStatus", "status: $status"),
    "season": ("$season: MediaSeason", "season: $season"),
}


def _build_popular_query(media_type: str, fields: str, active: list[str], include_adult: bool) -> str:
    decls = ["$page: Int!", "$perPage: Int!", "$sort: [MediaSort!]"]
    args = [f"type: {media_type}", "sort: $sort"]
    if not include_adult:
        args.append("isAdult: false")
    for name in active:
        decl, arg = _POPULAR_FILTER_DEFS[name]
        decls.append(decl)
        args.append(arg)
    return f"""
query Popular({", ".join(decls)}) {{
  Page(page: $page, perPage: $perPage) {{
    pageInfo {{ hasNextPage }}
    media({" ".join(args)}) {{
      {fields}
      title {{ userPreferred romaji english native }}
      coverImage {{ large }}
    }}
  }}
}}
"""


def _allow_adult(query: str) -> str:
    # search queries hard-code `isAdult: false`; drop it to include adult results
    return query.replace("isAdult: false, ", "")


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
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


# 90 es el valor INICIAL y el TECHO, no el presupuesto: AniList anuncia el suyo real en
# X-RateLimit-Limit (hoy dice 30) y el limitador lo sigue, degradándose y recuperándose
# solo. El techo es lo que impide que una cabecera absurda desactive el limitador.
_client = RateLimitedClient(requests_per_minute=90)

# Los 15 s por defecto del RateLimitedClient valen para las peticiones normales (una
# búsqueda va en ~2 s), pero NO para los lotes del backfill: medido contra AniList con
# una biblioteca real, la BATCH_DETAIL_QUERY de 50 ids tarda ~27 s (25 → 15,2 s ·
# 10 → 6,2 s · 1 → 3,0 s). Con 15 s TODOS los lotes expiraban, el
# `except Exception: continue` del backfill se lo tragaba sin registrar nada, `done`
# no llegaba a incrementarse nunca, y la barra se quedaba clavada en "0/N" mientras el
# backfill no terminaba jamás. 60 s deja margen para una AniList lenta sin aflojarle el
# cinturón al resto del cliente.
BATCH_TIMEOUT_SECONDS = 60.0


class AniListClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = _client

    def authorization_url(self, state: str) -> str:
        # AniList solo soporta Authorization Code Grant (el implicit grant está deshabilitado
        # en su servidor: devuelve unsupported_grant_type). El intercambio de código requiere
        # client_secret, así que AniList no tiene un flujo público sin secreto.
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
        if not self.settings.anilist_client_id:
            raise AniListError("AniList OAuth credentials are not configured")
        # Con secreto local (dev): intercambio directo. Sin secreto (build distribuido):
        # lo hace el broker (Supabase Edge Function), único que conoce el client_secret.
        if self.settings.anilist_client_secret:
            payload = {
                "grant_type": "authorization_code",
                "client_id": self.settings.anilist_client_id,
                "client_secret": self.settings.anilist_client_secret,
                "redirect_uri": self.settings.anilist_redirect_uri,
                "code": code,
            }
            response = await self.client.post(TOKEN_URL, json=payload)
            return response.json()["access_token"]
        if not self.settings.anilist_token_broker_url:
            raise AniListError("AniList OAuth credentials are not configured")
        try:
            # Cliente dedicado SIN reintentos: el code es de un solo uso, así que
            # reintentar tras un timeout lo quema y AniList responde "Cannot decrypt
            # the authorization code". 30 s cubre el arranque en frío de la función.
            async with httpx.AsyncClient(timeout=30.0) as broker_client:
                response = await broker_client.post(
                    self.settings.anilist_token_broker_url,
                    json={"code": code, "redirect_uri": self.settings.anilist_redirect_uri},
                )
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            # El broker adjunta el motivo de AniList (error/hint) sin datos sensibles.
            try:
                body = exc.response.json()
                detail = ", ".join(
                    str(value) for key in ("anilist_error", "anilist_hint")
                    if (value := body.get(key))
                ) or body.get("error", "")
            except ValueError:
                detail = exc.response.text[:200]
            raise AniListError(
                f"AniList rechazó el intercambio vía broker: {detail or exc.response.status_code}",
                status_code=exc.response.status_code,
            ) from exc
        token = response.json().get("access_token")
        if not token:
            raise AniListError("El broker de OAuth no devolvió un token de AniList")
        return token

    async def graphql(
        self,
        token: str,
        query: str,
        variables: dict | None = None,
        timeout: float | None = None,
    ) -> dict:
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        # timeout por petición (httpx lo acepta como kwarg): solo los lotes del backfill
        # necesitan más de los 15 s por defecto. Ver BATCH_TIMEOUT_SECONDS.
        extra = {"timeout": timeout} if timeout is not None else {}
        try:
            response = await self.client.post(
                API_URL,
                headers=headers,
                json={"query": query, "variables": variables or {}},
                **extra,
            )
        except httpx.HTTPStatusError as exc:
            body = exc.response.text[:500]
            raise AniListError(
                f"No se pudo completar la solicitud a AniList ({exc.response.status_code}): {body}",
                status_code=exc.response.status_code,
            ) from exc
        payload = response.json()
        if payload.get("errors"):
            raise AniListError(payload["errors"][0].get("message", "AniList request failed"))
        return payload["data"]

    async def media_list(self, token: str) -> list[MediaItem]:
        viewer = await self.graphql(token, VIEWER_QUERY)
        data = await self.graphql(token, LIST_QUERY, {"userId": viewer["Viewer"]["id"]})
        score_format = data["Viewer"]["mediaListOptions"]["scoreFormat"]
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
                score=convert_score(
                    entry.get("score"),
                    score_format,
                    ScoreFormat.POINT_100,
                ),
                episodes=entry["media"]["episodes"],
                cover_image=entry["media"]["coverImage"]["large"],
                title_romaji=entry["media"]["title"].get("romaji"),
                title_english=entry["media"]["title"].get("english"),
                title_native=entry["media"]["title"].get("native"),
                synonyms=entry["media"].get("synonyms") or [],
                genres=entry["media"].get("genres") or [],
                year=entry["media"].get("seasonYear"),
                season=entry["media"].get("season"),
                format=to_canonical_format("anilist", entry["media"].get("format")).value,
                media_status=entry["media"].get("status"),
                site_url=entry["media"].get("siteUrl"),
                updated_at=entry.get("updatedAt"),
                media_updated_at=entry["media"].get("updatedAt"),
                started_at=_fuzzy_date_to_str(entry.get("startedAt")),
                completed_at=_fuzzy_date_to_str(entry.get("completedAt")),
                id_mal=entry["media"].get("idMal"),
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
                title_romaji=item["title"].get("romaji"),
                title_english=item["title"].get("english"),
                title_native=item["title"].get("native"),
                synonyms=item.get("synonyms") or [],
                format=to_canonical_format("anilist", item.get("format")).value,
                status=item.get("status"),
                episodes=item.get("episodes"),
                average_score=item.get("averageScore"),
                popularity=item.get("popularity") or 0,
                cover_image=item["coverImage"]["large"],
                year=item.get("seasonYear"),
                genres=item.get("genres") or [],
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
                title_romaji=item["title"].get("romaji"),
                title_english=item["title"].get("english"),
                title_native=item["title"].get("native"),
                synonyms=item.get("synonyms") or [],
                format=to_canonical_format("anilist", item.get("format")).value,
                status=item.get("status"),
                chapters=item.get("chapters"),
                volumes=item.get("volumes"),
                average_score=item.get("averageScore"),
                popularity=item.get("popularity") or 0,
                cover_image=item["coverImage"]["large"],
                year=item.get("seasonYear"),
                genres=item.get("genres") or [],
            )
            for item in data["Page"]["media"]
        ]

    async def discover(self, token: str, filters: SearchFilters) -> GlobalSearchResponse:
        is_manga = filters.media_type == "MANGA"
        per_page = max(1, min(filters.per_page, 50))
        has_query = bool(filters.query and filters.query.strip())
        anilist_sort = ["SCORE_DESC"] if filters.sort == "SCORE" else ["POPULARITY_DESC"]
        include_adult = bool(filters.is_adult)
        if is_manga:
            if has_query:
                query = SEARCH_MANGA_PAGINATED_QUERY
                data = await self.graphql(
                    token,
                    _allow_adult(query) if include_adult else query,
                    {
                        "query": filters.query.strip(),
                        "page": filters.page,
                        "perPage": per_page,
                    },
                )
            else:
                applied = {"genre": filters.genre, "format": filters.format, "status": filters.status}
                active = [name for name, value in applied.items() if value]
                variables = {
                    "page": filters.page,
                    "perPage": per_page,
                    "sort": anilist_sort,
                    **{name: applied[name] for name in active},
                }
                data = await self.graphql(
                    token, _build_popular_query("MANGA", _POPULAR_MANGA_FIELDS, active, include_adult), variables
                )
        else:
            if has_query:
                query = SEARCH_PAGINATED_QUERY
                data = await self.graphql(
                    token,
                    _allow_adult(query) if include_adult else query,
                    {
                        "query": filters.query.strip(),
                        "page": filters.page,
                        "perPage": per_page,
                        "formats": ALLOWED_ANIME_FORMATS,
                    },
                )
            else:
                applied = {
                    "genre": filters.genre,
                    "format": filters.format,
                    "year": filters.year,
                    "status": filters.status,
                    "season": filters.season,
                }
                active = [name for name, value in applied.items() if value]
                variables = {
                    "page": filters.page,
                    "perPage": per_page,
                    "sort": anilist_sort,
                    **{name: applied[name] for name in active},
                }
                data = await self.graphql(
                    token, _build_popular_query("ANIME", _POPULAR_ANIME_FIELDS, active, include_adult), variables
                )
        page = data["Page"]
        return GlobalSearchResponse(
            results=[
                SearchResult(
                    id=item["id"],
                    title=item["title"]["userPreferred"],
                    title_romaji=item["title"].get("romaji"),
                    title_english=item["title"].get("english"),
                    title_native=item["title"].get("native"),
                    synonyms=item.get("synonyms") or [],
                    format=to_canonical_format("anilist", item.get("format")).value,
                    status=item.get("status"),
                    episodes=None if is_manga else item.get("episodes"),
                    chapters=item.get("chapters") if is_manga else None,
                    volumes=item.get("volumes") if is_manga else None,
                    average_score=item.get("averageScore"),
                    popularity=item.get("popularity") or 0,
                    cover_image=item["coverImage"]["large"],
                    year=item.get("seasonYear"),
                    genres=item.get("genres") or [],
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
                cover_color=item["coverImage"].get("color"),
                studios=[studio["name"] for studio in (item.get("studios") or {}).get("nodes", [])],
                genres=item.get("genres") or [],
                description=item.get("description"),
                next_episode=(item.get("nextAiringEpisode") or {}).get("episode"),
                next_airing_at=(item.get("nextAiringEpisode") or {}).get("airingAt"),
            )
            for item in data["Page"]["media"]
        ]

    def _build_statistics_response(self, data: dict) -> StatisticsResponse:
        def _groups(items: list, key: str) -> list[StatisticGroup]:
            return [StatisticGroup(label=str(item[key]), count=item["count"]) for item in items]

        def _studio_groups(items: list) -> list[StatisticGroup]:
            return [StatisticGroup(label=item["studio"]["name"], count=item["count"]) for item in items]

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
                studios=_studio_groups(anime["studios"]),
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
                studios=_studio_groups(manga["studios"]),
                countries=_groups(manga["countries"], "country"),
            ),
        )

    async def statistics(self, token: str) -> StatisticsResponse:
        data = await self.graphql(token, STATISTICS_QUERY)
        return self._build_statistics_response(data)

    def _parse_anime_details(
        self, media: dict, score_format: str, entry: dict | None = None
    ) -> MediaDetails:
        next_airing = media.get("nextAiringEpisode") or {}
        return MediaDetails(
            id=media["id"],
            updated_at=media.get("updatedAt"),
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
            score_format=score_format,
            list_entry=self._list_entry(entry, score_format) if entry else None,
            trailer=(
                TrailerInfo(id=media["trailer"]["id"], site=media["trailer"].get("site") or "")
                if media.get("trailer") and media["trailer"].get("id")
                else None
            ),
            characters=AniListClient._parse_characters(media),
            staff=AniListClient._parse_staff(media),
            relations=AniListClient._parse_relations(media),
            recommendations=AniListClient._parse_recommendations(media),
        )

    async def media_details(self, token: str, media_id: int) -> MediaDetails:
        data = await self.graphql(token, DETAIL_QUERY, {"id": media_id})
        media = data["Media"]
        score_format = data["Viewer"]["mediaListOptions"]["scoreFormat"]
        try:
            entry_data = await self.graphql(
                token,
                ENTRY_QUERY,
                {"id": media_id, "userId": data["Viewer"]["id"]},
            )
            entry = entry_data.get("MediaList")
        except AniListError as error:
            if error.status_code != 404:
                raise
            entry = None
        return self._parse_anime_details(media, score_format, entry)

    async def media_details_batch(
        self, token: str, media_ids: list[int]
    ) -> list[MediaDetails]:
        # Sin la MediaList por item: el detalle persistido reconstruye la entrada del
        # usuario desde la biblioteca local al servirse. Aquí solo interesa el detalle.
        if not media_ids:
            return []
        data = await self.graphql(
            token,
            BATCH_DETAIL_QUERY,
            {"ids": list(media_ids)},
            timeout=BATCH_TIMEOUT_SECONDS,
        )
        score_format = data["Viewer"]["mediaListOptions"]["scoreFormat"]
        return [
            self._parse_anime_details(media, score_format)
            for media in data["Page"]["media"]
        ]

    async def edit_entry(
        self, token: str, media_id: int, update: MediaEntryUpdate
    ) -> MediaListEntry:
        values = update.model_dump(exclude_unset=True)
        variables = {"mediaId": media_id}
        viewer = await self.graphql(token, SCORE_FORMAT_QUERY)
        score_format = viewer["Viewer"]["mediaListOptions"]["scoreFormat"]
        graphql_names = {
            "started_at": "startedAt",
            "completed_at": "completedAt",
        }
        for key, value in values.items():
            if key == "status" and value is not None:
                value = from_canonical_status("anilist", value)
            if key == "score":
                converted = convert_score(value, ScoreFormat.POINT_100, score_format) if value else None
                variables["score"] = converted if converted is not None else 0
                continue
            if key in ("started_at", "completed_at") and isinstance(value, dict) and not any(v is not None for v in value.values()):
                value = None
            variables[graphql_names.get(key, key)] = value
        data = await self.graphql(token, EDIT_ENTRY_MUTATION, variables)
        return self._list_entry(data["SaveMediaListEntry"], score_format)

    async def delete_entry(self, token: str, entry_id: int) -> bool:
        data = await self.graphql(token, DELETE_ENTRY_MUTATION, {"id": entry_id})
        return bool(data["DeleteMediaListEntry"]["deleted"])

    async def media_list_manga(self, token: str) -> list[MediaItem]:
        viewer = await self.graphql(token, VIEWER_QUERY)
        data = await self.graphql(
            token, MANGA_LIST_QUERY, {"userId": viewer["Viewer"]["id"]}
        )
        score_format = data["Viewer"]["mediaListOptions"]["scoreFormat"]
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
                score=convert_score(
                    entry.get("score"),
                    score_format,
                    ScoreFormat.POINT_100,
                ),
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
                media_updated_at=entry["media"].get("updatedAt"),
                started_at=_fuzzy_date_to_str(entry.get("startedAt")),
                completed_at=_fuzzy_date_to_str(entry.get("completedAt")),
            )
            for entry in entries
        ]

    def _parse_manga_details(
        self, media: dict, score_format: str, entry: dict | None = None
    ) -> MediaDetails:
        return MediaDetails(
            id=media["id"],
            updated_at=media.get("updatedAt"),
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
            score_format=score_format,
            list_entry=self._list_entry(entry, score_format) if entry else None,
            staff=AniListClient._parse_staff(media),
            relations=AniListClient._parse_relations(media),
            recommendations=AniListClient._parse_recommendations(media),
        )

    async def manga_details(self, token: str, media_id: int) -> MediaDetails:
        data = await self.graphql(token, MANGA_DETAIL_QUERY, {"id": media_id})
        media = data["Media"]
        score_format = data["Viewer"]["mediaListOptions"]["scoreFormat"]
        try:
            entry_data = await self.graphql(
                token,
                MANGA_ENTRY_QUERY,
                {"id": media_id, "userId": data["Viewer"]["id"]},
            )
            entry = entry_data.get("MediaList")
        except AniListError as error:
            if error.status_code != 404:
                raise
            entry = None
        return self._parse_manga_details(media, score_format, entry)

    async def manga_details_batch(
        self, token: str, media_ids: list[int]
    ) -> list[MediaDetails]:
        if not media_ids:
            return []
        data = await self.graphql(
            token,
            MANGA_BATCH_DETAIL_QUERY,
            {"ids": list(media_ids)},
            timeout=BATCH_TIMEOUT_SECONDS,
        )
        score_format = data["Viewer"]["mediaListOptions"]["scoreFormat"]
        return [
            self._parse_manga_details(media, score_format)
            for media in data["Page"]["media"]
        ]

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
    def _parse_relations(media: dict) -> list[RelationEdge]:
        edges = (media.get("relations") or {}).get("edges") or []
        return [
            RelationEdge(
                id=e["node"]["id"],
                title=e["node"]["title"]["userPreferred"],
                format=e["node"].get("format"),
                relation_type=e.get("relationType") or "OTHER",
                cover_image=((e["node"].get("coverImage") or {}).get("large")),
            )
            for e in edges
            if (e.get("node") or {}).get("id")
        ]

    @staticmethod
    def _parse_recommendations(media: dict) -> list[RecommendationItem]:
        nodes = (media.get("recommendations") or {}).get("nodes") or []
        return [
            RecommendationItem(
                id=n["mediaRecommendation"]["id"],
                title=n["mediaRecommendation"]["title"]["userPreferred"],
                format=n["mediaRecommendation"].get("format"),
                cover_image=(n["mediaRecommendation"].get("coverImage") or {}).get("large"),
                rating=n.get("rating"),
            )
            for n in nodes
            if n.get("mediaRecommendation") and n["mediaRecommendation"].get("id")
        ]

    @staticmethod
    def _parse_characters(media: dict) -> list[CharacterEdge]:
        edges = (media.get("characters") or {}).get("edges") or []
        result = []
        for e in edges:
            node = e.get("node") or {}
            va_list = [
                VoiceActorNode(
                    name=CharacterName(full=(va.get("name") or {}).get("full")),
                    image=CharacterImage(medium=(va.get("image") or {}).get("medium")),
                    language="JAPANESE",
                )
                for va in (e.get("voiceActors") or [])
            ]
            result.append(
                CharacterEdge(
                    node=CharacterNode(
                        name=CharacterName(full=(node.get("name") or {}).get("full")),
                        image=CharacterImage(medium=(node.get("image") or {}).get("medium")),
                    ),
                    role=e.get("role"),
                    voice_actors=va_list[:1],  # ponytail: solo el primero; mostrar más si la UI lo pide
                )
            )
        return result

    @staticmethod
    def _parse_staff(media: dict) -> list[StaffEdge]:
        edges = (media.get("staff") or {}).get("edges") or []
        return [
            StaffEdge(
                node=CharacterNode(
                    name=CharacterName(full=((e.get("node") or {}).get("name") or {}).get("full")),
                    image=CharacterImage(medium=((e.get("node") or {}).get("image") or {}).get("medium")),
                ),
                role=e.get("role"),
            )
            for e in edges
            if e.get("node")
        ]

    @staticmethod
    def _list_entry(entry: dict, score_format: str = ScoreFormat.POINT_100) -> MediaListEntry:
        def fuzzy_date(value: dict | None) -> FuzzyDate:
            return FuzzyDate(**(value or {}))

        return MediaListEntry(
            id=entry["id"],
            status=to_canonical_status("anilist", entry["status"]).value,
            score=convert_score(
                entry.get("score"),
                score_format,
                ScoreFormat.POINT_100,
            ) or 0,
            progress=entry.get("progress") or 0,
            repeat=entry.get("repeat") or 0,
            private=bool(entry.get("private")),
            notes=entry.get("notes"),
            started_at=fuzzy_date(entry.get("startedAt")),
            completed_at=fuzzy_date(entry.get("completedAt")),
        )
