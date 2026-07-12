from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = "ok"
    authenticated: bool


class ProviderCapabilitiesResponse(BaseModel):
    library: bool
    search: bool
    details: bool
    mutations: bool
    activity: bool
    statistics: bool
    seasons: bool
    manga: bool
    preferences: bool = False
    preferences_editable: bool = False


class ProviderInfo(BaseModel):
    name: str
    display_name: str
    authenticated: bool
    capabilities: ProviderCapabilitiesResponse


class AccountInfo(BaseModel):
    id: int
    provider: str
    alias: str
    authenticated: bool
    is_primary: bool
    last_synced_at: str | None = None
    # False = la fila existe pero nunca hubo login (la crean rutas de lectura).
    has_credential_ref: bool = False


class AccountUpdate(BaseModel):
    is_primary: bool | None = None


class LibraryFolder(BaseModel):
    id: int
    path: str
    recursive: bool


class LibraryFolderCreate(BaseModel):
    path: str
    recursive: bool = True


class ScanSummary(BaseModel):
    total: int
    matched: int
    unmatched: int


class ScanSettings(BaseModel):
    scan_on_startup: bool
    watch_folders: bool = False


class PendingLocalItem(BaseModel):
    media_id: int
    external_id: int
    title: str
    cover_image: str | None = None
    progress: int
    next_episode: int
    next_path: str
    available_count: int


class ConflictInfo(BaseModel):
    id: int
    media_id: int
    account_id: int
    provider: str
    alias: str
    field: str
    local_value: str | None
    remote_value: str | None
    detected_at: str
    status: str
    resolution_value: str | None
    title: str


class ConflictResolution(BaseModel):
    resolution: Literal["local", "remote", "manual"]
    value: str | None = None


class AniListTitle(BaseModel):
    user_preferred: str = Field(alias="userPreferred")

    model_config = {"populate_by_name": True}


class MediaItem(BaseModel):
    id: int
    title: str
    status: str
    progress: int
    score: float | None = None
    episodes: int | None = None
    chapters: int | None = None
    volumes: int | None = None
    cover_image: str | None = None
    title_romaji: str | None = None
    title_english: str | None = None
    title_native: str | None = None
    synonyms: list[str] = Field(default_factory=list)
    genres: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    year: int | None = None
    season: str | None = None  # temporada de emisión (WINTER/SPRING/SUMMER/FALL)
    format: str | None = None
    media_type: str = "ANIME"
    media_status: str | None = None  # estado de emisión (RELEASING/FINISHED/…)
    site_url: str | None = None
    updated_at: int | None = None  # cuándo cambió la ENTRADA del usuario (progreso/score)
    media_updated_at: int | None = None  # cuándo cambió la METADATA de la obra en el proveedor
    canonical_id: int | None = None
    provider: str | None = None
    account_alias: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    id_mal: int | None = None  # referencia cruzada de AniList al id de MyAnimeList


class ProgressUpdate(BaseModel):
    media_id: int
    progress: int = Field(ge=0)
    status: str | None = None


class PlaybackCandidate(BaseModel):
    source: str
    raw_title: str
    anime_title: str | None = None
    season: int | None = None
    episode: int | None = None
    episode_type: str | None = None
    confidence: float = 0.0
    process_name: str | None = None
    position_seconds: float | None = None
    duration_seconds: float | None = None
    paused: bool | None = None
    finished: bool | None = None
    page_url: str | None = None
    site_identifier: str | None = None
    content_kind: Literal["episode", "trailer", "preview", "opening", "ending", "unknown"] = "unknown"
    site_adapter: str | None = None
    search_hints: list[str] = Field(default_factory=list)
    next_episode_url: str | None = None


class ExtensionPairRequest(BaseModel):
    code: str = Field(min_length=6, max_length=32)
    label: str = Field(default="Browser", min_length=1, max_length=80)


class ExtensionTokenResponse(BaseModel):
    token: str
    expires_at: int


class ExtensionPairingResponse(BaseModel):
    code: str
    expires_at: int
    api_url: str


class ExtensionClientInfo(BaseModel):
    id: int
    label: str
    created_at: int
    expires_at: int
    last_seen_at: int | None = None
    revoked_at: int | None = None


class ExtensionRotateRequest(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=80)


class ExtensionPlaybackEvent(BaseModel):
    raw_title: str = Field(min_length=1, max_length=500)
    page_url: str = Field(min_length=1, max_length=2000)
    position_seconds: float | None = Field(default=None, ge=0)
    duration_seconds: float | None = Field(default=None, ge=0)
    paused: bool = False
    anime_title: str | None = Field(default=None, max_length=500)
    season: int | None = Field(default=None, ge=0)
    episode: int | None = Field(default=None, ge=0)
    content_kind: Literal["episode", "trailer", "preview", "opening", "ending", "unknown"] = "unknown"
    site_adapter: str = Field(default="generic", min_length=1, max_length=80)
    site_identifier: str | None = Field(default=None, max_length=500)
    search_hints: list[str] = Field(default_factory=list)
    next_episode_url: str | None = Field(default=None, max_length=2000)


class ActivityItem(BaseModel):
    id: int
    status: str
    progress: str | None = None
    created_at: int
    media_id: int
    title: str
    cover_image: str | None = None
    media_type: str = "ANIME"


class SeasonMedia(BaseModel):
    id: int
    title: str
    format: str | None = None
    status: str | None = None
    episodes: int | None = None
    average_score: int | None = None
    popularity: int = 0
    start_date: "FuzzyDate | None" = None
    cover_image: str | None = None
    cover_color: str | None = None
    studios: list[str] = Field(default_factory=list)
    genres: list[str] = Field(default_factory=list)
    description: str | None = None
    next_episode: int | None = None
    next_airing_at: int | None = None


class StatisticGroup(BaseModel):
    label: str
    count: int


class MediaStatistics(BaseModel):
    count: int
    episodes_watched: int
    minutes_watched: int
    mean_score: float
    genres: list[StatisticGroup]
    statuses: list[StatisticGroup]
    formats: list[StatisticGroup] = Field(default_factory=list)
    release_years: list[StatisticGroup] = Field(default_factory=list)
    studios: list[StatisticGroup] = Field(default_factory=list)
    countries: list[StatisticGroup] = Field(default_factory=list)


# ponytail: alias for backward compat with cached_value calls migrating from AnimeStatistics
AnimeStatistics = MediaStatistics


class StatisticsResponse(BaseModel):
    anime: MediaStatistics
    manga: MediaStatistics


class FuzzyDate(BaseModel):
    year: int | None = None
    month: int | None = None
    day: int | None = None


class MediaListEntry(BaseModel):
    id: int
    status: str
    score: float
    progress: int
    repeat: int
    private: bool
    notes: str | None = None
    started_at: FuzzyDate
    completed_at: FuzzyDate


class CharacterName(BaseModel):
    full: str | None = None


class CharacterImage(BaseModel):
    medium: str | None = None


class CharacterNode(BaseModel):
    name: CharacterName
    image: CharacterImage | None = None


class VoiceActorNode(BaseModel):
    name: CharacterName
    image: CharacterImage | None = None
    language: str | None = None


class CharacterEdge(BaseModel):
    node: CharacterNode
    role: str | None = None
    voice_actors: list[VoiceActorNode] = Field(default_factory=list)


class StaffEdge(BaseModel):
    node: CharacterNode
    role: str | None = None


class RelationEdge(BaseModel):
    id: int
    title: str
    format: str | None = None
    relation_type: str
    cover_image: str | None = None


class RecommendationItem(BaseModel):
    id: int
    title: str
    format: str | None = None
    cover_image: str | None = None
    rating: int | None = None


class TrailerInfo(BaseModel):
    id: str
    site: str


class MediaDetails(BaseModel):
    id: int
    # updatedAt del proveedor: si el valor fresco de la lista supera al guardado, la
    # metadata cambió y hay que re-bajar el detalle (refresco por cambio, no por TTL).
    updated_at: int | None = None
    title: str
    title_romaji: str | None = None
    title_english: str | None = None
    title_native: str | None = None
    synonyms: list[str]
    description: str | None = None
    site_url: str
    banner_image: str | None = None
    cover_image: str | None = None
    color: str | None = None
    format: str | None = None
    media_type: str = "ANIME"
    status: str | None = None
    source: str | None = None
    season: str | None = None
    season_year: int | None = None
    episodes: int | None = None
    chapters: int | None = None
    volumes: int | None = None
    duration: int | None = None
    genres: list[str]
    studios: list[str]
    country: str | None = None
    average_score: int | None = None
    next_episode: int | None = None
    next_airing_at: int | None = None
    score_format: str
    canonical_id: int | None = None
    list_entry: MediaListEntry | None = None
    characters: list[CharacterEdge] = Field(default_factory=list)
    staff: list[StaffEdge] = Field(default_factory=list)
    relations: list[RelationEdge] = Field(default_factory=list)
    recommendations: list[RecommendationItem] = Field(default_factory=list)
    trailer: TrailerInfo | None = None


class MediaEntryUpdate(BaseModel):
    status: str | None = None
    progress: int | None = Field(default=None, ge=0)
    score: float | None = Field(default=None, ge=0, le=100)
    repeat: int | None = Field(default=None, ge=0)
    private: bool | None = None
    notes: str | None = None
    started_at: FuzzyDate | None = None
    completed_at: FuzzyDate | None = None


class AccountUpdateResult(BaseModel):
    provider: str
    alias: str
    success: bool
    error: str | None = None


class BulkUpdateResult(BaseModel):
    results: list[AccountUpdateResult]
    local_updated: bool


class MediaTagUpdate(BaseModel):
    media_id: int
    tag: str


class PlaybackMatchRequest(BaseModel):
    source: str
    raw_title: str
    anime_title: str | None = None
    season: int | None = None
    episode: int | None = None
    episode_type: str | None = None
    confidence: float = 0.0
    position_seconds: float | None = None
    duration_seconds: float | None = None
    paused: bool | None = None
    finished: bool | None = None
    page_url: str | None = None
    site_identifier: str | None = None
    content_kind: Literal["episode", "trailer", "preview", "opening", "ending", "unknown"] = "unknown"
    site_adapter: str | None = None
    search_hints: list[str] = Field(default_factory=list)


class PlaybackMatchResponse(BaseModel):
    event_id: int
    event_status: str = "pending"
    candidate: PlaybackCandidate
    match: MediaItem | None = None
    match_score: float
    # Alternative library entries the user can pick when the single match is weak,
    # ambiguous or wrong — so detection never silently assumes an irrelevant series.
    suggestions: list[MediaItem] = Field(default_factory=list)


class PlaybackConfirmRequest(BaseModel):
    event_id: int | None = None
    media_id: int
    progress: int
    site_identifier: str | None = None
    site_adapter: str | None = None


class PlaybackUndoResponse(BaseModel):
    undone: bool
    media_id: int | None = None
    restored_progress: int | None = None


class PlaybackRetryResponse(BaseModel):
    retried: bool
    media_id: int
    progress: int


class PlaybackIgnoreRequest(BaseModel):
    event_id: int


class PlaybackEvent(BaseModel):
    id: int
    detected_at: str
    source: str
    raw_title: str
    anime_title: str | None = None
    episode: int | None = None
    status: str
    media_id: int | None = None
    progress_before: int | None = None
    progress_after: int | None = None
    provider_id: str | None = None
    account_id: int | None = None
    canonical_media_id: int | None = None
    error_message: str | None = None


class DetectorUpdate(BaseModel):
    enabled: bool


ProgressPolicy = Literal["always", "start", "middle", "end", "seconds", "never"]


class PlaybackPreferences(BaseModel):
    auto_confirm: bool = False
    confidence_threshold: float = Field(0.85, ge=0.0, le=1.0)
    progress_policy: ProgressPolicy = "end"
    progress_seconds: int = Field(90, ge=0)


class CacheStatusItem(BaseModel):
    key: str
    expires_at: int
    updated_at: int
    size: int
    stale: bool
    provider_id: str | None = None
    account_alias: str | None = None
    resource: str | None = None
    refresh_reason: str | None = None


class CacheStatusResponse(BaseModel):
    entries: list[CacheStatusItem]
    last_updated: int | None = None


class SyncStatusItem(BaseModel):
    updated_at: int | None = None
    stale: bool = False


class SyncStatusResponse(BaseModel):
    library: SyncStatusItem
    activity: SyncStatusItem
    statistics: SyncStatusItem
    season: SyncStatusItem


TitleLanguage = Literal["ROMAJI", "ENGLISH", "NATIVE"]
ScoreFormat = Literal["POINT_100", "POINT_10_DECIMAL", "POINT_10", "POINT_5", "POINT_3"]


class UserPreferences(BaseModel):
    username: str
    avatar: str | None = None
    title_language: TitleLanguage
    score_format: ScoreFormat
    display_adult_content: bool


class UserPreferencesUpdate(BaseModel):
    title_language: TitleLanguage
    score_format: ScoreFormat
    display_adult_content: bool


class WontWatchItem(BaseModel):
    external_id: str
    title: str | None = None
    cover_image: str | None = None


class WontWatchRequest(BaseModel):
    media_id: int
    title: str | None = None
    cover_image: str | None = None


class WontWatchState(BaseModel):
    items: list[WontWatchItem]
    show_marked: bool


class DiscoverSettingsUpdate(BaseModel):
    show_marked: bool


class MatchCorrectionRequest(BaseModel):
    raw_title: str
    media_id: int
    anime_title: str | None = None
    site_identifier: str | None = None
    site_adapter: str | None = None


class LibrarySearchResponse(BaseModel):
    results: list[MediaItem]


class SearchResult(BaseModel):
    id: int
    title: str
    title_romaji: str | None = None
    title_english: str | None = None
    title_native: str | None = None
    synonyms: list[str] = Field(default_factory=list)
    format: str | None = None
    status: str | None = None
    episodes: int | None = None
    chapters: int | None = None
    volumes: int | None = None
    average_score: int | None = None
    popularity: int = 0
    cover_image: str | None = None
    year: int | None = None
    genres: list[str] = Field(default_factory=list)


class SearchFilters(BaseModel):
    query: str = ""
    page: int = 1
    per_page: int = 20
    genre: str | None = None
    format: str | None = None
    year: int | None = None
    season: str | None = None
    status: str | None = None
    is_adult: bool = False
    media_type: Literal["ANIME", "MANGA"] = "ANIME"
    sort: Literal["POPULARITY", "SCORE"] = "POPULARITY"


class GlobalSearchResponse(BaseModel):
    results: list[SearchResult]
    has_next_page: bool = False


class TorrentSource(BaseModel):
    id: int
    name: str
    url: str
    enabled: bool
    kind: str = "release"


class TorrentSourceInput(BaseModel):
    name: str
    url: str
    enabled: bool = True
    kind: str = "release"


class TorrentCondition(BaseModel):
    element: str
    operator: str
    value: str


class TorrentFilter(BaseModel):
    id: int
    name: str
    action: str
    match: str = "all"
    scope: str = "all"
    enabled: bool = True
    conditions: list[TorrentCondition] = Field(default_factory=list)
    anime_ids: list[int] = Field(default_factory=list)


class TorrentFilterInput(BaseModel):
    name: str
    action: str
    match: str = "all"
    scope: str = "all"
    enabled: bool = True
    conditions: list[TorrentCondition] = Field(default_factory=list)
    anime_ids: list[int] = Field(default_factory=list)


class TorrentSettings(BaseModel):
    auto_check: bool = True
    interval_min: int = 60
    download_mode: str = "magnet"   # magnet | folder
    watch_folder: str = ""
    preferred_resolution: str = "1080p"
    on_new: str = "notify"          # notify | download
    client_path: str = ""
    folder_per_series: bool = False
    append_episode: bool = False
    use_anime_folder: bool = False  # descargar junto a los episodios locales existentes
    filters_enabled: bool = True
    global_discard_not_in_list: bool = True
    global_discard_seen: bool = True
    global_prefer_resolution: bool = True


class TorrentItem(BaseModel):
    signature: str
    raw_title: str
    link: str
    media_id: int | None = None
    media_title: str | None = None
    episode: int | None = None
    resolution: str | None = None
    group: str | None = None
    seeders: int | None = None
    size: str | None = None
    description: str | None = None
    filename: str | None = None
    torrent_date: str | None = None
    confidence: float
    is_new: bool
    cover_image: str | None = None


class TorrentActionRequest(BaseModel):
    signature: str
    mode: str | None = None  # None = según ajustes; "magnet" | "torrent" fuerzan el modo


class TorrentDownloadResponse(BaseModel):
    action: str          # "magnet" | "saved"
    link: str | None = None
    path: str | None = None
    client_path: str | None = None


class LocalAssociateRequest(BaseModel):
    title: str                          # título del grupo (parsed o canónico)
    from_media_id: int | None = None    # media canónico actual si el grupo ya estaba matcheado
    external_id: int | None = None      # id en el catálogo del proveedor; None = quitar asociación
    status: str | None = None           # estado de lista al agregar si aún no está en la biblioteca
    media: SearchResult | None = None   # resultado elegido, para registrar la obra sin esperar un sync


class LocalSeries(BaseModel):
    media_id: int | None = None
    title: str
    title_romaji: str | None = None
    title_english: str | None = None
    title_native: str | None = None
    episode_count: int
    matched: bool
    external_id: int | None = None
    provider: str | None = None
    account_alias: str | None = None
    cover_image: str | None = None
    episodes: int | None = None
    progress: int | None = None
    next_episode: int | None = None
    next_path: str | None = None
