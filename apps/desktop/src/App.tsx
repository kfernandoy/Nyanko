import { useCallback, useEffect, useMemo, useState } from "react";
import { openUrl } from "@tauri-apps/plugin-opener";
import { api, playbackSocket, setActiveAccount } from "./api";
import { getAutostart, setAutostart } from "./autostart";
import { listen } from "@tauri-apps/api/event";
import { DetectorSettingsView } from "./DetectorSettingsView";
import { PlaybackHistoryView } from "./PlaybackHistoryView";
import { DiscoveryView } from "./DiscoveryView";
import type {
  AccountUpdateResult,
  ActivityItem,
  MediaStatistics,
  StatisticsResponse,
  CacheStatus,
  DetectorInfo,
  ExtensionClientInfo,
  FuzzyDate,
  GlobalSearchResponse,
  Health,
  LibrarySearchResponse,
  MediaDetails,
  MediaEntryUpdate,
  MediaItem,
  PlaybackCandidate,
  PlaybackMatchResponse,
  PlaybackPreferences,
  ProviderCapabilities,
  ProviderInfo,
  SearchFilters,
  SearchResult,
  SeasonMedia,
  StatisticGroup,
  SyncStatusResponse,
  UserPreferences,
} from "./types";

type Filter = "ALL" | "CURRENT" | "PLANNING" | "COMPLETED" | "PAUSED" | "DROPPED";
type View = "library" | "manga" | "now-playing" | "history" | "activity" | "seasons" | "statistics" | "discovery" | "settings";
type CacheableView = "library" | "activity" | "seasons" | "statistics" | "details";
type Season = "WINTER" | "SPRING" | "SUMMER" | "FALL";
type MediaType = "ANIME" | "MANGA";

const SEASONS: Season[] = ["WINTER", "SPRING", "SUMMER", "FALL"];
const VIEW_COPY: Record<View, { eyebrow: string; title: string }> = {
  library: { eyebrow: "TU BIBLIOTECA", title: "Continúa donde quedaste." },
  manga: { eyebrow: "TU MANGA", title: "Lecturas en curso." },
  "now-playing": { eyebrow: "REPRODUCIENDO", title: "Detectado en este momento." },
  history: { eyebrow: "HISTORIAL LOCAL", title: "Decisiones y progreso detectado." },
  activity: { eyebrow: "ACTIVIDAD RECIENTE", title: "Tu actividad reciente." },
  seasons: { eyebrow: "TEMPORADA", title: "Anime de la temporada." },
  statistics: { eyebrow: "ESTADÍSTICAS", title: "Tu tiempo entre historias." },
  discovery: { eyebrow: "DESCUBRIMIENTO", title: "Busca y filtra anime." },
  settings: { eyebrow: "AJUSTES", title: "Controla cómo detecta Nyanko." },
};

function currentAnimeSeason(): { season: Season; year: number } {
  const now = new Date();
  return { season: SEASONS[Math.floor(now.getMonth() / 3)], year: now.getFullYear() };
}

function errorMessage(reason: unknown, fallback: string): string {
  return reason instanceof Error ? reason.message : typeof reason === "string" ? reason : fallback;
}

const DEFAULT_CAPABILITIES: ProviderCapabilities = {
  library: true,
  search: true,
  details: true,
  mutations: true,
  activity: true,
  statistics: true,
  seasons: true,
  manga: true,
};

export default function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [media, setMedia] = useState<MediaItem[]>([]);
  const [manga, setManga] = useState<MediaItem[]>([]);
  const [mangaLoaded, setMangaLoaded] = useState(false);
  const [activity, setActivity] = useState<ActivityItem[]>([]);
  const [activityLoaded, setActivityLoaded] = useState(false);
  const [activityPage, setActivityPage] = useState(1);
  const [activityHasMore, setActivityHasMore] = useState(true);
  const [activityLoadingMore, setActivityLoadingMore] = useState(false);
  const [seasonMedia, setSeasonMedia] = useState<SeasonMedia[]>([]);
  const [seasonCache, setSeasonCache] = useState<Record<string, SeasonMedia[]>>({});
  const [statistics, setStatistics] = useState<StatisticsResponse | null>(null);
  const [statisticsLoaded, setStatisticsLoaded] = useState(false);
  const [details, setDetails] = useState<MediaDetails | null>(null);
  const [detailCanonicalId, setDetailCanonicalId] = useState<number | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [candidate, setCandidate] = useState<PlaybackCandidate | null>(null);
  const [match, setMatch] = useState<PlaybackMatchResponse | null>(null);
  const [view, setView] = useState<View>("library");
  const [season, setSeason] = useState(currentAnimeSeason);
  const [filter, setFilter] = useState<Filter>("CURRENT");
  const [query, setQuery] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [sectionLoading, setSectionLoading] = useState(false);
  const [detectionPaused, setDetectionPaused] = useState(false);
  const [autostart, setAutostartState] = useState(false);
  const [historyVersion, setHistoryVersion] = useState(0);
  const [syncStatus, setSyncStatus] = useState<SyncStatusResponse | null>(null);
  const [viewCacheStatus, setViewCacheStatus] = useState<Record<CacheableView, CacheStatus | null>>({
    library: null,
    activity: null,
    seasons: null,
    statistics: null,
    details: null,
  });
  const [capabilities, setCapabilities] = useState<ProviderCapabilities>(DEFAULT_CAPABILITIES);
  const [activeAccount, setActiveAccountState] = useState({ provider: "anilist", alias: "default" });

  const setCacheStatus = useCallback((view: CacheableView, status: CacheStatus | null) => {
    setViewCacheStatus((previous) => ({ ...previous, [view]: status }));
  }, []);

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    setError(null);
    try {
      const accounts = await api.accounts();
      const selected = accounts.find((account) => account.is_primary && account.authenticated)
        ?? accounts.find((account) => account.authenticated);
      const activeProv = selected?.provider ?? "anilist";
      const activeAlias = selected?.alias ?? "default";
      setActiveAccount(activeProv, activeAlias);
      setActiveAccountState({ provider: activeProv, alias: activeAlias });
      const providerList = await api.providers();
      const activeProvider = providerList.find(p => p.name === (selected?.provider ?? "anilist"));
      setCapabilities(activeProvider?.capabilities ?? DEFAULT_CAPABILITIES);
      const service = await api.health();
      setHealth(service);
      if (service.authenticated) {
        const { data, cacheStatus } = await api.mediaList();
        setMedia(data);
        setCacheStatus("library", cacheStatus);
      } else {
        setMedia([]);
        setCacheStatus("library", null);
      }
    } catch (reason) {
      setError(errorMessage(reason, "No se pudo conectar al servicio local"));
    } finally {
      if (!silent) setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const loadManga = useCallback(async (silent = false) => {
    if (!silent) setSectionLoading(true);
    setError(null);
    try {
      const { data, cacheStatus } = await api.mediaListManga();
      setManga(data);
      setCacheStatus("library", cacheStatus);
      setMangaLoaded(true);
    } catch (reason) {
      setError(errorMessage(reason, "No se pudo cargar el manga"));
    } finally {
      if (!silent) setSectionLoading(false);
    }
  }, [setCacheStatus]);

  useEffect(() => {
    if (!health?.authenticated || view !== "manga" || mangaLoaded) return;
    let cancelled = false;
    const fetchManga = async () => {
      setSectionLoading(true);
      setError(null);
      try {
        const { data, cacheStatus } = await api.mediaListManga();
        if (!cancelled) {
          setManga(data);
          setCacheStatus("library", cacheStatus);
          setMangaLoaded(true);
        }
      } catch (reason) {
        if (!cancelled) setError(errorMessage(reason, "No se pudo cargar el manga"));
      } finally {
        if (!cancelled) setSectionLoading(false);
      }
    };
    void fetchManga();
    return () => { cancelled = true; };
  }, [health?.authenticated, mangaLoaded, setCacheStatus, view]);

  useEffect(() => {
    void getAutostart().then(setAutostartState);
  }, []);

  useEffect(() => {
    let cancelled = false;
    const refreshStatus = async () => {
      try {
        const status = await api.detectionStatus();
        if (!cancelled) setDetectionPaused(status.paused);
      } catch {
        // Ignore detection status errors.
      }
    };
    void refreshStatus();
    const timer = window.setInterval(refreshStatus, 5000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    if (!("__TAURI_INTERNALS__" in window)) return;
    let unlisten: (() => void) | undefined;
    listen<boolean>("detection-paused", (event) => setDetectionPaused(event.payload))
      .then((fn) => { unlisten = fn; })
      .catch(() => {});
    return () => { unlisten?.(); };
  }, []);

  useEffect(() => {
    if (health?.authenticated) return;
    const refresh = () => void load(true);
    window.addEventListener("focus", refresh);
    const timer = window.setInterval(refresh, 3000);
    return () => {
      window.removeEventListener("focus", refresh);
      window.clearInterval(timer);
    };
  }, [health?.authenticated, load]);

  useEffect(() => {
    let socket: WebSocket | undefined;
    let reconnectTimer: number | undefined;
    let disposed = false;
    const connect = async () => {
      if (disposed) return;
      socket = await playbackSocket();
      socket.onmessage = (event) => {
        const next = JSON.parse(event.data) as PlaybackCandidate | null;
        setCandidate(next);
        if (next && health?.authenticated) {
          api.matchPlayback(next)
            .then((result) => {
              if (result.event_status === "ignored" || result.event_status === "confirmed") {
                setCandidate(null);
                setMatch(null);
              } else {
                setMatch(result);
              }
            })
            .catch(() => setMatch(null));
        } else if (!next) {
          setMatch(null);
        }
      };
      socket.onclose = () => {
        if (!disposed) reconnectTimer = window.setTimeout(connect, 2000);
      };
    };
    const initialTimer = window.setTimeout(connect, 100);
    return () => {
      disposed = true;
      window.clearTimeout(initialTimer);
      if (reconnectTimer) window.clearTimeout(reconnectTimer);
      if (socket?.readyState === WebSocket.OPEN) socket.close();
      if (socket?.readyState === WebSocket.CONNECTING) {
        socket.onopen = () => socket?.close();
        socket.onclose = null;
      }
    };
  }, []);

  useEffect(() => {
    if (!health?.authenticated || !(["activity", "seasons", "statistics"] as View[]).includes(view)) return;
    const seasonKey = `${season.season}:${season.year}`;
    if (view === "activity" && activityLoaded) return;
    if (view === "statistics" && statisticsLoaded) return;
    if (view === "seasons" && seasonCache[seasonKey]) {
      setSeasonMedia(seasonCache[seasonKey]);
      return;
    }
    let cancelled = false;
    const fetchSection = async () => {
      setSectionLoading(true);
      setError(null);
      try {
        if (view === "activity") {
          const { data, cacheStatus } = await api.activity();
          if (!cancelled) {
            setActivity(data);
            setActivityLoaded(true);
            setActivityPage(1);
            setActivityHasMore(data.length === 30);
            setCacheStatus("activity", cacheStatus);
          }
        } else if (view === "seasons") {
          const { data, cacheStatus } = await api.season(season.season, season.year);
          if (!cancelled) {
            setSeasonCache((previous) => ({ ...previous, [seasonKey]: data }));
            setSeasonMedia(data);
            setCacheStatus("seasons", cacheStatus);
          }
        } else if (view === "statistics") {
          const { data, cacheStatus } = await api.statistics();
          if (!cancelled) {
            setStatistics(data);
            setStatisticsLoaded(true);
            setCacheStatus("statistics", cacheStatus);
          }
        }
      } catch (reason) {
        if (!cancelled) setError(errorMessage(reason, "No se pudo cargar esta sección"));
      } finally {
        if (!cancelled) setSectionLoading(false);
      }
    };
    void fetchSection();
    return () => { cancelled = true; };
  }, [activityLoaded, health?.authenticated, season, seasonCache, statisticsLoaded, view]);

  useEffect(() => {
    if (!health?.authenticated || !(["library", "activity", "seasons", "statistics"] as View[]).includes(view)) return;
    let cancelled = false;
    const fetchStatus = async () => {
      try {
        const status = await api.syncStatus(
          view === "seasons" ? season.season : undefined,
          view === "seasons" ? season.year : undefined,
        );
        if (!cancelled) setSyncStatus(status);
      } catch {
        // Ignore sync status errors.
      }
    };
    void fetchStatus();
    return () => { cancelled = true; };
  }, [health?.authenticated, season.season, season.year, view]);

  useEffect(() => {
    setView((current) => {
      const unsupported = new Set<View>([
        ...(!capabilities.manga      ? (["manga"]       as View[]) : []),
        ...(!capabilities.activity   ? (["activity"]    as View[]) : []),
        ...(!capabilities.seasons    ? (["seasons"]     as View[]) : []),
        ...(!capabilities.statistics ? (["statistics"]  as View[]) : []),
      ]);
      return unsupported.has(current) ? "library" : current;
    });
  }, [capabilities]);

  const connectAccount = async (provider = "anilist", alias = "default") => {
    try {
      const { url } = await api.authUrl(provider, alias);
      if ("__TAURI_INTERNALS__" in window) await openUrl(url);
      else if (!window.open(url, "_blank", "noopener,noreferrer")) {
        throw new Error("El navegador bloqueó la ventana de autenticación");
      }
    } catch (reason) {
      setError(errorMessage(reason, "No se pudo iniciar OAuth"));
    }
  };

  const toggleDetection = async () => {
    setError(null);
    try {
      if (detectionPaused) {
        await api.resumeDetection();
        setDetectionPaused(false);
      } else {
        await api.pauseDetection();
        setDetectionPaused(true);
      }
    } catch (reason) {
      setError(errorMessage(reason, "No se pudo cambiar el estado de detección"));
    }
  };

  const toggleAutostart = async () => {
    const next = !autostart;
    try {
      await setAutostart(next);
      setAutostartState(next);
    } catch (reason) {
      setError(errorMessage(reason, "No se pudo cambiar el inicio automático"));
    }
  };

  const confirmMatch = async (m: PlaybackMatchResponse) => {
    if (!m.match) return;
    setError(null);
    if (m.event_status === "confirmed") {
      setHistoryVersion((current) => current + 1);
      void load(true);
      return;
    }
    try {
      const episode = m.candidate.episode ?? 1;
      const progress = m.match.episodes != null ? Math.min(episode, m.match.episodes) : episode;
      await api.confirmPlayback(m.event_id, m.match.id, progress);
      setMatch((current) => (current ? { ...current, match: { ...current.match!, progress } } : current));
      setHistoryVersion((current) => current + 1);
      void load(true);
    } catch (reason) {
      setError(errorMessage(reason, "No se pudo actualizar el progreso"));
    }
  };

  const ignorePlayback = async () => {
    try {
      if (match) await api.ignorePlayback(match.event_id);
      setCandidate(null);
      setMatch(null);
      setHistoryVersion((current) => current + 1);
    } catch (reason) {
      setError(errorMessage(reason, "No se pudo ignorar la reproducción"));
    }
  };

  const undoPlayback = async () => {
    setError(null);
    try {
      const result = await api.undoPlayback();
      if (result.undone) {
        setHistoryVersion((current) => current + 1);
        void load(true);
      } else {
        setError("No hay una actualización reciente para deshacer");
      }
    } catch (reason) {
      setError(errorMessage(reason, "No se pudo deshacer la actualización"));
    }
  };

  const resetRemoteState = () => {
    setMedia([]);
    setManga([]);
    setMangaLoaded(false);
    setActivity([]);
    setActivityLoaded(false);
    setActivityPage(1);
    setActivityHasMore(true);
    setSeasonMedia([]);
    setSeasonCache({});
    setStatistics(null);
    setStatisticsLoaded(false);
    setDetails(null);
    setSyncStatus(null);
  };

  const clearLocalData = async () => {
    if (!window.confirm("¿Borrar token, caché, historial y preferencias locales? Esta acción no se puede deshacer.")) return;
    setLoading(true);
    setError(null);
    try {
      await api.clearLocalData();
      setHealth(null);
      resetRemoteState();
      setCandidate(null);
      void load();
    } catch (reason) {
      setError(errorMessage(reason, "No se pudieron borrar los datos locales"));
    } finally {
      setLoading(false);
    }
  };

  const forceSync = async () => {
    await api.forceSync();
    resetRemoteState();
    await load();
  };

  const refreshAfterPreferences = async () => {
    resetRemoteState();
    await load();
  };

  const changeAccount = async (provider: string, alias: string) => {
    setActiveAccount(provider, alias);
    setActiveAccountState({ provider, alias });
    resetRemoteState();
    setActivityLoaded(false);
    setStatisticsLoaded(false);
    await load();
  };

  const logout = async () => {
    await api.logout();
    resetRemoteState();
    setCandidate(null);
    setMatch(null);
    setHealth({ status: "ok", authenticated: false });
    setView("library");
  };



  const libraryMap = useMemo(() => {
    const map = new Map<number, MediaItem>();
    for (const item of media) {
      map.set(item.id, item);
    }
    return map;
  }, [media]);

  const setSeasonWithReset = (next: { season: Season; year: number }) => {
    setSeason(next);
  };

  const changeSeason = (offset: number) => {
    setSeason((current) => {
      const index = SEASONS.indexOf(current.season) + offset;
      if (index < 0) return { season: "FALL", year: current.year - 1 };
      if (index >= SEASONS.length) return { season: "WINTER", year: current.year + 1 };
      return { season: SEASONS[index], year: current.year };
    });
  };

  const handleStatisticsExport = async () => {
    try {
      const blob = await api.statisticsExport();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "nyanko-stats.json";
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      // silencio — el usuario verá que no descargó nada
    }
  };

  const openDetails = async (mediaId: number, mediaType: "ANIME" | "MANGA" = "ANIME") => {
    setDetailLoading(true);
    setError(null);
    const library = mediaType === "MANGA" ? manga : media;
    setDetailCanonicalId(library.find((item) => item.id === mediaId)?.canonical_id ?? null);
    try {
      const { data, cacheStatus } = mediaType === "MANGA"
        ? await api.mangaDetails(mediaId)
        : await api.mediaDetails(mediaId);
      setDetails(data);
      setCacheStatus("details", cacheStatus);
    } catch (reason) {
      setError(errorMessage(reason, mediaType === "MANGA" ? "No se pudo cargar el manga" : "No se pudo cargar el anime"));
    } finally {
      setDetailLoading(false);
    }
  };

  const refreshDetails = async () => {
    if (!details) return;
    const [{ data: updated, cacheStatus }] = await Promise.all([
      api.mediaDetails(details.id),
      load(true),
    ]);
    setDetails(updated);
    setCacheStatus("details", cacheStatus);
    setActivityLoaded(false);
    setStatisticsLoaded(false);
  };

  const loadMoreActivity = async () => {
    setActivityLoadingMore(true);
    setError(null);
    try {
      const nextPage = activityPage + 1;
      const { data, cacheStatus } = await api.activity(nextPage);
      setActivity((current) => [...new Map([...current, ...data].map((item) => [item.id, item])).values()]);
      setActivityPage(nextPage);
      setActivityHasMore(data.length === 30);
      setCacheStatus("activity", cacheStatus);
    } catch (reason) {
      setError(errorMessage(reason, "No se pudo cargar más actividad"));
    } finally {
      setActivityLoadingMore(false);
    }
  };

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand"><span>猫</span><strong>Nyanko</strong></div>
        <nav>
          {([
            ["library",     "Anime"],
            ...(capabilities.manga      ? [["manga",       "Manga"]]        : []),
            ["now-playing", "Reproduciendo"],
            ["history",     "Registro"],
            ...(capabilities.activity   ? [["activity",    "Actividad"]]    : []),
            ...(capabilities.seasons    ? [["seasons",     "Temporadas"]]   : []),
            ...(capabilities.statistics ? [["statistics",  "Estadísticas"]] : []),
            ["discovery",   "Descubrir"],
            ["settings",    "Ajustes"],
          ] as [View, string][]).map(([key, label]) => (
            <button key={key} className={view === key ? "active" : ""} onClick={() => setView(key)}>
              {label}
              {key === "now-playing" && candidate && <span className="nav-dot" />}
            </button>
          ))}
        </nav>
        <div className="service-status">
          <i className={health ? "online" : "offline"} />
          {health ? "Servicio local activo" : "Servicio desconectado"}
        </div>
        <button className="clear-data" onClick={() => void clearLocalData()}>
          Borrar datos locales
        </button>
        <button
          className={detectionPaused ? "detection-paused" : "detection-active"}
          onClick={() => void toggleDetection()}
        >
          {detectionPaused ? "Detección pausada" : "Detección activa"}
        </button>
        <label className="autostart-field">
          <input type="checkbox" checked={autostart} onChange={() => void toggleAutostart()} />
          Iniciar con Windows
        </label>
      </aside>

      <main>
        <header>
          <div>
            <p className="eyebrow">{VIEW_COPY[view].eyebrow}</p>
            <h1>{VIEW_COPY[view].title}</h1>
            {syncStatus && <SyncBadge view={view} syncStatus={syncStatus} season={season} />}
          {viewCacheStatus[view as CacheableView] && (
            <CacheBadge status={viewCacheStatus[view as CacheableView]} />
          )}
          </div>
        </header>

        {error && (
          <div className="error">
            <strong>No se pudo completar la operación.</strong><span>{error}</span>
            <button onClick={() => view === "library" ? void load() : setView("library")}>Volver</button>
          </div>
        )}

        {!health?.authenticated && view !== "settings" ? (
          <Empty title="Conecta tu cuenta" detail="Tu información aparecerá aquí." />
        ) : view === "library" ? (
          <LibraryView items={media} filter={filter} query={query} loading={loading} setFilter={setFilter} setQuery={setQuery} onSelect={openDetails} />
        ) : view === "manga" ? (
          <MangaLibraryView items={manga} loading={sectionLoading && !mangaLoaded} onSelect={(id) => void openDetails(id, "MANGA")} onRefresh={() => { setMangaLoaded(false); void loadManga(); }} />
        ) : view === "now-playing" ? (
          <NowPlayingView candidate={candidate} match={match} onIgnore={() => void ignorePlayback()} onUndo={() => void undoPlayback()} onSelect={openDetails} onCorrected={async (next) => { setMatch(next); if (next.match) { await confirmMatch(next); } }} />
        ) : view === "history" ? (
          <PlaybackHistoryView refreshKey={historyVersion} onSelect={openDetails} onRefresh={() => setHistoryVersion((v) => v + 1)} />
        ) : view === "discovery" ? (
          <DiscoveryView onSelect={(id, mediaType) => void openDetails(id, mediaType)} />
        ) : view === "settings" ? (
          <DetectorSettingsView
            authenticated={Boolean(health?.authenticated)}
            activeAccount={activeAccount}
            onSync={forceSync}
            onPreferencesChanged={refreshAfterPreferences}
            onLogout={logout}
            onConnectAccount={connectAccount}
            onAccountChanged={changeAccount}
          />
        ) : sectionLoading ? (
          <Empty title="Cargando…" />
        ) : view === "activity" ? (
          <ActivityView items={activity} hasMore={activityHasMore} loadingMore={activityLoadingMore} onLoadMore={loadMoreActivity} onSelect={openDetails} />
        ) : view === "seasons" ? (
          <SeasonsView items={seasonMedia} season={season} onMove={changeSeason} onChange={setSeasonWithReset} onSelect={openDetails} libraryMap={libraryMap} />
        ) : (
          <StatisticsView statistics={statistics} onExport={() => void handleStatisticsExport()} />
        )}
      </main>
      {detailLoading && <div className="modal-backdrop"><div className="modal-loading">Cargando información…</div></div>}
      {details && <DetailsModal details={details} canonicalId={detailCanonicalId} mediaType={details.media_type === "MANGA" ? "MANGA" : "ANIME"} onClose={() => setDetails(null)} onChanged={refreshDetails} onSelect={(id, type) => { setDetails(null); void openDetails(id, type); }} />}
    </div>
  );
}

type SearchScope = "library" | "global";

type CombinedResult =
  | { source: "library"; item: MediaItem }
  | { source: "global"; item: SearchResult };

function NowPlayingView({ candidate, match, onIgnore, onUndo, onSelect, onCorrected }: {
  candidate: PlaybackCandidate | null;
  match: PlaybackMatchResponse | null;
  onIgnore: () => void;
  onUndo: () => void;
  onSelect: (id: number) => void;
  onCorrected: (match: PlaybackMatchResponse) => Promise<void> | void;
}) {
  const [correcting, setCorrecting] = useState(false);
  const [query, setQuery] = useState("");
  const [combinedResults, setCombinedResults] = useState<CombinedResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [searched, setSearched] = useState(false);
  const [adding, setAdding] = useState<{ id: number; status: string } | null>(null);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const defaultQuery = (match?.candidate.anime_title ?? candidate?.anime_title ?? candidate?.raw_title ?? "").trim();

  useEffect(() => {
    setCorrecting(false);
    setQuery(defaultQuery);
    setCombinedResults([]);
    setSearched(false);
    setAdding(null);
    setSearchError(null);
    setActionError(null);
  }, [candidate?.raw_title, defaultQuery]);

  const search = useCallback(async (searchQuery: string) => {
    const queries = Array.from(new Set([
      searchQuery.trim(),
      searchQuery.replace(/\bseason\s+\d+\b/gi, "").trim(),
    ].filter((value) => value.length >= 2)));
    if (!queries.length) {
      setCombinedResults([]);
      setSearched(false);
      setSearchError(null);
      return;
    }
    setSearching(true);
    setSearched(false);
    setSearchError(null);
    try {
      const responses = await Promise.all(queries.flatMap((query) => [
        api.searchLibrary(query),
        api.searchGlobal(query),
      ]));
      const libraryResults = responses.flatMap((response, index) =>
        index % 2 === 0 ? (response as { data: LibrarySearchResponse }).data.results : [],
      );
      const globalResults = responses.flatMap((response, index) =>
        index % 2 === 1 ? (response as GlobalSearchResponse).results : [],
      );
      const seenLibrary = new Set<number>();
      const uniqueLibraryResults = libraryResults.filter((item) =>
        !seenLibrary.has(item.id) && (seenLibrary.add(item.id) || true)
      );
      const libraryIds = new Set(uniqueLibraryResults.map((item) => item.id));
      const seenGlobal = new Set<number>();
      const combined: CombinedResult[] = [
        ...uniqueLibraryResults.map((item) => ({ source: "library" as const, item })),
        ...globalResults
          .filter((item) => !libraryIds.has(item.id) && !seenGlobal.has(item.id) && (seenGlobal.add(item.id) || true))
          .map((item) => ({ source: "global" as const, item })),
      ];
      setCombinedResults(combined);
    } catch (reason) {
      setSearchError(reason instanceof Error ? reason.message : "No se pudo buscar");
    } finally {
      setSearching(false);
      setSearched(true);
    }
  }, []);

  useEffect(() => {
    if (!correcting) return;
    const timer = window.setTimeout(() => void search(query), 300);
    return () => window.clearTimeout(timer);
  }, [correcting, query, search]);

  const applyResult = async (mediaId: number, source: "library" | "global", status?: string) => {
    if (!candidate) return;
    setActionError(null);
    if (source === "global" && status) {
      setAdding({ id: mediaId, status });
    }
    try {
      if (source === "global" && status) {
        await api.editEntry(mediaId, { status, progress: 0 });
      }
      await api.createCorrection(candidate.raw_title, mediaId, candidate.anime_title, candidate.site_identifier, candidate.site_adapter);
      const corrected = await api.matchPlayback(candidate);
      await onCorrected(corrected);
      setCorrecting(false);
    } catch (reason) {
      setActionError(reason instanceof Error ? reason.message : "No se pudo aplicar la corrección");
    } finally {
      setAdding(null);
    }
  };

  if (!candidate) {
    return <Empty title="No hay reproducción detectada" detail="Abre un reproductor compatible y vuelve aquí." />;
  }
  const confidence = Math.round(candidate.confidence * 100);
  const season = candidate.season ? `T${candidate.season} · ` : "";
  const episodeType = candidate.episode_type && candidate.episode_type !== "regular"
    ? `${candidate.episode_type.toUpperCase()} `
    : "";
  const sourceLabel = candidate.source === "active-window" ? "ventana activa" : candidate.source;
  const matchScore = match ? Math.round(match.match_score * 100) : 0;
  const hasCorrection = match && match.match_score >= 0.99;

  const formatSeconds = (value: number | null | undefined): string => {
    if (value == null || !Number.isFinite(value)) return "--:--";
    const total = Math.max(0, Math.round(value));
    const hours = Math.floor(total / 3600);
    const minutes = Math.floor((total % 3600) / 60);
    const seconds = total % 60;
    const padded = `${minutes.toString().padStart(2, "0")}:${seconds.toString().padStart(2, "0")}`;
    return hours > 0 ? `${hours}:${padded}` : padded;
  };

  const progressPercent = candidate.duration_seconds
    ? Math.min(100, Math.max(0, (candidate.position_seconds ?? 0) / candidate.duration_seconds * 100))
    : 0;
  return (
    <section className="now-playing-view">
      <div className="detection-card">
        <div className="pulse" />
        <div>
          <small>FUENTE: {sourceLabel} · CONFIANZA {confidence}%{candidate.paused ? " · PAUSADO" : ""}{candidate.finished ? " · FINALIZADO" : ""}</small>
          <strong>{candidate.anime_title ?? candidate.raw_title}</strong>
          <span>{candidate.episode ? `${season}${episodeType}Episodio ${candidate.episode}` : "Episodio sin identificar"}</span>
          {candidate.duration_seconds != null && candidate.duration_seconds > 0 && (
            <div className="detection-progress">
              <div className="detection-progress-bar" style={{ width: `${progressPercent}%` }} />
              <small>{formatSeconds(candidate.position_seconds)} / {formatSeconds(candidate.duration_seconds)}</small>
            </div>
          )}
        </div>
      </div>

      {correcting ? (
        <div className="match-card correction-card">
          <h3>Corregir coincidencia</h3>
          <p>La búsqueda se hace en tu biblioteca y en AniList a la vez. Si la serie ya está en tu lista, aparece con su estado.</p>
          <div className="correction-search">
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Escribe al menos 2 caracteres…"
              onKeyDown={(event) => event.key === "Enter" && void search(query)}
            />
            <button onClick={() => void search(query)} disabled={searching || query.trim().length < 2}>{searching ? "Buscando…" : "Buscar"}</button>
          </div>
          {searchError && <p className="correction-empty" style={{ color: "#eaa9b7" }}>{searchError}</p>}
          {actionError && <p className="correction-empty" style={{ color: "#eaa9b7" }}>{actionError}</p>}
          {searching ? (
            <p className="correction-empty">Buscando…</p>
          ) : combinedResults.length > 0 ? (
            <div className="correction-results">
              {combinedResults.map((entry) => {
                const item = entry.item;
                const isLibrary = entry.source === "library";
                const libraryItem = isLibrary ? item as MediaItem : null;
                return (
                  <div key={item.id} className="correction-item">
                    <div className="poster" style={item.cover_image ? { backgroundImage: `url(${item.cover_image})` } : undefined}>
                      {libraryItem && <span className="season-library-badge">{STATUS_BADGE_LABELS[libraryItem.status] ?? libraryItem.status}</span>}
                    </div>
                    <span>{item.title}</span>
                    <small>{item.format ?? "Anime"}{(item as SearchResult).average_score ? ` · ${(item as SearchResult).average_score}%` : ""}</small>
                    {isLibrary ? (
                      <button className="primary small" onClick={() => void applyResult(item.id, "library")}>Usar este</button>
                    ) : (
                      <div className="correction-add-actions">
                        <button className="primary small" disabled={adding?.id === item.id && adding?.status === "CURRENT"} onClick={() => void applyResult(item.id, "global", "CURRENT")}>Añadir a Viendo</button>
                        <button className="small" disabled={adding?.id === item.id && adding?.status === "PLANNING"} onClick={() => void applyResult(item.id, "global", "PLANNING")}>A Planeados</button>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          ) : searched && query.trim().length >= 2 ? (
            <p className="correction-empty">No se encontró "{query}" en tu biblioteca ni en AniList.</p>
          ) : null}
          <div className="match-actions">
            <button onClick={() => setCorrecting(false)}>Cancelar</button>
          </div>
        </div>
      ) : match?.match ? (
        <div className="match-card">
          <h3>Coincidencia sugerida ({matchScore}%){hasCorrection && <small> · corregida manualmente</small>}</h3>
          <article className="now-playing-match-card clickable" onClick={() => onSelect(match.match!.id)}>
            <div className="poster" style={match.match.cover_image ? { backgroundImage: `url(${match.match.cover_image})` } : undefined} />
            <div className="now-playing-match-info">
              <strong title={match.match.title}>{match.match.title}</strong>
              <span>{match.match.format?.replace("_", " ")}{match.match.year ? ` · ${match.match.year}` : ""}</span>
              <span>{match.match.progress} / {match.match.episodes ?? "?"} episodios</span>
            </div>
          </article>
          <div className="match-actions">
            <button onClick={() => setCorrecting(true)}>Corregir</button>
            <button onClick={onIgnore}>Ignorar</button>
            <button onClick={onUndo}>Deshacer última</button>
          </div>
        </div>
      ) : (
        <div className="match-card">
          <h3>Sin coincidencia en tu biblioteca</h3>
          <p>No se encontró un anime que coincida con este título.</p>
          <div className="match-actions">
            <button onClick={() => setCorrecting(true)}>Buscar</button>
            <button onClick={onIgnore}>Ignorar</button>
            <button onClick={onUndo}>Deshacer última</button>
          </div>
        </div>
      )}
    </section>
  );
}

type SortKey = "TITLE" | "PROGRESS_DESC" | "SCORE_DESC" | "UPDATED_DESC";

function LibraryToolbar({
  filter,
  setFilter,
  query,
  setQuery,
  sort,
  setSort,
  formatFilter,
  setFormatFilter,
  formats,
  counts,
  statusLabels,
  searchPlaceholder,
  onRefresh,
  children,
}: {
  filter: Filter;
  setFilter: (filter: Filter) => void;
  query: string;
  setQuery: (query: string) => void;
  sort: SortKey;
  setSort: (sort: SortKey) => void;
  formatFilter: string;
  setFormatFilter: (format: string) => void;
  formats: string[];
  counts: Record<Filter, number> & { total: number };
  statusLabels: Record<Filter, string>;
  searchPlaceholder: string;
  onRefresh?: () => void;
  children?: React.ReactNode;
}) {
  const formatLabel = (format: string) => format.replace("_", " ");
  return <>
    <section className="toolbar">
      <div className="filters">
        {(["CURRENT", "COMPLETED", "PAUSED", "DROPPED", "PLANNING", "ALL"] as Filter[]).map((value) => (
          <button key={value} className={filter === value ? "selected" : ""} onClick={() => setFilter(value)}>
            {statusLabels[value]} <small>{value === "ALL" ? counts.total : counts[value]}</small>
          </button>
        ))}
      </div>
      <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={searchPlaceholder} />
      {onRefresh && <button className="small" onClick={onRefresh}>Recargar</button>}
    </section>
    <div className="season-filters library-filters">
      <select value={sort} onChange={(event) => setSort(event.target.value as SortKey)}>
        <option value="TITLE">Título A–Z</option>
        <option value="PROGRESS_DESC">Progreso descendente</option>
        <option value="SCORE_DESC">Puntuación descendente</option>
        <option value="UPDATED_DESC">Última actualización</option>
      </select>
      <select value={formatFilter} onChange={(event) => setFormatFilter(event.target.value)}>
        <option value="ALL">Todos los formatos</option>
        {formats.map((format) => <option key={format} value={format}>{formatLabel(format)}</option>)}
      </select>
      {children}
    </div>
  </>;
}

function LibraryView({ items, filter, query, loading, setFilter, setQuery, onSelect }: {
  items: MediaItem[]; filter: Filter; query: string; loading: boolean;
  setFilter: (filter: Filter) => void; setQuery: (query: string) => void; onSelect: (id: number) => void;
}) {
  const [sort, setSort] = useState<SortKey>("TITLE");
  const [formatFilter, setFormatFilter] = useState<string>("ALL");
  const [yearFilter, setYearFilter] = useState<string>("ALL");
  const [genreFilter, setGenreFilter] = useState<string>("ALL");
  const [tagFilter, setTagFilter] = useState<string>("ALL");

  const counts = Object.fromEntries((["CURRENT", "PLANNING", "COMPLETED", "PAUSED", "DROPPED"] as Filter[]).map((status) => [status, items.filter((item) => item.status === status).length])) as Record<Filter, number> & { total: number };
  counts.total = items.length;

  const formats = useMemo(() => Array.from(new Set(items.map((item) => item.format).filter((format): format is string => Boolean(format)))).sort(), [items]);
  const years = useMemo(() => Array.from(new Set(items.map((item) => item.year).filter((year): year is number => year != null))).sort((a, b) => b - a), [items]);
  const genres = useMemo(() => Array.from(new Set(items.flatMap((item) => item.genres ?? []))).sort(), [items]);
  const tags = useMemo(() => Array.from(new Set(items.flatMap((item) => item.tags ?? []))).sort(), [items]);

  const visible = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase();
    const result = items.filter(
      (item) =>
        (filter === "ALL" || item.status === filter) &&
        (!normalized || item.title.toLocaleLowerCase().includes(normalized)) &&
        (formatFilter === "ALL" || item.format === formatFilter) &&
        (yearFilter === "ALL" || String(item.year) === yearFilter) &&
        (genreFilter === "ALL" || (item.genres ?? []).includes(genreFilter)) &&
        (tagFilter === "ALL" || (item.tags ?? []).includes(tagFilter)),
    );
    result.sort((a, b) => {
      if (sort === "TITLE") return a.title.localeCompare(b.title);
      if (sort === "PROGRESS_DESC") return b.progress - a.progress;
      if (sort === "SCORE_DESC") return (b.score ?? 0) - (a.score ?? 0);
      return (b.updated_at ?? 0) - (a.updated_at ?? 0);
    });
    return result;
  }, [filter, formatFilter, genreFilter, items, query, sort, tagFilter, yearFilter]);

  return <>
    <LibraryToolbar
      filter={filter}
      setFilter={setFilter}
      query={query}
      setQuery={setQuery}
      sort={sort}
      setSort={setSort}
      formatFilter={formatFilter}
      setFormatFilter={setFormatFilter}
      formats={formats}
      counts={counts}
      statusLabels={{ CURRENT: "Viendo", PLANNING: "Planeados", COMPLETED: "Completados", PAUSED: "Pausados", DROPPED: "Abandonados", ALL: "Todos" }}
      searchPlaceholder="Buscar anime…"
    >
      <select value={yearFilter} onChange={(event) => setYearFilter(event.target.value)}>
        <option value="ALL">Todos los años</option>
        {years.map((year) => <option key={year} value={String(year)}>{year}</option>)}
      </select>
      <select value={genreFilter} onChange={(event) => setGenreFilter(event.target.value)}>
        <option value="ALL">Todos los géneros</option>
        {genres.map((genre) => <option key={genre} value={genre}>{genre}</option>)}
      </select>
      <select value={tagFilter} onChange={(event) => setTagFilter(event.target.value)}>
        <option value="ALL">Todas las etiquetas</option>
        {tags.map((tag) => <option key={tag} value={tag}>{tag}</option>)}
      </select>
    </LibraryToolbar>
    {loading ? <Empty title="Cargando biblioteca…" /> : visible.length === 0 ? <Empty title="No hay resultados" detail="Prueba otro filtro o búsqueda." /> : (
      <section className="media-grid">{visible.map((item) => <MediaCard key={item.id} item={item} mediaType="ANIME" onSelect={onSelect} />)}</section>
    )}
  </>;
}

function MangaLibraryView({ items, loading, onSelect, onRefresh }: {
  items: MediaItem[]; loading: boolean; onSelect: (id: number) => void; onRefresh: () => void;
}) {
  const [filter, setFilter] = useState<Filter>("CURRENT");
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<SortKey>("TITLE");
  const [formatFilter, setFormatFilter] = useState<string>("ALL");

  const counts = Object.fromEntries((["CURRENT", "PLANNING", "COMPLETED", "PAUSED", "DROPPED"] as Filter[]).map((status) => [status, items.filter((item) => item.status === status).length])) as Record<Filter, number> & { total: number };
  counts.total = items.length;
  const formats = useMemo(() => Array.from(new Set(items.map((item) => item.format).filter((format): format is string => Boolean(format)))).sort(), [items]);
  const visible = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase();
    const result = items.filter(
      (item) =>
        (filter === "ALL" || item.status === filter) &&
        (!normalized || item.title.toLocaleLowerCase().includes(normalized)) &&
        (formatFilter === "ALL" || item.format === formatFilter),
    );
    result.sort((a, b) => {
      if (sort === "TITLE") return a.title.localeCompare(b.title);
      if (sort === "PROGRESS_DESC") return b.progress - a.progress;
      if (sort === "SCORE_DESC") return (b.score ?? 0) - (a.score ?? 0);
      return (b.updated_at ?? 0) - (a.updated_at ?? 0);
    });
    return result;
  }, [filter, formatFilter, items, query, sort]);

  return <>
    <LibraryToolbar
      filter={filter}
      setFilter={setFilter}
      query={query}
      setQuery={setQuery}
      sort={sort}
      setSort={setSort}
      formatFilter={formatFilter}
      setFormatFilter={setFormatFilter}
      formats={formats}
      counts={counts}
      statusLabels={{ CURRENT: "Leyendo", PLANNING: "Planeados", COMPLETED: "Completados", PAUSED: "Pausados", DROPPED: "Abandonados", ALL: "Todos" }}
      searchPlaceholder="Buscar manga…"
      onRefresh={onRefresh}
    />
    {loading ? <Empty title="Cargando manga…" /> : visible.length === 0 ? <Empty title="No hay resultados" detail="Prueba otro filtro o búsqueda." /> : (
      <section className="media-grid">{visible.map((item) => <MediaCard key={item.id} item={item} mediaType="MANGA" onSelect={onSelect} />)}</section>
    )}
  </>;
}

function ActivityView({ items, hasMore, loadingMore, onLoadMore, onSelect }: {
  items: ActivityItem[];
  hasMore: boolean;
  loadingMore: boolean;
  onLoadMore: () => Promise<void>;
  onSelect: (id: number) => void;
}) {
  const [type, setType] = useState("ALL");
  const [status, setStatus] = useState("ALL");
  const [dateFrom, setDateFrom] = useState("");
  const statuses = useMemo(() => Array.from(new Set(items.map((item) => item.status))).sort(), [items]);
  const visible = useMemo(() => {
    const from = dateFrom ? new Date(`${dateFrom}T00:00:00`).getTime() / 1000 : 0;
    return items.filter((item) =>
      (type === "ALL" || (type === "PROGRESS") === Boolean(item.progress)) &&
      (status === "ALL" || item.status === status) &&
      item.created_at >= from
    );
  }, [dateFrom, items, status, type]);

  if (!items.length) return <Empty title="No hay actividad reciente" />;
  return <>
    <div className="season-filters">
      <select value={type} onChange={(event) => setType(event.target.value)}>
        <option value="ALL">Todos los tipos</option>
        <option value="PROGRESS">Avances de episodio</option>
        <option value="STATUS">Cambios de estado</option>
      </select>
      <select value={status} onChange={(event) => setStatus(event.target.value)}>
        <option value="ALL">Todos los estados</option>
        {statuses.map((value) => <option key={value} value={value}>{value}</option>)}
      </select>
      <input type="date" value={dateFrom} onChange={(event) => setDateFrom(event.target.value)} aria-label="Actividad desde" />
    </div>
    {visible.length === 0 ? <Empty title="No hay resultados" detail="Prueba otros filtros." /> : <section className="activity-list">{visible.map((item) => (
    <article className="activity-row clickable" key={item.id} onClick={() => onSelect(item.media_id)}>
      <div className="activity-cover" style={item.cover_image ? { backgroundImage: `url(${item.cover_image})` } : undefined} />
      <div><strong>{item.title}</strong><span>{item.status}{item.progress ? ` · ${item.progress}` : ""}</span></div>
      <time>{new Intl.DateTimeFormat("es", { dateStyle: "medium", timeStyle: "short" }).format(item.created_at * 1000)}</time>
    </article>
    ))}</section>}
    {hasMore && <button className="primary load-more" disabled={loadingMore} onClick={() => void onLoadMore()}>{loadingMore ? "Cargando…" : "Cargar más"}</button>}
  </>;
}

const STATUS_BADGE_LABELS: Record<string, string> = {
  CURRENT: "Viendo",
  COMPLETED: "Completado",
  PAUSED: "Pausado",
  DROPPED: "Abandonado",
  PLANNING: "Planeado",
};

type SeasonFormatKey = "TV" | "TV_SHORT" | "ONA_OVA_SPECIAL" | "MOVIE" | "OTHER";

const SEASON_GROUPS: { label: string; key: SeasonFormatKey }[] = [
  { label: "TV", key: "TV" },
  { label: "TV Short", key: "TV_SHORT" },
  { label: "ONA / OVA / Especial", key: "ONA_OVA_SPECIAL" },
  { label: "Películas", key: "MOVIE" },
  { label: "Otros", key: "OTHER" },
];

const FORMAT_LABELS: Record<string, string> = {
  TV: "TV",
  TV_SHORT: "TV Short",
  ONA: "ONA",
  OVA: "OVA",
  SPECIAL: "Especial",
  MOVIE: "Película",
};

function seasonFormatKey(format: string | null | undefined): SeasonFormatKey {
  if (!format) return "OTHER";
  if (["ONA", "OVA", "SPECIAL"].includes(format)) return "ONA_OVA_SPECIAL";
  if (SEASON_GROUPS.some((group) => group.key === format)) return format as SeasonFormatKey;
  return "OTHER";
}

function SeasonsView({ items, season, onMove, onChange, onSelect, libraryMap }: { items: SeasonMedia[]; season: { season: Season; year: number }; onMove: (offset: number) => void; onChange: (season: { season: Season; year: number }) => void; onSelect: (id: number) => void; libraryMap: Map<number, MediaItem> }) {
  const labels: Record<Season, string> = { WINTER: "Invierno", SPRING: "Primavera", SUMMER: "Verano", FALL: "Otoño" };
  const [search, setSearch] = useState("");
  const [format, setFormat] = useState("ALL");
  const [sort, setSort] = useState("POPULARITY");
  const visibleItems = useMemo(() => {
    const normalized = search.trim().toLocaleLowerCase();
    return items.filter((item) => (format === "ALL" || item.format === format) && (!normalized || item.title.toLocaleLowerCase().includes(normalized))).sort((left, right) => {
      if (sort === "TITLE") return left.title.localeCompare(right.title);
      if (sort === "SCORE") return (right.average_score ?? 0) - (left.average_score ?? 0);
      if (sort === "DATE") return dateNumber(left.start_date) - dateNumber(right.start_date);
      return right.popularity - left.popularity;
    });
  }, [format, items, search, sort]);
  const groups = useMemo(() => {
    if (format !== "ALL") {
      return [{ label: FORMAT_LABELS[format] ?? format, key: seasonFormatKey(format) }];
    }
    return SEASON_GROUPS;
  }, [format]);
  const years = Array.from({ length: new Date().getFullYear() - 1970 + 3 }, (_, index) => new Date().getFullYear() + 2 - index);
  return <>
    <div className="season-controls"><button onClick={() => onMove(-1)}>←</button><select value={season.season} onChange={(event) => onChange({ season: event.target.value as Season, year: season.year })}>{SEASONS.map((value) => <option value={value} key={value}>{labels[value]}</option>)}</select><select value={season.year} onChange={(event) => onChange({ season: season.season, year: Number(event.target.value) })}>{years.map((year) => <option value={year} key={year}>{year}</option>)}</select><button onClick={() => onMove(1)}>→</button></div>
    <div className="season-filters"><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Buscar en la temporada…" /><select value={format} onChange={(event) => setFormat(event.target.value)}><option value="ALL">Todos los formatos</option><option value="TV">TV</option><option value="TV_SHORT">TV Short</option><option value="ONA">ONA</option><option value="OVA">OVA</option><option value="SPECIAL">Especial</option><option value="MOVIE">Película</option></select><select value={sort} onChange={(event) => setSort(event.target.value)}><option value="POPULARITY">Popularidad</option><option value="TITLE">Título A–Z</option><option value="DATE">Fecha de inicio</option><option value="SCORE">Puntuación</option></select></div>
    {!visibleItems.length ? <Empty title="No hay títulos para estos filtros" /> : groups.map((group) => {
      const groupItems = visibleItems.filter((item) => seasonFormatKey(item.format) === group.key);
      if (!groupItems.length) return null;
      return (
        <section key={group.label} className="season-group">
          <h3 className="season-group-title">{group.label}</h3>
          <section className="media-grid">{groupItems.map((item) => {
            const libraryEntry = libraryMap.get(item.id);
            return (
              <article className="media-card clickable" key={item.id} onClick={() => onSelect(item.id)}>
                <div className="poster" style={item.cover_image ? { backgroundImage: `url(${item.cover_image})` } : undefined}>
                  {libraryEntry && <span className="season-library-badge">{STATUS_BADGE_LABELS[libraryEntry.status] ?? libraryEntry.status}</span>}
                </div>
                <div className="media-info"><strong title={item.title}>{item.title}</strong><span className="season-studio">{item.studios.slice(0, 2).join(", ") || "Estudio desconocido"}</span><span>{item.format ?? "Anime"} · {item.episodes ?? "?"} episodios · {formatFuzzyDate(item.start_date)}</span><span>{item.average_score ? `${item.average_score}%` : "Sin puntuación"}{item.next_airing_at && item.next_airing_at > Date.now() / 1000 ? ` · Ep ${item.next_episode ?? "?"} en ${formatCountdown(item.next_airing_at)}` : ""}</span></div>
              </article>
            );
          })}</section>
        </section>
      );
    })}
  </>;
}

function StatisticsView({
  statistics,
  onExport,
}: {
  statistics: StatisticsResponse | null;
  onExport: () => void;
}) {
  const [tab, setTab] = useState<"ANIME" | "MANGA">("ANIME");
  const [fromA, setFromA] = useState("");
  const [toA, setToA] = useState("");
  const [fromB, setFromB] = useState("");
  const [toB, setToB] = useState("");
  const [periodA, setPeriodA] = useState<MediaStatistics | null>(null);
  const [periodB, setPeriodB] = useState<MediaStatistics | null>(null);
  const [periodLoading, setPeriodLoading] = useState(false);

  useEffect(() => {
    setPeriodA(null);
    setPeriodB(null);
  }, [tab]);

  if (!statistics) return <Empty title="No hay estadísticas disponibles" />;
  const stats = tab === "ANIME" ? statistics.anime : statistics.manga;

  const handleCompare = async () => {
    setPeriodLoading(true);
    try {
      const [a, b] = await Promise.all([
        fromA && toA ? api.statisticsPeriod(fromA, toA, tab) : Promise.resolve(null),
        fromB && toB ? api.statisticsPeriod(fromB, toB, tab) : Promise.resolve(null),
      ]);
      setPeriodA(a);
      setPeriodB(b);
    } catch {
      // ignorar
    } finally {
      setPeriodLoading(false);
    }
  };

  return (
    <>
      <div className="stat-tabs">
        <button className={tab === "ANIME" ? "active" : ""} onClick={() => setTab("ANIME")}>
          Anime
        </button>
        <button className={tab === "MANGA" ? "active" : ""} onClick={() => setTab("MANGA")}>
          Manga
        </button>
      </div>
      <section className="stat-cards">
        <StatCard label={tab === "ANIME" ? "Anime vistos" : "Manga leídos"} value={stats.count.toLocaleString("es")} />
        <StatCard
          label={tab === "ANIME" ? "Episodios" : "Capítulos"}
          value={stats.episodes_watched.toLocaleString("es")}
        />
        {tab === "ANIME" && (
          <StatCard label="Horas" value={Math.round(stats.minutes_watched / 60).toLocaleString("es")} />
        )}
        <StatCard label="Puntuación media" value={stats.mean_score.toFixed(1)} />
      </section>
      <section className="stat-panels">
        <StatBars title="Géneros principales" items={stats.genres} />
        <StatBars title="Formatos" items={stats.formats} />
        <StatBars title="Años" items={stats.release_years} />
        {stats.studios.length > 0 && <StatBars title="Estudios" items={stats.studios} />}
        {stats.countries.length > 0 && <StatBars title="Países" items={stats.countries} />}
        <StatBars title="Estados de lista" items={stats.statuses} />
      </section>
      <section className="stat-period">
        <h2>Comparación por períodos</h2>
        <div className="stat-period-inputs">
          <div>
            <label>Rango A</label>
            <input type="date" value={fromA} onChange={(e) => setFromA(e.target.value)} />
            <input type="date" value={toA} onChange={(e) => setToA(e.target.value)} />
          </div>
          <div>
            <label>Rango B</label>
            <input type="date" value={fromB} onChange={(e) => setFromB(e.target.value)} />
            <input type="date" value={toB} onChange={(e) => setToB(e.target.value)} />
          </div>
          <button onClick={() => void handleCompare()} disabled={periodLoading}>
            {periodLoading ? "Cargando…" : "Comparar"}
          </button>
        </div>
        {(periodA !== null || periodB !== null) && (
          <div className="stat-period-comparison">
            <PeriodColumn
              stats={periodA}
              label={fromA && toA ? `${fromA} – ${toA}` : "Rango A"}
              mediaType={tab}
            />
            <PeriodColumn
              stats={periodB}
              label={fromB && toB ? `${fromB} – ${toB}` : "Rango B"}
              mediaType={tab}
            />
          </div>
        )}
      </section>
      <section className="stat-export">
        <button onClick={onExport}>Exportar JSON</button>
      </section>
    </>
  );
}

function PeriodColumn({
  stats,
  label,
  mediaType,
}: {
  stats: MediaStatistics | null;
  label: string;
  mediaType: "ANIME" | "MANGA";
}) {
  return (
    <div className="stat-period-column">
      <strong>{label}</strong>
      {!stats ? (
        <p className="stat-period-empty">Sin entradas en este período</p>
      ) : (
        <>
          <section className="stat-cards">
            <StatCard label="Obras" value={stats.count.toLocaleString("es")} />
            <StatCard
              label={mediaType === "ANIME" ? "Episodios" : "Capítulos"}
              value={stats.episodes_watched.toLocaleString("es")}
            />
            <StatCard
              label="Puntuación media"
              value={stats.mean_score > 0 ? stats.mean_score.toFixed(1) : "—"}
            />
          </section>
          <section className="stat-panels">
            {stats.genres.length > 0 && <StatBars title="Géneros" items={stats.genres} />}
            {stats.formats.length > 0 && <StatBars title="Formatos" items={stats.formats} />}
            {stats.release_years.length > 0 && <StatBars title="Años" items={stats.release_years} />}
          </section>
        </>
      )}
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <article className="stat-card">
      <span>{label}</span>
      <strong>{value}</strong>
    </article>
  );
}

function StatBars({ title, items }: { title: string; items: StatisticGroup[] }) {
  if (items.length === 0) return null;
  const max = Math.max(...items.map((item) => item.count), 1);
  return (
    <article className="stat-panel">
      <h2>{title}</h2>
      {items.map((item) => (
        <div className="stat-row" key={item.label}>
          <div>
            <span>{item.label}</span>
            <strong>{item.count}</strong>
          </div>
          <i>
            <b style={{ width: `${(item.count / max) * 100}%` }} />
          </i>
        </div>
      ))}
    </article>
  );
}

function MediaCard({ item, mediaType, onSelect }: { item: MediaItem; mediaType: MediaType; onSelect: (id: number) => void }) {
  const total = mediaType === "MANGA" ? (item.chapters ?? 0) : (item.episodes ?? 0);
  const percentage = total ? Math.min(100, item.progress / total * 100) : 0;
  const progressLabel = mediaType === "MANGA"
    ? `${item.progress} / ${item.chapters ?? "?"} capítulos${item.volumes ? ` · ${item.volumes} vol.` : ""}`
    : `${item.progress} / ${item.episodes ?? "?"} episodios`;
  return <article className="media-card clickable" onClick={() => onSelect(item.id)}>
    <div className="poster" style={item.cover_image ? { backgroundImage: `url(${item.cover_image})` } : undefined} />
    <div className="media-info"><strong title={item.title}>{item.title}</strong><span>{progressLabel}</span><div className="progress"><i style={{ width: `${percentage}%` }} /></div>{(item.tags ?? []).length > 0 && <div className="media-tags">{item.tags?.map((tag) => <span key={tag}>{tag}</span>)}</div>}</div>
  </article>;
}

function TagEditor({ canonicalId, onChanged }: { canonicalId: number; onChanged?: () => void }) {
  const [tags, setTags] = useState<string[]>([]);
  const [newTag, setNewTag] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api.getLibraryTags(canonicalId)
      .then((result) => { if (!cancelled) setTags(result); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [canonicalId]);

  const add = async () => {
    const tag = newTag.trim();
    if (!tag || tags.includes(tag)) return;
    setLoading(true);
    try {
      await api.addLibraryTag(canonicalId, tag);
      setTags((previous) => [...previous, tag].sort());
      setNewTag("");
      onChanged?.();
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  };

  const remove = async (tag: string) => {
    setLoading(true);
    try {
      await api.removeLibraryTag(canonicalId, tag);
      setTags((previous) => previous.filter((value) => value !== tag));
      onChanged?.();
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="tag-editor">
      <h4>Etiquetas</h4>
      <div className="tag-list">
        {tags.map((tag) => (
          <span key={tag} className="tag-chip">
            {tag}
            <button onClick={() => void remove(tag)} aria-label={`Eliminar ${tag}`}>×</button>
          </span>
        ))}
      </div>
      <div className="tag-input">
        <input
          value={newTag}
          onChange={(event) => setNewTag(event.target.value)}
          onKeyDown={(event) => event.key === "Enter" && void add()}
          placeholder="Añadir etiqueta…"
          disabled={loading}
        />
        <button onClick={() => void add()} disabled={loading || !newTag.trim()}>Añadir</button>
      </div>
    </div>
  );
}

const RELATION_TYPE_LABELS: Record<string, string> = {
  SEQUEL: "Secuela",
  PREQUEL: "Precuela",
  ALTERNATIVE: "Alternativo",
  SIDE_STORY: "Historia paralela",
  CHARACTER: "Personaje",
  SUMMARY: "Resumen",
  OTHER: "Relacionado",
  PARENT: "Obra principal",
  COMPILATION: "Recopilación",
  CONTAINS: "Contiene",
  SOURCE: "Fuente",
  ADAPTATION: "Adaptación",
  SPIN_OFF: "Spin-off",
};

function formatToMediaType(format: string | null | undefined): "ANIME" | "MANGA" {
  return ["MANGA", "NOVEL", "ONE_SHOT"].includes(format ?? "") ? "MANGA" : "ANIME";
}

function DetailsModal({ details, canonicalId, mediaType, onClose, onChanged, onSelect }: {
  details: MediaDetails;
  canonicalId: number | null;
  mediaType: "ANIME" | "MANGA";
  onClose: () => void;
  onChanged: () => Promise<void>;
  onSelect?: (id: number, type: "ANIME" | "MANGA") => void;
}) {
  const isManga = mediaType === "MANGA";
  const entry = details.list_entry;
  const [tab, setTab] = useState<"info" | "reparto" | "recomendaciones" | "edit">("info");
  const [status, setStatus] = useState(entry?.status ?? "PLANNING");
  const [progress, setProgress] = useState(entry?.progress ?? 0);
  const [score, setScore] = useState(entry?.score ?? 0);
  const [repeat, setRepeat] = useState(entry?.repeat ?? 0);
  const [privateEntry, setPrivateEntry] = useState(entry?.private ?? false);
  const [notes, setNotes] = useState(entry?.notes ?? "");
  const [startedAt, setStartedAt] = useState(dateToInput(entry?.started_at));
  const [completedAt, setCompletedAt] = useState(dateToInput(entry?.completed_at));
  const [saving, setSaving] = useState(false);
  const [modalError, setModalError] = useState<string | null>(null);
  const [modalSuccess, setModalSuccess] = useState<string | null>(null);
  const [updateResults, setUpdateResults] = useState<AccountUpdateResult[] | null>(null);
  const scoreConfig = scoreInputConfig(details.score_format);

  const save = async () => {
    setSaving(true);
    setModalError(null);
    setModalSuccess(null);
    setUpdateResults(null);
    const update: MediaEntryUpdate = {
      status,
      progress,
      score,
      repeat,
      private: privateEntry,
      notes,
    };
    update.started_at = startedAt ? inputToDate(startedAt) : null;
    update.completed_at = completedAt ? inputToDate(completedAt) : null;
    try {
      const targetId = canonicalId ?? details.id;
      const result = await api.bulkUpdateEntry(targetId, update);
      await onChanged();
      setUpdateResults(result.results);
      const failures = result.results.filter((item) => !item.success);
      if (failures.length === 0) {
        setModalSuccess(entry ? "Cambios guardados correctamente en todas las cuentas." : `${isManga ? "Manga" : "Anime"} añadido a tu lista.`);
      } else {
        setModalSuccess("Cambios guardados parcialmente.");
      }
    } catch (reason) {
      setModalError(errorMessage(reason, "No se pudo guardar la entrada"));
    } finally {
      setSaving(false);
    }
  };

  const remove = async () => {
    if (!entry || !window.confirm(`¿Eliminar ${details.title} de tu lista?`)) return;
    setSaving(true);
    setModalError(null);
    setModalSuccess(null);
    try {
      await api.deleteEntry(entry.id);
      await onChanged();
      setTab("info");
      setModalSuccess(`${isManga ? "Manga" : "Anime"} eliminado de tu lista.`);
    } catch (reason) {
      setModalError(errorMessage(reason, "No se pudo eliminar la entrada"));
    } finally {
      setSaving(false);
    }
  };

  const description = details.description ? new DOMParser().parseFromString(details.description, "text/html").body.textContent : null;
  const alternativeTitles = Array.from(new Set([details.title_romaji, details.title_english, details.title_native, ...details.synonyms].filter(Boolean)));

  return <div className="modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
    <section className="details-modal">
      <button className="modal-close" onClick={onClose} aria-label="Cerrar">×</button>
      <div className="detail-banner" style={details.banner_image ? { backgroundImage: `linear-gradient(0deg, #11151f 0%, transparent 75%), url(${details.banner_image})` } : undefined} />
      <div className="detail-heading">
        <div className="detail-poster" style={details.cover_image ? { backgroundImage: `url(${details.cover_image})` } : undefined} />
        <div><p className="eyebrow">{details.format ?? (isManga ? "MANGA" : "ANIME")} {details.season ? `· ${details.season} ${details.season_year ?? ""}` : ""}</p><h2>{details.title}</h2><div className="genre-list">{details.genres.map((genre) => <span key={genre}>{genre}</span>)}</div></div>
      </div>
      <div className="detail-tabs">
        <button className={tab === "info" ? "selected" : ""} onClick={() => setTab("info")}>Información</button>
        {((details.characters ?? []).length > 0 || (details.staff ?? []).length > 0) && (
          <button className={tab === "reparto" ? "selected" : ""} onClick={() => setTab("reparto")}>Reparto</button>
        )}
        {(details.recommendations ?? []).length > 0 && (
          <button className={tab === "recomendaciones" ? "selected" : ""} onClick={() => setTab("recomendaciones")}>Recomendaciones</button>
        )}
        <button className={tab === "edit" ? "selected" : ""} onClick={() => setTab("edit")}>{entry ? "Editar lista" : "Añadir a lista"}</button>
      </div>
      {modalError && <div className="modal-error">{modalError}</div>}
      {modalSuccess && <div className="modal-success">{modalSuccess}</div>}
      {updateResults && (
        <div className="update-results">
          {updateResults.map((result) => (
            <div key={`${result.provider}-${result.alias}`} className={result.success ? "update-success" : "update-failure"}>
              <span>{result.provider} · {result.alias}</span>
              <span>{result.success ? "Guardado" : result.error ?? "Falló"}</span>
            </div>
          ))}
        </div>
      )}
      {tab === "info" && <div className="detail-body">
        {description && <div className="synopsis"><h3>Sinopsis</h3><p>{description}</p></div>}
        <div className="detail-facts">
          <Fact label="Estado" value={details.status} />
          <Fact label="Origen" value={details.source} />
          {isManga ? (
            <>
              <Fact label="Capítulos" value={details.chapters} />
              <Fact label="Volúmenes" value={details.volumes} />
            </>
          ) : (
            <>
              <Fact label="Episodios" value={details.episodes} />
              <Fact label="Duración" value={details.duration ? `${details.duration} min` : null} />
            </>
          )}
          {!isManga && (
            <>
              <Fact label="Estudios" value={details.studios.join(", ")} />
              <Fact label="País" value={details.country} />
              <Fact label="Próximo episodio" value={details.next_episode ? `${details.next_episode}${details.next_airing_at ? ` · ${new Date(details.next_airing_at * 1000).toLocaleString("es")}` : ""}` : null} />
            </>
          )}
          <Fact label="Puntuación" value={details.average_score ? `${details.average_score}%` : null} />
        </div>
        {alternativeTitles.length > 1 && <div className="alternative-titles"><h3>Títulos alternativos</h3><p>{alternativeTitles.join(" · ")}</p></div>}
        {details.trailer && details.trailer.site === "youtube" && (
          <a className="external-link" href={`https://www.youtube.com/watch?v=${details.trailer.id}`} target="_blank" rel="noreferrer">Ver trailer en YouTube ↗</a>
        )}
        {(details.relations ?? []).filter(r => r.format !== "MUSIC").length > 0 && (
          <div className="detail-section">
            <h3>Obras relacionadas</h3>
            <div className="portrait-grid">
              {(details.relations ?? []).filter(r => r.format !== "MUSIC").map((rel) => (
                <button
                  key={rel.id}
                  className="portrait-card"
                  onClick={() => { onClose(); onSelect?.(rel.id, formatToMediaType(rel.format)); }}
                >
                  <div className="portrait-img" style={rel.cover_image ? { backgroundImage: `url(${rel.cover_image})` } : undefined}>
                    <span className="portrait-badge">{RELATION_TYPE_LABELS[rel.relation_type] ?? "Relacionado"}</span>
                  </div>
                  <span className="portrait-name">{rel.title}</span>
                  {rel.format && <span className="portrait-sub">{rel.format.replace(/_/g, " ")}</span>}
                </button>
              ))}
            </div>
          </div>
        )}
        {canonicalId && <TagEditor canonicalId={canonicalId} onChanged={onChanged} />}
        <a className="external-link" href={details.site_url} target="_blank" rel="noreferrer">Abrir en AniList ↗</a>
      </div>}
      {tab === "reparto" && <div className="detail-body">
        {!isManga && (details.characters ?? []).length > 0 && (
          <div className="detail-section">
            <h3>Personajes</h3>
            <div className="portrait-grid">
              {(details.characters ?? []).map((edge, i) => {
                const va = edge.voice_actors[0];
                return (
                  <div key={i} className="portrait-card">
                    <div className="portrait-img" style={edge.node.image?.medium ? { backgroundImage: `url(${edge.node.image.medium})` } : undefined}>
                      {va?.image?.medium && (
                        <div className="portrait-va-thumb" style={{ backgroundImage: `url(${va.image.medium})` }} />
                      )}
                    </div>
                    <span className="portrait-name">{edge.node.name?.full ?? "?"}</span>
                    <span className="portrait-sub">{edge.role === "MAIN" ? "Principal" : "Secundario"}</span>
                    {va?.name?.full && <span className="portrait-va">{va.name.full}</span>}
                  </div>
                );
              })}
            </div>
          </div>
        )}
        {(details.staff ?? []).length > 0 && (
          <div className="detail-section">
            <h3>Staff</h3>
            <div className="portrait-grid">
              {(details.staff ?? []).map((edge, i) => (
                <div key={i} className="portrait-card">
                  <div className="portrait-img" style={edge.node.image?.medium ? { backgroundImage: `url(${edge.node.image.medium})` } : undefined} />
                  <span className="portrait-name">{edge.node.name?.full ?? "?"}</span>
                  {edge.role && <span className="portrait-sub">{edge.role}</span>}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>}
      {tab === "recomendaciones" && <div className="detail-body">
        <div className="portrait-grid">
          {(details.recommendations ?? []).map((rec) => (
            <button
              key={rec.id}
              className="portrait-card"
              onClick={() => { onClose(); onSelect?.(rec.id, formatToMediaType(rec.format)); }}
            >
              <div className="portrait-img" style={rec.cover_image ? { backgroundImage: `url(${rec.cover_image})` } : undefined}>
                {rec.rating != null && <span className="portrait-badge">★ {rec.rating}</span>}
              </div>
              <span className="portrait-name">{rec.title}</span>
              {rec.format && <span className="portrait-sub">{rec.format.replace(/_/g, " ")}</span>}
            </button>
          ))}
        </div>
      </div>}
      {tab === "edit" && <div className="edit-entry">
        <label>Estado<select value={status} onChange={(event) => setStatus(event.target.value)}><option value="CURRENT">Viendo</option><option value="PLANNING">Planeado</option><option value="COMPLETED">Completado</option><option value="PAUSED">Pausado</option><option value="DROPPED">Abandonado</option></select></label>
        <label>Progreso<input type="number" min="0" max={isManga ? (details.chapters ?? undefined) : (details.episodes ?? undefined)} value={progress} onChange={(event) => setProgress(Number(event.target.value))} /></label>
        <label>Puntuación<input type="number" min="0" max={scoreConfig.max} step={scoreConfig.step} value={score} onChange={(event) => setScore(Number(event.target.value))} /></label>
        <label>Repeticiones<input type="number" min="0" value={repeat} onChange={(event) => setRepeat(Number(event.target.value))} /></label>
        <label>Fecha de inicio<input type="date" value={startedAt} onChange={(event) => setStartedAt(event.target.value)} /></label>
        <label>Fecha de término<input type="date" value={completedAt} onChange={(event) => setCompletedAt(event.target.value)} /></label>
        <label className="notes-field">Notas<textarea rows={4} value={notes} onChange={(event) => setNotes(event.target.value)} /></label>
        <label className="checkbox-field"><input type="checkbox" checked={privateEntry} onChange={(event) => setPrivateEntry(event.target.checked)} /> Entrada privada</label>
        <div className="edit-actions"><button className="primary" disabled={saving} onClick={() => void save()}>{saving ? "Guardando…" : entry ? "Guardar cambios" : "Añadir a la lista"}</button>{entry && <button className="danger" disabled={saving} onClick={() => void remove()}>Eliminar</button>}</div>
      </div>}
    </section>
  </div>;
}

function formatSyncAge(timestamp: number): string {
  const seconds = Math.floor((Date.now() - timestamp * 1000) / 1000);
  if (seconds < 60) return "hace un momento";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `hace ${minutes} min`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `hace ${hours} h`;
  const days = Math.floor(hours / 24);
  return `hace ${days} d`;
}

function CacheBadge({ status }: { status: CacheStatus | null }) {
  if (!status) return null;
  const labels: Record<CacheStatus, string> = {
    hit: "En caché",
    stale: "Caché vencida",
    miss: "En línea",
  };
  const stateClass = status === "stale" ? "cache-stale" : status === "hit" ? "cache-hit" : "cache-miss";
  return (
    <small className={`cache-badge ${stateClass}`} title={labels[status]}>
      <span className="cache-dot" /> {labels[status]}
    </small>
  );
}

function SyncBadge({ view, syncStatus, season }: { view: View; syncStatus: SyncStatusResponse; season: { season: string; year: number } }) {
  const status = view === "library"
    ? syncStatus.library
    : view === "activity"
      ? syncStatus.activity
      : view === "seasons"
        ? syncStatus.season
        : view === "statistics"
          ? syncStatus.statistics
          : null;
  if (status?.updated_at == null) return null;
  const label = view === "seasons" ? `Temporada ${season.season} ${season.year}` : "Datos";
  const stateClass = status.stale ? "sync-stale" : "sync-fresh";
  const stateLabel = status.stale ? "Datos cacheados" : "Datos en línea";
  return <small className={`sync-badge ${stateClass}`} title={`${label} · ${stateLabel}`}><span className="sync-dot" /> Sincronizado {formatSyncAge(status.updated_at)}</small>;
}

function Fact({ label, value }: { label: string; value: string | number | null | undefined }) {
  return <div><span>{label}</span><strong>{value ?? "Desconocido"}</strong></div>;
}

function dateToInput(date?: FuzzyDate): string {
  return date?.year && date.month && date.day ? `${date.year}-${String(date.month).padStart(2, "0")}-${String(date.day).padStart(2, "0")}` : "";
}

function inputToDate(value: string): FuzzyDate {
  const [year, month, day] = value.split("-").map(Number);
  return { year, month, day };
}

function dateNumber(date: FuzzyDate | null): number {
  return (date?.year ?? 9999) * 10_000 + (date?.month ?? 12) * 100 + (date?.day ?? 31);
}

function formatFuzzyDate(date: FuzzyDate | null): string {
  if (!date?.year) return "Fecha por anunciar";
  const month = date.month ? String(date.month).padStart(2, "0") : "??";
  const day = date.day ? String(date.day).padStart(2, "0") : "??";
  return `${date.year}-${month}-${day}`;
}

function formatCountdown(timestamp: number): string {
  const seconds = Math.max(0, timestamp - Math.floor(Date.now() / 1000));
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  if (days > 0) return `${days}d ${hours}h`;
  if (hours > 0) return `${hours}h ${minutes}m`;
  return `${minutes}m`;
}

function scoreInputConfig(format: string): { max: number; step: number } {
  if (format === "POINT_100") return { max: 100, step: 1 };
  if (format === "POINT_10_DECIMAL") return { max: 10, step: 0.1 };
  if (format === "POINT_5") return { max: 5, step: 1 };
  if (format === "POINT_3") return { max: 3, step: 1 };
  return { max: 10, step: 1 };
}

function Empty({ title, detail }: { title: string; detail?: string }) {
  return <div className="empty"><strong>{title}</strong>{detail && <span>{detail}</span>}</div>;
}
