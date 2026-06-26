export type CacheStatus = "hit" | "stale" | "miss";

export interface Health {
  status: string;
  authenticated: boolean;
}

export interface MediaItem {
  id: number;
  title: string;
  status: string;
  progress: number;
  score?: number | null;
  episodes: number | null;
  chapters?: number | null;
  volumes?: number | null;
  cover_image: string | null;
  title_romaji?: string | null;
  title_english?: string | null;
  title_native?: string | null;
  synonyms?: string[];
  genres?: string[];
  tags?: string[];
  year?: number | null;
  format?: string | null;
  site_url?: string | null;
  updated_at?: number | null;
  canonical_id?: number | null;
  provider?: string | null;
}

export interface PlaybackCandidate {
  source: string;
  raw_title: string;
  anime_title: string | null;
  season: number | null;
  episode: number | null;
  episode_type: string | null;
  confidence: number;
  process_name: string | null;
  position_seconds?: number | null;
  duration_seconds?: number | null;
  paused?: boolean | null;
  finished?: boolean | null;
  page_url?: string | null;
  site_identifier?: string | null;
  content_kind?: "episode" | "trailer" | "preview" | "opening" | "ending" | "unknown";
  site_adapter?: string | null;
  search_hints?: string[];
}

export interface ActivityItem {
  id: number;
  status: string;
  progress: string | null;
  created_at: number;
  media_id: number;
  title: string;
  cover_image: string | null;
}

export interface SeasonMedia {
  id: number;
  title: string;
  format: string | null;
  status: string | null;
  episodes: number | null;
  average_score: number | null;
  popularity: number;
  start_date: FuzzyDate | null;
  cover_image: string | null;
  studios: string[];
  next_episode: number | null;
  next_airing_at: number | null;
}

export interface StatisticGroup {
  label: string;
  count: number;
}

export interface MediaStatistics {
  count: number;
  episodes_watched: number;
  minutes_watched: number;
  mean_score: number;
  genres: StatisticGroup[];
  statuses: StatisticGroup[];
  formats: StatisticGroup[];
  release_years: StatisticGroup[];
  studios: StatisticGroup[];
  countries: StatisticGroup[];
}

export interface StatisticsResponse {
  anime: MediaStatistics;
  manga: MediaStatistics;
}

// ponytail: alias de compatibilidad — eliminar cuando no queden usos
export type AnimeStatistics = MediaStatistics;

export interface FuzzyDate {
  year: number | null;
  month: number | null;
  day: number | null;
}

export interface MediaListEntry {
  id: number;
  status: string;
  score: number;
  progress: number;
  repeat: number;
  private: boolean;
  notes: string | null;
  started_at: FuzzyDate;
  completed_at: FuzzyDate;
}

export interface CharacterEdge {
  node: {
    name: { full: string | null } | null;
    image: { medium: string | null } | null;
  };
  role: string | null;
  voice_actors: Array<{
    name: { full: string | null } | null;
    image: { medium: string | null } | null;
  }>;
}

export interface StaffEdge {
  node: {
    name: { full: string | null } | null;
    image: { medium: string | null } | null;
  };
  role: string | null;
}

export interface RelationEdge {
  id: number;
  title: string;
  format: string | null;
  relation_type: string;
  cover_image?: string | null;
}

export interface RecommendationItem {
  id: number;
  title: string;
  format: string | null;
  cover_image: string | null;
  rating: number | null;
}

export interface TrailerInfo {
  id: string;
  site: string;
}

export interface MediaDetails {
  id: number;
  title: string;
  title_romaji: string | null;
  title_english: string | null;
  title_native: string | null;
  synonyms: string[];
  description: string | null;
  site_url: string;
  banner_image: string | null;
  cover_image: string | null;
  color: string | null;
  format: string | null;
  media_type?: string | null;
  status: string | null;
  source: string | null;
  season: string | null;
  season_year: number | null;
  episodes: number | null;
  chapters?: number | null;
  volumes?: number | null;
  duration: number | null;
  genres: string[];
  studios: string[];
  country: string | null;
  average_score: number | null;
  next_episode: number | null;
  next_airing_at: number | null;
  score_format: string;
  list_entry: MediaListEntry | null;
  characters?: CharacterEdge[];
  staff?: StaffEdge[];
  relations?: RelationEdge[];
  recommendations?: RecommendationItem[];
  trailer?: TrailerInfo | null;
}

export interface MediaEntryUpdate {
  status?: string | null;
  progress?: number | null;
  score?: number | null;
  repeat?: number | null;
  private?: boolean | null;
  notes?: string | null;
  started_at?: FuzzyDate | null;
  completed_at?: FuzzyDate | null;
}

export interface AccountUpdateResult {
  provider: string;
  alias: string;
  success: boolean;
  error?: string | null;
}

export interface BulkUpdateResult {
  results: AccountUpdateResult[];
  local_updated: boolean;
}

export interface PlaybackMatchResponse {
  event_id: number;
  event_status: "pending" | "confirmed" | "ignored";
  candidate: PlaybackCandidate;
  match: MediaItem | null;
  match_score: number;
}

export interface PlaybackEvent {
  id: number;
  detected_at: string;
  source: string;
  raw_title: string;
  anime_title: string | null;
  episode: number | null;
  status: "pending" | "confirmed" | "ignored" | "undone" | "failed";
  media_id: number | null;
  progress_before: number | null;
  progress_after: number | null;
  error_message: string | null;
}

export interface DetectorInfo {
  name: string;
  available: boolean;
  priority: number;
  enabled: boolean;
}

export type ProgressPolicy = "always" | "start" | "middle" | "end" | "seconds" | "never";

export interface PlaybackPreferences {
  auto_confirm: boolean;
  confidence_threshold: number;
  progress_policy: ProgressPolicy;
  progress_seconds: number;
}

export interface CacheStatusItem {
  key: string;
  expires_at: number;
  updated_at: number;
  size: number;
  stale: boolean;
  provider_id: string | null;
  account_alias: string | null;
  resource: string | null;
  refresh_reason: string | null;
}

export interface AccountInfo {
  id: number;
  provider: string;
  alias: string;
  authenticated: boolean;
  sync_direction: "import" | "bidirectional" | "export";
  is_primary: boolean;
  last_synced_at: string | null;
}

export interface AssociationCandidateInfo {
  id: number;
  source_identity_id: number;
  source_provider: string;
  source_external_id: string;
  source_title: string;
  candidate_media_id: number;
  candidate_title: string;
  confidence: number;
  status: string;
}

export interface LinkedIdentityInfo {
  identity_id: number;
  media_id: number;
  provider: string;
  external_id: string;
  title: string;
  confidence: number;
  identity_count: number;
}

export interface ConflictInfo {
  id: number;
  media_id: number;
  account_id: number;
  provider: string;
  alias: string;
  field: string;
  local_value: string | null;
  remote_value: string | null;
  detected_at: string;
  status: string;
  resolution_value: string | null;
  title: string;
}

export interface ConflictResolution {
  resolution: "local" | "remote" | "manual";
  value?: string | null;
}

export interface ExtensionClientInfo {
  id: number;
  label: string;
  created_at: number;
  expires_at: number;
  last_seen_at: number | null;
  revoked_at: number | null;
}

export interface CacheStatusResponse {
  entries: CacheStatusItem[];
  last_updated: number | null;
}

export interface SyncStatusItem {
  updated_at: number | null;
  stale: boolean;
}

export interface SyncStatusResponse {
  library: SyncStatusItem;
  activity: SyncStatusItem;
  statistics: SyncStatusItem;
  season: SyncStatusItem;
}

export interface UserPreferences {
  username: string;
  avatar: string | null;
  title_language: "ROMAJI" | "ENGLISH" | "NATIVE";
  score_format: "POINT_100" | "POINT_10_DECIMAL" | "POINT_10" | "POINT_5" | "POINT_3";
  display_adult_content: boolean;
}

export interface UserPreferencesUpdate {
  title_language: UserPreferences["title_language"];
  score_format: UserPreferences["score_format"];
  display_adult_content: boolean;
}

export interface LibrarySearchResponse {
  results: MediaItem[];
}

export interface SearchResult {
  id: number;
  title: string;
  format: string | null;
  status: string | null;
  episodes: number | null;
  chapters?: number | null;
  volumes?: number | null;
  average_score: number | null;
  popularity: number;
  cover_image: string | null;
}

export interface GlobalSearchResponse {
  results: SearchResult[];
  has_next_page: boolean;
}

export interface SearchFilters {
  query: string;
  page: number;
  per_page: number;
  genre: string | null;
  format: string | null;
  year: number | null;
  status: string | null;
  is_adult: boolean;
  media_type: "ANIME" | "MANGA";
  sort: "POPULARITY" | "SCORE";
}

export interface ProviderCapabilities {
  library: boolean;
  search: boolean;
  details: boolean;
  mutations: boolean;
  activity: boolean;
  statistics: boolean;
  seasons: boolean;
  manga: boolean;
}

export interface ProviderInfo {
  name: string;
  display_name: string;
  authenticated: boolean;
  capabilities: ProviderCapabilities;
}
