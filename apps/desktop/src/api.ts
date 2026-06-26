import { BaseDirectory, readTextFile } from "@tauri-apps/plugin-fs";

import type {
  AccountInfo,
  AssociationCandidateInfo,
  BulkUpdateResult,
  ConflictInfo,
  ConflictResolution,
  ActivityItem,
  MediaStatistics,
  StatisticsResponse,
  CacheStatusResponse,
  CacheStatus,
  DetectorInfo,
  ExtensionClientInfo,
  GlobalSearchResponse,
  Health,
  LibrarySearchResponse,
  LinkedIdentityInfo,
  MediaDetails,
  MediaEntryUpdate,
  MediaListEntry,
  MediaItem,
  PlaybackCandidate,
  PlaybackEvent,
  PlaybackMatchResponse,
  PlaybackPreferences,
  ProviderInfo,
  SearchFilters,
  SeasonMedia,
  SyncStatusResponse,
  UserPreferences,
  UserPreferencesUpdate,
} from "./types";

const DEFAULT_API_URL = "http://127.0.0.1:8765";
const INSTANCE_TIMEOUT_MS = 3_000;
const REQUEST_TIMEOUT_MS = 15_000;

let cachedApiUrl: string | null = null;

export interface ActiveAccount {
  provider: string;
  alias: string;
}

let activeAccount: ActiveAccount = { provider: "anilist", alias: "default" };

export function setActiveAccount(provider: string, alias: string): void {
  activeAccount = { provider, alias };
}

function withAccount(path: string, account: ActiveAccount = activeAccount): string {
  const separator = path.includes("?") ? "&" : "?";
  return `${path}${separator}provider=${encodeURIComponent(account.provider)}&account=${encodeURIComponent(account.alias)}`;
}

async function readAppDataFile(name: string): Promise<string | null> {
  if (!("__TAURI_INTERNALS__" in window)) return null;
  try {
    return (await readTextFile(`nyanko/${name}`, { baseDir: BaseDirectory.AppData })).trim();
  } catch {
    return null;
  }
}

async function resolveApiUrl(): Promise<string> {
  const envUrl = import.meta.env.VITE_API_URL;
  if (envUrl) return envUrl as string;
  const port = await readAppDataFile("port");
  if (port) return `http://127.0.0.1:${port}`;
  return DEFAULT_API_URL;
}

async function getApiUrl(): Promise<string> {
  if (cachedApiUrl) return cachedApiUrl;
  cachedApiUrl = await resolveApiUrl();
  return cachedApiUrl;
}

export function clearApiUrlCache(): void {
  cachedApiUrl = null;
}

async function fetchWithTimeout(
  input: RequestInfo | URL,
  options: RequestInit = {},
  timeoutMs = REQUEST_TIMEOUT_MS,
): Promise<Response> {
  const controller = new AbortController();
  const sourceSignal = options.signal;
  const abortFromSource = () => controller.abort(sourceSignal?.reason);
  if (sourceSignal?.aborted) abortFromSource();
  else sourceSignal?.addEventListener("abort", abortFromSource, { once: true });
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(input, { ...options, signal: controller.signal });
  } catch (reason) {
    if (controller.signal.aborted && !sourceSignal?.aborted) {
      throw new Error("El servicio local no respondió a tiempo");
    }
    throw reason;
  } finally {
    window.clearTimeout(timer);
    sourceSignal?.removeEventListener("abort", abortFromSource);
  }
}

async function verifyInstance(apiUrl: string, expectedToken?: string | null): Promise<boolean> {
  expectedToken ??= await readAppDataFile("instance_token");
  if (!expectedToken) return true;
  try {
    const response = await fetchWithTimeout(
      `${apiUrl}/api/instance`,
      {},
      INSTANCE_TIMEOUT_MS,
    );
    if (!response.ok) return false;
    const payload = (await response.json()) as { token?: string };
    return payload.token === expectedToken;
  } catch {
    return false;
  }
}

export interface ApiResponse<T> {
  data: T;
  cacheStatus: CacheStatus | null;
}

async function rawRequest(path: string, options?: RequestInit): Promise<Response> {
  const apiUrl = await getApiUrl();
  const expectedToken = await readAppDataFile("instance_token");
  if (expectedToken && !(await verifyInstance(apiUrl, expectedToken))) {
    clearApiUrlCache();
    throw new Error("El servicio local no pertenece a esta instancia de Nyanko");
  }
  let instanceToken = expectedToken;
  if (!instanceToken) {
    try {
      const instanceResponse = await fetchWithTimeout(
        `${apiUrl}/api/instance`,
        {},
        INSTANCE_TIMEOUT_MS,
      );
      if (instanceResponse.ok) {
        const payload = (await instanceResponse.json()) as { token?: string };
        instanceToken = payload.token ?? null;
      }
    } catch {
      // The real request below will report the connection failure consistently.
    }
  }
  const response = await fetchWithTimeout(`${apiUrl}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(instanceToken ? { "X-Nyanko-Instance": instanceToken } : {}),
      ...options?.headers,
    },
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new Error(payload?.detail ?? `HTTP ${response.status}`);
  }
  return response;
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await rawRequest(path, options);
  return response.status === 204 ? (undefined as T) : response.json();
}

async function requestWithCache<T>(path: string, options?: RequestInit): Promise<ApiResponse<T>> {
  const response = await rawRequest(path, options);
  const cacheStatus = response.headers.get("X-Cache-Status") as CacheStatus | null;
  const data = response.status === 204 ? (undefined as T) : await response.json();
  return { data, cacheStatus };
}

const inFlightRequests = new Map<string, Promise<unknown>>();

function deduplicated<T>(key: string, loader: () => Promise<T>): Promise<T> {
  const existing = inFlightRequests.get(key) as Promise<T> | undefined;
  if (existing) return existing;
  const pending = loader().finally(() => inFlightRequests.delete(key));
  inFlightRequests.set(key, pending);
  return pending;
}

function cachedGet<T>(path: string): Promise<ApiResponse<T>> {
  return deduplicated(path, () => requestWithCache<T>(path));
}

export const api = {
  health: () => request<Health>(withAccount("/api/health")),
  authUrl: (provider = "anilist", alias = "default") =>
    request<{ url: string }>(withAccount(
      provider === "mal" ? "/api/auth/mal/url" : "/api/auth/url",
      { provider, alias },
    )),
  accounts: () => request<AccountInfo[]>("/api/accounts"),
  providers: () => request<ProviderInfo[]>("/api/providers"),
  updateAccount: (
    accountId: number,
    update: Partial<Pick<AccountInfo, "sync_direction" | "is_primary">>,
  ) =>
    request<AccountInfo>(`/api/accounts/${accountId}`, {
      method: "PUT",
      body: JSON.stringify(update),
    }),
  startExtensionPairing: () =>
    request<{ code: string; expires_at: number; api_url: string }>("/api/extension/pairing", { method: "POST" }),
  extensionClients: () =>
    request<ExtensionClientInfo[]>("/api/extension/clients"),
  revokeExtensionClient: (clientId: number) =>
    request<void>(`/api/extension/clients/${clientId}`, { method: "DELETE" }),
  associationCandidates: () =>
    request<AssociationCandidateInfo[]>("/api/associations"),
  resolveAssociation: (candidateId: number) =>
    request<{ media_id: number }>(`/api/associations/${candidateId}/resolve`, { method: "POST" }),
  dismissAssociation: (candidateId: number) =>
    request<void>(`/api/associations/${candidateId}/dismiss`, { method: "POST" }),
  linkedIdentities: () =>
    request<LinkedIdentityInfo[]>("/api/associations/identities"),
  conflicts: (status = "pending") =>
    request<ConflictInfo[]>(`/api/conflicts?status=${encodeURIComponent(status)}`),
  resolveConflict: (conflictId: number, resolution: ConflictResolution) =>
    request<ConflictInfo>(`/api/conflicts/${conflictId}/resolve`, { method: "POST", body: JSON.stringify(resolution) }),
  dismissConflict: (conflictId: number) =>
    request<ConflictInfo>(`/api/conflicts/${conflictId}/dismiss`, { method: "POST" }),
  separateIdentity: (identityId: number) =>
    request<{ media_id: number }>(`/api/associations/identities/${identityId}/separate`, { method: "POST" }),
  logout: () => request<void>(withAccount("/api/auth/logout"), { method: "POST" }),
  logoutAccount: (provider: string, alias: string) =>
    request<void>(withAccount("/api/auth/logout", { provider, alias }), { method: "POST" }),
  importMal: (alias: string) =>
    request<{ imported: number }>(withAccount("/api/providers/mal/import", { provider: "mal", alias }), { method: "POST" }),
  mediaList: () => cachedGet<MediaItem[]>(withAccount("/api/library")),
  mediaListManga: () => cachedGet<MediaItem[]>(withAccount("/api/library/manga")),
  activity: (page = 1) => cachedGet<ActivityItem[]>(withAccount(`/api/activity?page=${page}`)),
  season: (season: string, year: number) =>
    cachedGet<SeasonMedia[]>(withAccount(`/api/season?season=${season}&year=${year}`)),
  statistics: () => cachedGet<StatisticsResponse>(withAccount("/api/statistics")),
  statisticsPeriod: (from: string, to: string, type: "ANIME" | "MANGA" = "ANIME") =>
    request<MediaStatistics>(
      withAccount(
        `/api/statistics/period?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}&type=${type}`
      )
    ),
  statisticsExport: async (): Promise<Blob> => {
    const response = await rawRequest(withAccount("/api/statistics/export"));
    return response.blob();
  },
  mediaDetails: (mediaId: number) => cachedGet<MediaDetails>(withAccount(`/api/media/${mediaId}`)),
  mangaDetails: (mediaId: number) => cachedGet<MediaDetails>(withAccount(`/api/media/${mediaId}/manga`)),
  editEntry: (mediaId: number, update: MediaEntryUpdate) =>
    request<MediaListEntry>(withAccount(`/api/media/${mediaId}/entry`), {
      method: "PUT",
      body: JSON.stringify(update),
    }),
  bulkUpdateEntry: (mediaId: number, update: MediaEntryUpdate) =>
    request<BulkUpdateResult>(`/api/library/bulk-update?media_id=${mediaId}`, {
      method: "POST",
      body: JSON.stringify(update),
    }),
  deleteEntry: (entryId: number) =>
    request<void>(withAccount(`/api/library/entry/${entryId}`), { method: "DELETE" }),
  activePlayback: () => request<PlaybackCandidate | null>("/api/playback/active"),
  clearLocalData: () => request<void>("/api/data/clear", { method: "POST" }),
  cacheStatus: () => request<CacheStatusResponse>("/api/cache/status"),
  syncStatus: (season?: string, year?: number) => {
    const params = new URLSearchParams();
    if (season) params.set("season", season);
    if (year != null) params.set("year", String(year));
    const query = params.size ? `?${params.toString()}` : "";
    return request<SyncStatusResponse>(withAccount(`/api/sync/status${query}`));
  },
  forceSync: () => request<void>(withAccount("/api/sync"), { method: "POST" }),
  preferences: () => requestWithCache<UserPreferences>(withAccount("/api/preferences")),
  updatePreferences: (preferences: UserPreferencesUpdate) =>
    request<UserPreferences>(withAccount("/api/preferences"), {
      method: "PUT",
      body: JSON.stringify(preferences),
    }),
  pauseDetection: () => request<void>("/api/detection/pause", { method: "POST" }),
  resumeDetection: () => request<void>("/api/detection/resume", { method: "POST" }),
  detectionStatus: () => request<{ paused: boolean }>("/api/detection/status"),
  detectors: () => request<DetectorInfo[]>("/api/detectors"),
  updateDetector: (name: string, enabled: boolean) =>
    request<void>(`/api/detectors/${encodeURIComponent(name)}`, {
      method: "PUT",
      body: JSON.stringify({ enabled }),
    }),
  matchPlayback: (candidate: PlaybackCandidate) =>
    request<PlaybackMatchResponse>(withAccount("/api/playback/match"), { method: "POST", body: JSON.stringify(candidate) }),
  confirmPlayback: (eventId: number, mediaId: number, progress: number) =>
    request<void>(withAccount("/api/playback/confirm"), {
      method: "POST",
      body: JSON.stringify({ event_id: eventId, media_id: mediaId, progress }),
    }),
  undoPlayback: () => request<{ undone: boolean; media_id: number | null; restored_progress: number | null }>(withAccount("/api/playback/undo"), { method: "POST" }),
  retryPlayback: (eventId: number) =>
    request<{ retried: boolean; media_id: number; progress: number }>(withAccount(`/api/playback/retry/${eventId}`), { method: "POST" }),
  ignorePlayback: (eventId: number) =>
    request<void>("/api/playback/ignore", {
      method: "POST",
      body: JSON.stringify({ event_id: eventId }),
    }),
  playbackHistory: (status?: string, source?: string, dateFrom?: string, dateTo?: string) => {
    const params = new URLSearchParams();
    if (status) params.set("status", status);
    if (source) params.set("source", source);
    if (dateFrom) params.set("date_from", dateFrom);
    if (dateTo) params.set("date_to", dateTo);
    const query = params.size ? `?${params.toString()}` : "";
    return request<PlaybackEvent[]>(`/api/playback/history${query}`);
  },
  clearPlaybackHistory: () =>
    request<void>("/api/playback/history", { method: "DELETE" }),
  playbackPreferences: () =>
    request<PlaybackPreferences>("/api/playback/preferences"),
  updatePlaybackPreferences: (preferences: PlaybackPreferences) =>
    request<PlaybackPreferences>("/api/playback/preferences", {
      method: "PUT",
      body: JSON.stringify(preferences),
    }),
  updateProgress: (mediaId: number, progress: number, status?: string) =>
    request(withAccount("/api/library/progress"), {
      method: "POST",
      body: JSON.stringify({ media_id: mediaId, progress, status }),
    }),
  searchLibrary: (query: string) =>
    requestWithCache<LibrarySearchResponse>(withAccount(`/api/library/search?q=${encodeURIComponent(query)}`)),
  listLibraryTags: () => request<string[]>(withAccount("/api/library/tags")),
  getLibraryTags: (mediaId: number) => request<string[]>(withAccount(`/api/library/tags/${mediaId}`)),
  addLibraryTag: (mediaId: number, tag: string) =>
    request<void>(withAccount("/api/library/tags"), { method: "POST", body: JSON.stringify({ media_id: mediaId, tag }) }),
  removeLibraryTag: (mediaId: number, tag: string) =>
    request<void>(withAccount(`/api/library/tags/${mediaId}/${encodeURIComponent(tag)}`), { method: "DELETE" }),
  searchGlobal: (query: string) =>
    request<GlobalSearchResponse>(withAccount(`/api/search/media?q=${encodeURIComponent(query)}`)),
  searchManga: (query: string) =>
    request<GlobalSearchResponse>(withAccount(`/api/search/manga?q=${encodeURIComponent(query)}`)),
  discover: (filters: SearchFilters) => {
    const params = new URLSearchParams();
    params.set("q", filters.query);
    params.set("page", String(filters.page));
    params.set("per_page", String(filters.per_page));
    params.set("media_type", filters.media_type);
    params.set("sort", filters.sort);
    if (filters.genre) params.set("genre", filters.genre);
    if (filters.format) params.set("format", filters.format);
    if (filters.year != null) params.set("year", String(filters.year));
    if (filters.status) params.set("status", filters.status);
    if (filters.is_adult) params.set("is_adult", "true");
    return request<GlobalSearchResponse>(withAccount(`/api/search/media?${params.toString()}`));
  },
  createCorrection: (rawTitle: string, mediaId: number, animeTitle?: string | null, siteIdentifier?: string | null, siteAdapter?: string | null) =>
    request<void>("/api/playback/correction", {
      method: "POST",
      body: JSON.stringify({
        raw_title: rawTitle,
        media_id: mediaId,
        anime_title: animeTitle ?? undefined,
        site_identifier: siteIdentifier ?? undefined,
        site_adapter: siteAdapter ?? undefined,
      }),
    }),
  deleteCorrection: (rawTitle: string) =>
    request<void>(`/api/playback/correction/${encodeURIComponent(rawTitle)}`, { method: "DELETE" }),
};

export async function playbackSocket(): Promise<WebSocket> {
  const apiUrl = await getApiUrl();
  return new WebSocket(`${apiUrl.replace("http", "ws")}/api/playback/stream`);
}
