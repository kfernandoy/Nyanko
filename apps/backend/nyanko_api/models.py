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


class ProviderInfo(BaseModel):
    name: str
    display_name: str
    authenticated: bool
    capabilities: ProviderCapabilitiesResponse


SyncDirection = Literal["import", "bidirectional", "export"]


class AccountInfo(BaseModel):
    id: int
    provider: str
    alias: str
    authenticated: bool
    sync_direction: SyncDirection
    is_primary: bool
    last_synced_at: str | None = None


class AccountUpdate(BaseModel):
    sync_direction: SyncDirection | None = None
    is_primary: bool | None = None


class AssociationCandidateInfo(BaseModel):
    id: int
    source_identity_id: int
    source_provider: str
    source_external_id: str
    source_title: str
    candidate_media_id: int
    candidate_title: str
    confidence: float
    status: str


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


class LinkedIdentityInfo(BaseModel):
    identity_id: int
    media_id: int
    provider: str
    external_id: str
    title: str
    confidence: float
    identity_count: int


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
    format: str | None = None
    media_type: str = "ANIME"
    site_url: str | None = None
    updated_at: int | None = None
    canonical_id: int | None = None
    provider: str | None = None
    started_at: str | None = None
    completed_at: str | None = None


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


class ActivityItem(BaseModel):
    id: int
    status: str
    progress: str | None = None
    created_at: int
    media_id: int
    title: str
    cover_image: str | None = None


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
    studios: list[str] = Field(default_factory=list)
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


class PlaybackConfirmRequest(BaseModel):
    event_id: int | None = None
    media_id: int
    progress: int


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
    format: str | None = None
    status: str | None = None
    episodes: int | None = None
    chapters: int | None = None
    volumes: int | None = None
    average_score: int | None = None
    popularity: int = 0
    cover_image: str | None = None


class SearchFilters(BaseModel):
    query: str = ""
    page: int = 1
    per_page: int = 20
    genre: str | None = None
    format: str | None = None
    year: int | None = None
    status: str | None = None
    is_adult: bool = False
    media_type: Literal["ANIME", "MANGA"] = "ANIME"
    sort: Literal["POPULARITY", "SCORE"] = "POPULARITY"


class GlobalSearchResponse(BaseModel):
    results: list[SearchResult]
    has_next_page: bool = False
