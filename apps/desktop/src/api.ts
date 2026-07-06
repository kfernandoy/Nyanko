import { BaseDirectory, readTextFile } from "@tauri-apps/plugin-fs";

import type {
  AccountInfo,
  BulkUpdateResult,
  ConflictInfo,
  ConflictResolution,
  ActivityItem,
  StatisticsResponse,
  CacheStatusResponse,
  CacheStatus,
  DetectorInfo,
  ExtensionBundle,
  ExtensionClientInfo,
  GlobalSearchResponse,
  WontWatchState,
  Health,
  LibraryFolder,
  LibrarySearchResponse,
  PendingLocalItem,
  ScanSummary,
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
  SearchResult,
  SeasonMedia,
  SyncStatusResponse,
  UserPreferences,
  UserPreferencesUpdate,
  TorrentItem,
  TorrentSource,
  TorrentFilter,
  TorrentSettings,
  TorrentDownloadResponse,
  LocalSeries,
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
  // Con VITE_API_URL (dev) hablamos con un backend fijo que NO es nuestro sidecar y no
  // escribe port/instance_token en AppData; leer los del último build de prod daría un
  // token que no corresponde y rompería la verificación de instancia en dev.
  if (import.meta.env.VITE_API_URL) return null;
  if (!("__TAURI_INTERNALS__" in window)) return null;
  try {
    // El sidecar escribe port/instance_token en NYANKO_DATA_DIR = app_data_dir()
    // (%APPDATA%\<identifier>), que es exactamente BaseDirectory.AppData. El prefijo
    // "nyanko/" apuntaba a una subcarpeta inexistente, así que el frontend nunca
    // encontraba el puerto real ni el token y dependía del 8765 hardcodeado.
    return (await readTextFile(name, { baseDir: BaseDirectory.AppData })).trim();
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

// En producción el sidecar se lanza en frío y aún no escucha cuando el webview monta.
// Sin esto, las primeras requests de arranque chocaban con un backend a medio arrancar
// (o con el puerto equivocado) y encadenaban timeouts de 15s → "Cargando biblioteca…"
// durante casi un minuto. Sondear un endpoint barato con timeout corto, re-resolviendo
// el puerto en cada intento, convierte eso en "espera hasta que esté listo y carga ya".
export async function waitForBackend(timeoutMs = 40_000): Promise<boolean> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    clearApiUrlCache(); // re-lee el port file por si el sidecar cayó a otro puerto
    const url = await resolveApiUrl();
    try {
      const response = await fetchWithTimeout(`${url}/`, {}, 1_000);
      if (response.ok) {
        cachedApiUrl = url;
        return true;
      }
    } catch {
      // aún no responde; reintentar
    }
    await new Promise((resolve) => setTimeout(resolve, 300));
  }
  return false;
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

// El token de instancia se lee de disco y se verifica UNA vez (single-flight) y se
// reutiliza en memoria: hacerlo por request duplicaba la latencia de toda la app.
let instanceTokenPromise: Promise<string | null> | null = null;

function resetInstanceToken(): void {
  instanceTokenPromise = null;
}

async function loadInstanceToken(apiUrl: string): Promise<string | null> {
  const expected = await readAppDataFile("instance_token");
  if (expected) {
    if (!(await verifyInstance(apiUrl, expected))) {
      clearApiUrlCache();
      throw new Error("El servicio local no pertenece a esta instancia de Nyanko");
    }
    return expected;
  }
  try {
    const response = await fetchWithTimeout(`${apiUrl}/api/instance`, {}, INSTANCE_TIMEOUT_MS);
    if (response.ok) {
      return ((await response.json()) as { token?: string }).token ?? null;
    }
  } catch {
    // La request real de abajo reporta el fallo de conexión de forma consistente.
  }
  return null;
}

function getInstanceToken(apiUrl: string): Promise<string | null> {
  instanceTokenPromise ??= loadInstanceToken(apiUrl).catch((reason) => {
    instanceTokenPromise = null;
    throw reason;
  });
  return instanceTokenPromise;
}

export interface ApiResponse<T> {
  data: T;
  cacheStatus: CacheStatus | null;
}

function normalizeAssetUrls<T>(value: T, apiUrl: string): T {
  if (typeof value === "string") {
    return (value.startsWith("/assets/") ? `${apiUrl}${value}` : value) as T;
  }
  if (Array.isArray(value)) {
    return value.map((item) => normalizeAssetUrls(item, apiUrl)) as T;
  }
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value).map(([key, item]) => [key, normalizeAssetUrls(item, apiUrl)]),
    ) as T;
  }
  return value;
}

async function rawRequest(path: string, options?: RequestInit, timeoutMs = REQUEST_TIMEOUT_MS): Promise<Response> {
  const apiUrl = await getApiUrl();
  const instanceToken = await getInstanceToken(apiUrl);
  let response: Response;
  try {
    response = await fetchWithTimeout(`${apiUrl}${path}`, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...(instanceToken ? { "X-Nyanko-Instance": instanceToken } : {}),
        ...options?.headers,
      },
    }, timeoutMs);
  } catch (reason) {
    // Fallo de red: puede que el sidecar se reiniciara con otro token/puerto.
    resetInstanceToken();
    clearApiUrlCache();
    throw reason;
  }
  if (!response.ok) {
    if (response.status === 401) resetInstanceToken();
    const payload = await response.json().catch(() => null);
    const detail = payload?.detail;
    throw new Error(typeof detail === "string" ? detail : (detail?.message ?? `HTTP ${response.status}`));
  }
  return response;
}

async function request<T>(path: string, options?: RequestInit, timeoutMs?: number): Promise<T> {
  const response = await rawRequest(path, options, timeoutMs);
  if (response.status === 204) return undefined as T;
  return normalizeAssetUrls(await response.json(), await getApiUrl());
}

async function requestWithCache<T>(path: string, options?: RequestInit): Promise<ApiResponse<T>> {
  const response = await rawRequest(path, options);
  const cacheStatus = response.headers.get("X-Cache-Status") as CacheStatus | null;
  const data = response.status === 204
    ? (undefined as T)
    : normalizeAssetUrls(await response.json(), await getApiUrl());
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
  kitsuConnect: (username: string, password: string, account = "default") =>
    request<{ ok: boolean }>("/api/auth/kitsu/connect", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password, account }),
    }),
  accounts: () => request<AccountInfo[]>("/api/accounts"),
  providers: () => request<ProviderInfo[]>("/api/providers"),
  updateAccount: (
    accountId: number,
    update: Partial<Pick<AccountInfo, "is_primary">>,
  ) =>
    request<AccountInfo>(`/api/accounts/${accountId}`, {
      method: "PUT",
      body: JSON.stringify(update),
    }),
  extensionBundle: () =>
    request<ExtensionBundle>("/api/extension/bundle"),
  extensionClients: () =>
    request<ExtensionClientInfo[]>("/api/extension/clients"),
  revokeExtensionClient: (clientId: number) =>
    request<void>(`/api/extension/clients/${clientId}`, { method: "DELETE" }),
  libraryFolders: () => request<LibraryFolder[]>("/api/library/folders"),
  addLibraryFolder: (path: string, recursive: boolean) =>
    request<LibraryFolder>("/api/library/folders", { method: "POST", body: JSON.stringify({ path, recursive }) }),
  deleteLibraryFolder: (folderId: number) =>
    request<void>(`/api/library/folders/${folderId}`, { method: "DELETE" }),
  // El escaneo recorre el disco; necesita mucho más que el timeout genérico de 15s.
  scanLibrary: () => request<ScanSummary>("/api/library/scan", { method: "POST" }, 300_000),
  pendingLocal: () => request<PendingLocalItem[]>("/api/library/pending-local"),
  getLocalLibrary: () => request<LocalSeries[]>("/api/library/local"),
  associateLocal: (body: { title: string; from_media_id?: number | null; external_id?: number | null; status?: string | null; media?: SearchResult | null }) =>
    request<void>(withAccount("/api/library/local/associate"), { method: "POST", body: JSON.stringify(body) }),
  getScanSettings: () => request<{ scan_on_startup: boolean; watch_folders: boolean }>("/api/library/scan-settings"),
  setScanSettings: (scanOnStartup: boolean, watchFolders: boolean) =>
    request<{ scan_on_startup: boolean; watch_folders: boolean }>("/api/library/scan-settings", { method: "PUT", body: JSON.stringify({ scan_on_startup: scanOnStartup, watch_folders: watchFolders }) }),
  conflicts: (status = "pending") =>
    request<ConflictInfo[]>(`/api/conflicts?status=${encodeURIComponent(status)}`),
  resolveConflict: (conflictId: number, resolution: ConflictResolution) =>
    request<ConflictInfo>(`/api/conflicts/${conflictId}/resolve`, { method: "POST", body: JSON.stringify(resolution) }),
  dismissConflict: (conflictId: number) =>
    request<ConflictInfo>(`/api/conflicts/${conflictId}/dismiss`, { method: "POST" }),
  logout: () => request<void>(withAccount("/api/auth/logout"), { method: "POST" }),
  logoutAccount: (provider: string, alias: string) =>
    request<void>(withAccount("/api/auth/logout", { provider, alias }), { method: "POST" }),
  mediaList: (view: "provider" | "combined" = "provider") => cachedGet<MediaItem[]>(withAccount(`/api/library?view=${view}`)),
  mediaListManga: (view: "provider" | "combined" = "provider") => cachedGet<MediaItem[]>(withAccount(`/api/library/manga?view=${view}`)),
  activity: (page = 1) => cachedGet<ActivityItem[]>(withAccount(`/api/activity?page=${page}`)),
  season: (season: string, year: number) =>
    cachedGet<SeasonMedia[]>(withAccount(`/api/season?season=${season}&year=${year}`)),
  statistics: () => cachedGet<StatisticsResponse>(withAccount("/api/statistics")),
  statisticsExport: async (): Promise<Blob> => {
    const response = await rawRequest(withAccount("/api/statistics/export"));
    return response.blob();
  },
  mediaDetails: (mediaId: number, account: ActiveAccount = activeAccount) => cachedGet<MediaDetails>(withAccount(`/api/media/${mediaId}`, account)),
  mangaDetails: (mediaId: number, account: ActiveAccount = activeAccount) => cachedGet<MediaDetails>(withAccount(`/api/media/${mediaId}/manga`, account)),
  editEntry: (mediaId: number, update: MediaEntryUpdate) =>
    request<MediaListEntry>(withAccount(`/api/media/${mediaId}/entry`), {
      method: "PUT",
      body: JSON.stringify(update),
    }),
  bulkUpdateEntry: (mediaId: number, update: MediaEntryUpdate) =>
    request<BulkUpdateResult>(withAccount(`/api/library/bulk-update?media_id=${mediaId}`), {
      method: "POST",
      body: JSON.stringify(update),
    }),
  deleteEntry: (entryId: number, account: ActiveAccount = activeAccount) =>
    request<void>(withAccount(`/api/library/entry/${entryId}`, account), { method: "DELETE" }),
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
  preferences: (account: ActiveAccount = activeAccount) =>
    requestWithCache<UserPreferences>(withAccount("/api/preferences", account)),
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
  confirmPlayback: (eventId: number, mediaId: number, progress: number, siteIdentifier?: string | null, siteAdapter?: string | null) =>
    request<void>(withAccount("/api/playback/confirm"), {
      method: "POST",
      body: JSON.stringify({ event_id: eventId, media_id: mediaId, progress, site_identifier: siteIdentifier ?? null, site_adapter: siteAdapter ?? null }),
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
    if (filters.season) params.set("season", filters.season);
    if (filters.status) params.set("status", filters.status);
    if (filters.is_adult) params.set("is_adult", "true");
    return request<GlobalSearchResponse>(withAccount(`/api/search/media?${params.toString()}`));
  },
  wontWatch: () => request<WontWatchState>(withAccount("/api/discover/wont-watch")),
  addWontWatch: (mediaId: number, title: string | null, coverImage: string | null) =>
    request<void>(withAccount("/api/discover/wont-watch"), {
      method: "POST",
      body: JSON.stringify({ media_id: mediaId, title, cover_image: coverImage }),
    }),
  removeWontWatch: (mediaId: number) =>
    request<void>(withAccount(`/api/discover/wont-watch/${mediaId}`), { method: "DELETE" }),
  setDiscoverShowMarked: (showMarked: boolean) =>
    request<void>(withAccount("/api/discover/settings"), {
      method: "PUT",
      body: JSON.stringify({ show_marked: showMarked }),
    }),
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
  torrentFeed: (refresh = false) => request<TorrentItem[]>(`/api/torrents/feed?refresh=${refresh}`),
  torrentUnread: () => request<{ count: number }>("/api/torrents/unread-count"),
  downloadTorrent: (signature: string, mode?: "magnet" | "torrent") => request<TorrentDownloadResponse>("/api/torrents/download", { method: "POST", body: JSON.stringify({ signature, mode: mode ?? null }) }),
  discardTorrent: (signature: string) => request<void>("/api/torrents/discard", { method: "POST", body: JSON.stringify({ signature }) }),
  torrentSources: () => request<TorrentSource[]>("/api/torrents/sources"),
  addTorrentSource: (b: Omit<TorrentSource, "id">) => request<TorrentSource>("/api/torrents/sources", { method: "POST", body: JSON.stringify(b) }),
  updateTorrentSource: (id: number, b: Omit<TorrentSource, "id">) => request<TorrentSource>(`/api/torrents/sources/${id}`, { method: "PUT", body: JSON.stringify(b) }),
  deleteTorrentSource: (id: number) => request<void>(`/api/torrents/sources/${id}`, { method: "DELETE" }),
  torrentFilters: () => request<TorrentFilter[]>("/api/torrents/filters"),
  addTorrentFilter: (b: Omit<TorrentFilter, "id">) => request<TorrentFilter>("/api/torrents/filters", { method: "POST", body: JSON.stringify(b) }),
  updateTorrentFilter: (id: number, b: Omit<TorrentFilter, "id">) => request<TorrentFilter>(`/api/torrents/filters/${id}`, { method: "PUT", body: JSON.stringify(b) }),
  deleteTorrentFilter: (id: number) => request<void>(`/api/torrents/filters/${id}`, { method: "DELETE" }),
  torrentSettings: () => request<TorrentSettings>("/api/torrents/settings"),
  putTorrentSettings: (b: TorrentSettings) => request<TorrentSettings>("/api/torrents/settings", { method: "PUT", body: JSON.stringify(b) }),
};

export async function playbackSocket(): Promise<WebSocket> {
  const apiUrl = await getApiUrl();
  return new WebSocket(`${apiUrl.replace("http", "ws")}/api/playback/stream`);
}
