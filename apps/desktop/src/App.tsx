import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { openUrl, openPath } from "@tauri-apps/plugin-opener";
import { api, playbackSocket, setActiveAccount, type ActiveAccount } from "./api";
import { useApp } from "./i18n";
import { displayTitle } from "./title";
import { setDiscordActivity, clearDiscordActivity } from "./discord";
import { getAutostart, setAutostart } from "./autostart";
import { listen } from "@tauri-apps/api/event";
import { isPermissionGranted, requestPermission, sendNotification } from "@tauri-apps/plugin-notification";
import { DetectorSettingsView } from "./DetectorSettingsView";
import { PlaybackHistoryView } from "./PlaybackHistoryView";
import { DiscoveryView } from "./DiscoveryView";
import { TorrentsView } from "./TorrentsView";
import { LocalLibraryView } from "./LocalLibraryView";
import type {
  AccountUpdateResult,
  ActivityItem,
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
  PendingLocalItem,
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
type View = "library" | "manga" | "now-playing" | "history" | "activity" | "seasons" | "statistics" | "discovery" | "torrents" | "settings" | "local-library";
type CacheableView = "library" | "activity" | "seasons" | "statistics" | "details";
type Season = "WINTER" | "SPRING" | "SUMMER" | "FALL";
type MediaType = "ANIME" | "MANGA";

const SEASONS: Season[] = ["WINTER", "SPRING", "SUMMER", "FALL"];

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
  preferences: true,
  preferences_editable: true,
};

const PROVIDER_LABELS: Record<string, string> = {
  anilist: "AniList",
  mal: "MyAnimeList",
};

export default function App() {
  const { t, discordRpc, discordFields } = useApp();
  const [health, setHealth] = useState<Health | null>(null);
  // The playback WebSocket effect runs once and its onmessage closure would otherwise
  // capture health=null forever, so auto-match never fires. Read it through a ref.
  const healthRef = useRef<Health | null>(health);
  healthRef.current = health;
  // Remember the last detected episode so we jump to Now Playing once per new detection,
  // not on every WebSocket message.
  const detectedSignatureRef = useRef<string | null>(null);
  // Once an episode is confirmed (auto-updated), stop re-matching it on every position tick.
  const confirmedSignatureRef = useRef<string | null>(null);
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
  const [playbackPrefs, setPlaybackPrefs] = useState<PlaybackPreferences | null>(null);
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
  const [torrentUnread, setTorrentUnread] = useState(0);
  const prevTorrentUnreadRef = useRef(0);
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
  const [detailAccount, setDetailAccount] = useState<ActiveAccount>({ provider: "anilist", alias: "default" });
  const [accountUsername, setAccountUsername] = useState<string>("");
  const [accountAvatar, setAccountAvatar] = useState<string | null>(null);
  const [displayAdult, setDisplayAdult] = useState(false);
  const [accountMenuOpen, setAccountMenuOpen] = useState(false);

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
        try {
          const { data: prefs } = await api.preferences();
          setAccountUsername(prefs.username || "");
          setAccountAvatar(prefs.avatar || null);
          setDisplayAdult(Boolean(prefs.display_adult_content));
        } catch { /* provider without preferences — keep empty */ }
      } else {
        setMedia([]);
        setCacheStatus("library", null);
        setAccountUsername("");
        setAccountAvatar(null);
        setDisplayAdult(false);
      }
    } catch (reason) {
      setError(errorMessage(reason, "No se pudo conectar al servicio local"));
    } finally {
      if (!silent) setLoading(false);
    }
  }, [setCacheStatus]);

  useEffect(() => { void load(); }, [load]);

  // Escaneo de carpetas locales al arrancar, si el usuario lo activó. Fire-and-forget.
  useEffect(() => {
    void api.getScanSettings()
      .then((s) => { if (s.scan_on_startup) void api.scanLibrary().catch(() => {}); })
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (!health?.authenticated) return;
    api.playbackPreferences().then(setPlaybackPrefs).catch(() => {});
  }, [health?.authenticated]);

  useEffect(() => {
    if (!health?.authenticated) return;
    setMedia([]);
    setManga([]);
    setMangaLoaded(false);
    void load(true);
  }, [health?.authenticated, load]);

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
    const tick = async () => {
      try {
        const r = await api.torrentUnread();
        const prev = prevTorrentUnreadRef.current;
        prevTorrentUnreadRef.current = r.count;
        setTorrentUnread(r.count);
        if (r.count > prev && r.count > 0 && "__TAURI_INTERNALS__" in window) {
          let granted = await isPermissionGranted();
          if (!granted) granted = (await requestPermission()) === "granted";
          if (granted) sendNotification({ title: t("torrents.title"), body: t("torrents.notify") });
        }
      } catch { /* ignore */ }
    };
    void tick();
    const id = window.setInterval(() => void tick(), 60_000);
    return () => window.clearInterval(id);
  }, [t]);

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
        if (!next) {
          setMatch(null);
          return;
        }
        if (!healthRef.current?.authenticated) return;
        const signature = `${next.raw_title}|${next.episode ?? ""}`;
        if (detectedSignatureRef.current !== signature) {
          detectedSignatureRef.current = signature;
          setView("now-playing");
        }
        // Already auto-confirmed this episode: keep showing it, but don't re-match every
        // position tick (no churn, no flicker).
        if (confirmedSignatureRef.current === signature) return;
        api.matchPlayback(next)
          .then((result) => {
            if (result.event_status === "ignored") {
              setCandidate(null);
              setMatch(null);
              return;
            }
            // Keep showing the matched series (incl. "confirmed") rather than blanking the
            // panel we just navigated to. Adopt the backend-sanitised candidate so the
            // displayed/RP episode respects the catalogue (movies, episode caps).
            setMatch(result);
            setCandidate(result.candidate);
            if (result.event_status === "confirmed") {
              confirmedSignatureRef.current = signature;
              void load(true); // refresh the library after an automatic update
            }
          })
          .catch(() => setMatch(null));
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

  // Discord Rich Presence: reflect the currently-playing series. The start timestamp
  // resets only when the series/episode changes, so Discord's elapsed timer is accurate.
  const discordSigRef = useRef<string | null>(null);
  const discordStartRef = useRef<number | null>(null);
  useEffect(() => {
    if (!discordRpc || !candidate) {
      discordSigRef.current = null;
      discordStartRef.current = null;
      void clearDiscordActivity();
      return;
    }
    const signature = `${candidate.raw_title}|${candidate.episode ?? ""}`;
    if (discordSigRef.current !== signature) {
      discordSigRef.current = signature;
      discordStartRef.current = Math.floor(Date.now() / 1000);
    }
    const series = match?.match?.title ?? candidate.anime_title ?? candidate.raw_title;
    const episodeText = candidate.episode ? ` · Ep ${candidate.episode}` : "";
    const providerLabel = { anilist: "AniList", mal: "MyAnimeList", kitsu: "Kitsu" }[activeAccount.provider] ?? activeAccount.provider;
    const stateText = accountUsername ? `${accountUsername} · ${providerLabel}` : providerLabel;
    void setDiscordActivity({
      details: discordFields.title ? `${series}${episodeText}`.slice(0, 128) : "",
      state: discordFields.user ? stateText.slice(0, 128) : "",
      start_timestamp: discordFields.elapsed ? (discordStartRef.current ?? undefined) : undefined,
    });
  }, [discordRpc, discordFields, candidate, match, accountUsername, activeAccount.provider]);

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
        // statistics always available: native (AniList) or derived from the local library
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
      await api.confirmPlayback(m.event_id, m.match.id, progress, m.candidate.site_identifier, m.candidate.site_adapter);
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

  const openDetails = async (
    mediaId: number,
    mediaType: "ANIME" | "MANGA" = "ANIME",
    accountOverride?: ActiveAccount,
    canonicalId?: number | null,
  ) => {
    setDetailLoading(true);
    setError(null);
    const detailSource = accountOverride ?? activeAccount;
    setDetailAccount(detailSource);
    setDetailCanonicalId(canonicalId ?? null);
    try {
      const { data, cacheStatus } = mediaType === "MANGA"
        ? await api.mangaDetails(mediaId, detailSource)
        : await api.mediaDetails(mediaId, detailSource);
      setDetails(data);
      if (data.canonical_id) setDetailCanonicalId(data.canonical_id);
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
      (details.media_type === "MANGA"
        ? api.mangaDetails(details.id, detailAccount)
        : api.mediaDetails(details.id, detailAccount)),
      load(true),
    ]);
    setDetails(updated);
    setCacheStatus("details", cacheStatus);
    setActivityLoaded(false);
    setStatisticsLoaded(false);
  };

  const quickProgress = async (item: MediaItem, nextProgress: number) => {
    const targetId = item.canonical_id ?? item.id;
    const update: MediaEntryUpdate = { progress: nextProgress };
    if (item.episodes && nextProgress >= item.episodes) update.status = "COMPLETED";
    else if (item.status === "PLANNING") update.status = "CURRENT";
    // optimistic: patch the row immediately so the count moves without waiting on a refetch
    setMedia((current) => current.map((m) =>
      m.id === item.id ? { ...m, progress: nextProgress, status: update.status ?? m.status } : m));
    try {
      await api.bulkUpdateEntry(targetId, update);
      await load(true);
    } catch (reason) {
      setError(errorMessage(reason, "No se pudo actualizar el progreso"));
      await load(true);
    }
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
            "library",
            ...(capabilities.manga      ? ["manga"]    : []),
            "now-playing",
            "history",
            ...(capabilities.activity   ? ["activity"] : []),
            ...(capabilities.seasons    ? ["seasons"]  : []),
            "statistics",
            "discovery",
            "torrents",
            "settings",
          ] as View[]).map((key) => (
            <button key={key} className={view === key ? "active" : ""} onClick={() => setView(key)}>
              {t(`nav.${key}`)}
              {key === "now-playing" && candidate && <span className="nav-dot" />}
              {key === "torrents" && torrentUnread > 0 && <span className="nav-badge">{torrentUnread}</span>}
            </button>
          ))}
        </nav>
        <div className="account-widget">
          <button
            className="account-avatar-btn"
            onClick={() => setAccountMenuOpen((prev) => !prev)}
            title={accountUsername || activeAccount.provider}
          >
            {accountAvatar
              ? <img src={accountAvatar} alt="" className="account-avatar-img" />
              : <span className="account-avatar-initials">{(accountUsername || activeAccount.provider)[0].toUpperCase()}</span>
            }
            <i className={health ? "online" : "offline"} />
          </button>
          <div className="account-info" onClick={() => setAccountMenuOpen((prev) => !prev)}>
            <strong>{accountUsername || activeAccount.alias}</strong>
            <small>{{ anilist: "AniList", mal: "MyAnimeList", kitsu: "Kitsu" }[activeAccount.provider] ?? activeAccount.provider}</small>
          </div>
          {accountMenuOpen && (
            <div className="account-dropdown">
              <button onClick={() => { setAccountMenuOpen(false); void toggleDetection(); }}>
                {detectionPaused ? t("account.resumeDetection") : t("account.pauseDetection")}
              </button>
              <button onClick={() => { setAccountMenuOpen(false); setView("settings"); }}>
                {t("account.settings")}
              </button>
              <button className="danger" onClick={() => { setAccountMenuOpen(false); void clearLocalData(); }}>
                {t("account.logout")}
              </button>
            </div>
          )}
        </div>
      </aside>

      <main>
        <header>
          <div>
            <p className="eyebrow">{t(`view.${view}.eyebrow`)}</p>
            <h1>{t(`view.${view}.title`)}</h1>
            {syncStatus && <SyncBadge view={view} syncStatus={syncStatus} season={season} />}
          {viewCacheStatus[view as CacheableView] && (
            <CacheBadge status={viewCacheStatus[view as CacheableView]} />
          )}
          </div>
        </header>

        {error && (
          <div className="error">
            <strong>{t("common.error.generic")}</strong><span>{error}</span>
            <button onClick={() => view === "library" ? void load() : setView("library")}>{t("common.back")}</button>
          </div>
        )}

        {!health?.authenticated && view !== "settings" ? (
          <Empty title={t("common.connectAccount")} detail={t("common.connectAccount.detail")} />
        ) : view === "library" ? (
          <LibraryView items={media} filter={filter} query={query} loading={loading} setFilter={setFilter} setQuery={setQuery} onProgress={quickProgress} onSelect={(item) => void openDetails(item.id, "ANIME", item.provider && item.account_alias ? { provider: item.provider, alias: item.account_alias } : activeAccount, item.canonical_id)} />
        ) : view === "manga" ? (
          <MangaLibraryView items={manga} loading={sectionLoading && !mangaLoaded} onSelect={(item) => void openDetails(item.id, "MANGA", item.provider && item.account_alias ? { provider: item.provider, alias: item.account_alias } : activeAccount, item.canonical_id)} onRefresh={() => { setMangaLoaded(false); void loadManga(); }} />
        ) : view === "now-playing" ? (
          <NowPlayingView candidate={candidate} match={match} prefs={playbackPrefs} onIgnore={() => void ignorePlayback()} onUndo={() => void undoPlayback()} onSelect={openDetails} onCorrected={async (next) => { setMatch(next); if (next.match) { await confirmMatch(next); } }} onSeeMore={() => setView("local-library")} />
        ) : view === "history" ? (
          <PlaybackHistoryView refreshKey={historyVersion} onSelect={openDetails} onRefresh={() => setHistoryVersion((v) => v + 1)} />
        ) : view === "discovery" ? (
          <DiscoveryView onSelect={(id, mediaType) => void openDetails(id, mediaType)} provider={activeAccount.provider} displayAdult={displayAdult} />
        ) : view === "settings" ? (
          <DetectorSettingsView
            authenticated={Boolean(health?.authenticated)}
            activeAccount={activeAccount}
            capabilities={capabilities}
            onSync={forceSync}
            onPreferencesChanged={refreshAfterPreferences}
            onLogout={logout}
            onConnectAccount={connectAccount}
            onAccountChanged={changeAccount}
            autostart={autostart}
            onToggleAutostart={toggleAutostart}
          />
        ) : view === "torrents" ? (
          <TorrentsView />
        ) : view === "local-library" ? (
          <LocalLibraryView onBack={() => setView("now-playing")} />
        ) : sectionLoading ? (
          <Empty title={t("common.loading")} />
        ) : view === "activity" ? (
          <ActivityView items={activity} hasMore={activityHasMore} loadingMore={activityLoadingMore} onLoadMore={loadMoreActivity} onSelect={openDetails} />
        ) : view === "seasons" ? (
          <SeasonsView items={seasonMedia} season={season} onMove={changeSeason} onChange={setSeasonWithReset} onSelect={openDetails} libraryMap={libraryMap} />
        ) : (
          <StatisticsView statistics={statistics} onExport={() => void handleStatisticsExport()} />
        )}
      </main>
      {detailLoading && <div className="modal-backdrop"><div className="modal-loading">{t("common.loadingInfo")}</div></div>}
      {details && <DetailsModal details={details} canonicalId={detailCanonicalId} mediaType={details.media_type === "MANGA" ? "MANGA" : "ANIME"} detailAccount={detailAccount} onClose={() => setDetails(null)} onChanged={refreshDetails} onSelect={(id, type) => { setDetails(null); void openDetails(id, type); }} />}
    </div>
  );
}

// Provider list statuses (vs. airing statuses like RELEASING/FINISHED) — marks a match
// as already on the user's list.
const PLAYBACK_LIST_STATUSES = ["CURRENT", "PLANNING", "COMPLETED", "DROPPED", "PAUSED", "REPEATING"];

type SearchScope = "library" | "global";

type CombinedResult =
  | { source: "library"; item: MediaItem }
  | { source: "global"; item: SearchResult };

function NowPlayingView({ candidate, match, prefs, onIgnore, onUndo, onSelect, onCorrected, onSeeMore }: {
  candidate: PlaybackCandidate | null;
  match: PlaybackMatchResponse | null;
  prefs: PlaybackPreferences | null;
  onIgnore: () => void;
  onUndo: () => void;
  onSelect: (id: number) => void;
  onCorrected: (match: PlaybackMatchResponse) => Promise<void> | void;
  onSeeMore?: () => void;
}) {
  const { t } = useApp();
  const [correcting, setCorrecting] = useState(false);
  const [dismissed, setDismissed] = useState(false);
  const [query, setQuery] = useState("");
  const [combinedResults, setCombinedResults] = useState<CombinedResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [searched, setSearched] = useState(false);
  const [adding, setAdding] = useState<{ id: number; status: string } | null>(null);
  const [justConfirmed, setJustConfirmed] = useState(false);
  const [countdown, setCountdown] = useState<number | null>(null);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const defaultQuery = (match?.candidate.anime_title ?? candidate?.anime_title ?? candidate?.raw_title ?? "").trim();

  useEffect(() => {
    setCorrecting(false);
    setDismissed(false);
    setQuery(defaultQuery);
    setCombinedResults([]);
    setSearched(false);
    setAdding(null);
    setJustConfirmed(false);
    setSearchError(null);
    setActionError(null);
  }, [candidate?.raw_title, defaultQuery]);

  // No suggested match → open the search automatically (the search effect below runs it),
  // unless the user explicitly cancelled it for this candidate.
  useEffect(() => {
    if (candidate && match && !match.match && !correcting && !dismissed) setCorrecting(true);
  }, [candidate, match, correcting, dismissed]);

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

  // Live countdown to the automatic save: only when a tracked series will actually
  // auto-confirm (seconds policy, on the list, confident enough) and is playing.
  useEffect(() => {
    const m = match?.match;
    const willAutoSave = !!m
      && match?.event_status === "pending"
      && !justConfirmed
      && !!prefs?.auto_confirm
      && prefs.progress_policy === "seconds"
      && PLAYBACK_LIST_STATUSES.includes(m.status)
      && m.status !== "COMPLETED"  // a finished series waits for an explicit rewatch
      && match.match_score >= prefs.confidence_threshold;
    if (!willAutoSave || candidate?.paused || candidate?.position_seconds == null) {
      setCountdown(null);
      return;
    }
    const anchorPos = candidate.position_seconds;
    const anchorTime = Date.now();
    const threshold = prefs!.progress_seconds;
    const tick = () => {
      const pos = anchorPos + (Date.now() - anchorTime) / 1000;
      setCountdown(Math.max(0, Math.ceil(threshold - pos)));
    };
    tick();
    const id = window.setInterval(tick, 500);
    return () => window.clearInterval(id);
  }, [match, prefs, candidate?.position_seconds, candidate?.paused, justConfirmed]);

  const applyResult = async (mediaId: number, source: "library" | "global", status?: string) => {
    if (!candidate) return;
    setActionError(null);
    if (source === "global" && status) {
      setAdding({ id: mediaId, status });
    }
    try {
      // The add (remote) and the correction (local) are independent — fire together.
      await Promise.all([
        source === "global" && status ? api.editEntry(mediaId, { status, progress: 0 }) : Promise.resolve(),
        api.createCorrection(candidate.raw_title, mediaId, candidate.anime_title, candidate.site_identifier, candidate.site_adapter),
      ]);
      const corrected = await api.matchPlayback(candidate);
      await onCorrected(corrected);
      setCorrecting(false);
    } catch (reason) {
      setActionError(reason instanceof Error ? reason.message : "No se pudo aplicar la corrección");
    } finally {
      setAdding(null);
    }
  };

  // Re-watching a completed series: flip it to REPEATING starting just before the current
  // episode, then re-match so normal tracking resumes (the backend bumps the rewatch
  // counter and sets it back to Completed on the final episode).
  const startRewatch = async () => {
    if (!candidate || !match?.match) return;
    setActionError(null);
    try {
      await api.editEntry(match.match.id, { status: "REPEATING", progress: Math.max(0, (candidate.episode ?? 1) - 1) });
      const next = await api.matchPlayback(candidate);
      await onCorrected(next);
    } catch (reason) {
      setActionError(reason instanceof Error ? reason.message : "No se pudo iniciar el rewatch");
    }
  };

  if (!candidate) {
    return <div className="now-playing-view">
      <PendingLocalReminder onSelect={onSelect} onSeeMore={onSeeMore} />
      <Empty title={t("np.none")} detail={t("np.none.detail")} />
    </div>;
  }
  const confidence = Math.round(candidate.confidence * 100);
  const season = candidate.season ? `T${candidate.season} · ` : "";
  const episodeType = candidate.episode_type && candidate.episode_type !== "regular"
    ? `${candidate.episode_type.toUpperCase()} `
    : "";
  const sourceLabel = candidate.source === "active-window" ? t("np.activeWindow") : candidate.source === "media-window" ? t("np.playerSource") : candidate.source;
  const matchScore = match ? Math.round(match.match_score * 100) : 0;
  const hasCorrection = match && match.match_score >= 0.99;
  // A not-on-list match carries an airing status (FINISHED/RELEASING/…); a list entry
  // carries one of these. Drives the add-vs-confirm label.
  const onList = match?.match ? PLAYBACK_LIST_STATUSES.includes(match.match.status) : false;
  // Already tracked this session (confirmed by dedup/auto-confirm, or just added) → no button.
  const alreadyTracked = match?.event_status === "confirmed" || justConfirmed;
  // A finished series being watched again: offer rewatch instead of silently re-saving.
  const isCompleted = match?.match?.status === "COMPLETED";
  const isRepeating = match?.match?.status === "REPEATING";

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
  const isMovie = match?.match ? (match.match.format === "MOVIE" || match.match.episodes === 1) : false;
  return (
    <section className="now-playing-view">
      <PendingLocalReminder onSelect={onSelect} onSeeMore={onSeeMore} />
      <div className="detection-card">
        <div className="pulse" />
        <div>
          <small>{t("np.source")}: {sourceLabel} · {t("np.confidence")} {confidence}%{candidate.paused ? ` · ${t("np.paused")}` : ""}{candidate.finished ? ` · ${t("np.finished")}` : ""}</small>
          <strong>{candidate.anime_title ?? candidate.raw_title}</strong>
          <span>{isMovie ? t("np.movie") : candidate.episode ? `${season}${episodeType}${t("np.episode")} ${candidate.episode}` : t("np.episode.unknown")}</span>
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
          <h3>{t("np.correct.title")}</h3>
          <p>{t("np.correct.desc")}</p>
          <div className="correction-search">
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder={t("np.correct.placeholder")}
              onKeyDown={(event) => event.key === "Enter" && void search(query)}
            />
            <button onClick={() => void search(query)} disabled={searching || query.trim().length < 2}>{searching ? t("np.searching") : t("np.search")}</button>
          </div>
          {searchError && <p className="correction-empty" style={{ color: "#eaa9b7" }}>{searchError}</p>}
          {actionError && <p className="correction-empty" style={{ color: "#eaa9b7" }}>{actionError}</p>}
          {searching ? (
            <p className="correction-empty">{t("np.searching")}</p>
          ) : combinedResults.length > 0 ? (
            <div className="correction-results">
              {combinedResults.map((entry) => {
                const item = entry.item;
                const isLibrary = entry.source === "library";
                const libraryItem = isLibrary ? item as MediaItem : null;
                return (
                  <div key={item.id} className="correction-item">
                    <div className="poster clickable" title={t("np.viewEntry")} style={item.cover_image ? { backgroundImage: `url(${item.cover_image})` } : undefined} onClick={() => onSelect(item.id)}>
                      {libraryItem && <span className="season-library-badge">{t(`badge.${libraryItem.status}`)}</span>}
                    </div>
                    <span className="clickable" title={t("np.viewEntry")} onClick={() => onSelect(item.id)}>{item.title}</span>
                    <small>{item.format ?? t("common.anime")}{(item as SearchResult).average_score ? ` · ${(item as SearchResult).average_score}%` : ""}</small>
                    {isLibrary ? (
                      <button className="primary small" onClick={() => void applyResult(item.id, "library")}>{t("np.useThis")}</button>
                    ) : (
                      <div className="correction-add-actions">
                        <button className="primary small" disabled={adding?.id === item.id && adding?.status === "CURRENT"} onClick={() => void applyResult(item.id, "global", "CURRENT")}>{t("np.addWatching")}</button>
                        <button className="small" disabled={adding?.id === item.id && adding?.status === "PLANNING"} onClick={() => void applyResult(item.id, "global", "PLANNING")}>{t("np.addPlanning")}</button>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          ) : searched && query.trim().length >= 2 ? (
            <p className="correction-empty">{t("np.notFoundPre")}{query}{t("np.notFoundPost")}</p>
          ) : null}
          <div className="match-actions">
            <button onClick={() => { setCorrecting(false); setDismissed(true); }}>{t("np.cancel")}</button>
          </div>
        </div>
      ) : match?.match ? (
        <div className="match-card">
          <h3>{t("np.suggestedMatch")} ({matchScore}%){hasCorrection && <small> · {t("np.manuallyCorrected")}</small>}</h3>
          <article className="now-playing-match-card clickable" onClick={() => onSelect(match.match!.id)}>
            <div className="poster" style={match.match.cover_image ? { backgroundImage: `url(${match.match.cover_image})` } : undefined} />
            <div className="now-playing-match-info">
              <strong title={match.match.title}>{match.match.title}</strong>
              <span>{match.match.format?.replace("_", " ")}{match.match.year ? ` · ${match.match.year}` : ""}</span>
              <span>{match.match.progress} / {match.match.episodes ?? "?"} {t("np.episodes")}</span>
            </div>
          </article>
          <div className="match-actions">
            {alreadyTracked ? (
              <span className="np-tracked">✓ {t("np.tracked")}</span>
            ) : isCompleted ? (
              // Finished series watched again → offer a rewatch instead of re-saving.
              <>
                <span className="np-tracked">{t("np.completed")}</span>
                <button className="primary" onClick={() => void startRewatch()}>↻ {t("np.startRewatch")}</button>
              </>
            ) : onList ? (
              // Already on the list → auto-updates ~Ns in; show the live countdown.
              <span className="np-tracked np-auto">
                {isRepeating ? `↻ ${t("np.rewatching")} · ` : ""}
                {countdown != null
                  ? (countdown > 0 ? `${t("np.savingIn")} ${countdown}s` : t("np.saving"))
                  : t("np.autoSaving")}
              </span>
            ) : (
              <button className="primary" onClick={async () => { await onCorrected(match); setJustConfirmed(true); }}>
                {t("np.addWatching")}
              </button>
            )}
            <button onClick={() => setCorrecting(true)}>{t("np.correct")}</button>
            <button onClick={onIgnore}>{t("np.ignore")}</button>
            <button onClick={onUndo}>{t("np.undoLast")}</button>
          </div>
        </div>
      ) : (
        <div className="match-card">
          <h3>{t("np.noMatch")}</h3>
          <p>{t("np.noMatch.desc")}</p>
          <div className="match-actions">
            <button onClick={() => setCorrecting(true)}>{t("np.search")}</button>
            <button onClick={onIgnore}>{t("np.ignore")}</button>
            <button onClick={onUndo}>{t("np.undoLast")}</button>
          </div>
        </div>
      )}

      {!correcting && (match?.suggestions?.length ?? 0) > 0 && (
        <div className="match-card suggestions-card">
          <h3>{t("np.otherOptions")}</h3>
          <div className="np-suggestions">
            {match!.suggestions.map((item) => (
              <button key={item.id} className="np-suggestion" onClick={() => void applyResult(item.id, "library")} title={item.title}>
                <span className="poster" style={item.cover_image ? { backgroundImage: `url(${item.cover_image})` } : undefined} />
                <span className="np-suggestion-title">{item.title}</span>
                <small>{item.progress}/{item.episodes ?? "?"}</small>
              </button>
            ))}
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
  const { t } = useApp();
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
      {onRefresh && <button className="small" onClick={onRefresh}>{t("common.reload")}</button>}
    </section>
    <div className="season-filters library-filters">
      <select value={sort} onChange={(event) => setSort(event.target.value as SortKey)}>
        <option value="TITLE">{t("lib.sort.title")}</option>
        <option value="PROGRESS_DESC">{t("lib.sort.progress")}</option>
        <option value="SCORE_DESC">{t("lib.sort.score")}</option>
        <option value="UPDATED_DESC">{t("lib.sort.updated")}</option>
      </select>
      <select value={formatFilter} onChange={(event) => setFormatFilter(event.target.value)}>
        <option value="ALL">{t("lib.format.all")}</option>
        {formats.map((format) => <option key={format} value={format}>{formatLabel(format)}</option>)}
      </select>
      {children}
    </div>
  </>;
}

type LibraryLayout = "grid" | "list";

function LibraryView({ items, filter, query, loading, setFilter, setQuery, onSelect, onProgress }: {
  items: MediaItem[]; filter: Filter; query: string; loading: boolean;
  setFilter: (filter: Filter) => void; setQuery: (query: string) => void; onSelect: (item: MediaItem) => void;
  onProgress: (item: MediaItem, nextProgress: number) => Promise<void>;
}) {
  const { t, titleLanguage } = useApp();
  const [sort, setSort] = useState<SortKey>("TITLE");
  const [layout, setLayout] = useState<LibraryLayout>(() => (localStorage.getItem("library-layout") as LibraryLayout) || "grid");
  const setLayoutPersist = (next: LibraryLayout) => { setLayout(next); localStorage.setItem("library-layout", next); };
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
    const result = items
      .map((item) => ({ ...item, title: displayTitle(item, titleLanguage) }))
      .filter(
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
  }, [filter, formatFilter, genreFilter, items, query, sort, tagFilter, yearFilter, titleLanguage]);

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
      statusLabels={{ CURRENT: t("filter.watching"), PLANNING: t("filter.planning"), COMPLETED: t("filter.completed"), PAUSED: t("filter.paused"), DROPPED: t("filter.dropped"), ALL: t("filter.all") }}
      searchPlaceholder={t("lib.search.anime")}
    >
      <select value={yearFilter} onChange={(event) => setYearFilter(event.target.value)}>
        <option value="ALL">{t("lib.year.all")}</option>
        {years.map((year) => <option key={year} value={String(year)}>{year}</option>)}
      </select>
      <select value={genreFilter} onChange={(event) => setGenreFilter(event.target.value)}>
        <option value="ALL">{t("lib.genre.all")}</option>
        {genres.map((genre) => <option key={genre} value={genre}>{genre}</option>)}
      </select>
      <select value={tagFilter} onChange={(event) => setTagFilter(event.target.value)}>
        <option value="ALL">{t("lib.tag.all")}</option>
        {tags.map((tag) => <option key={tag} value={tag}>{tag}</option>)}
      </select>
      <div className="layout-toggle">
        <button className={layout === "grid" ? "active" : ""} title={t("lib.layout.grid")} onClick={() => setLayoutPersist("grid")}>▦</button>
        <button className={layout === "list" ? "active" : ""} title={t("lib.layout.list")} onClick={() => setLayoutPersist("list")}>☰</button>
      </div>
    </LibraryToolbar>
    {loading ? <Empty title={t("lib.loading.anime")} /> : visible.length === 0 ? <Empty title={t("common.noResults")} detail={t("common.tryOtherFilter")} /> : layout === "grid" ? (
      <section className="media-grid">{visible.map((item) => <MediaCard key={item.id} item={item} mediaType="ANIME" onSelect={onSelect} />)}</section>
    ) : (
      <section className="media-list">{visible.map((item) => <MediaListRow key={item.id} item={item} onSelect={onSelect} onProgress={onProgress} />)}</section>
    )}
  </>;
}

function MediaListRow({ item, onSelect, onProgress }: {
  item: MediaItem; onSelect: (item: MediaItem) => void; onProgress: (item: MediaItem, nextProgress: number) => Promise<void>;
}) {
  const { t } = useApp();
  const [busy, setBusy] = useState(false);
  const total = item.episodes ?? null;
  const atMax = total != null && item.progress >= total;
  const bump = async () => {
    if (busy || atMax) return;
    setBusy(true);
    try { await onProgress(item, item.progress + 1); } finally { setBusy(false); }
  };
  return (
    <article className="media-row" onClick={() => onSelect(item)}>
      {item.cover_image ? <img src={item.cover_image} alt="" loading="lazy" /> : <div className="media-row-noimg" />}
      <div className="media-row-main">
        <strong>{item.title}</strong>
        <small>{[item.format, item.year ? String(item.year) : null].filter(Boolean).join(" · ")}</small>
      </div>
      <span className={`media-row-badge status-${item.status.toLowerCase()}`}>{t(`badge.${item.status}`)}</span>
      <span className="media-row-progress">{item.progress}{total != null ? ` / ${total}` : ""}</span>
      <span className="media-row-score">{item.score ? `★ ${Math.round(item.score) / 10}` : "—"}</span>
      <div className="media-row-actions" onClick={(event) => event.stopPropagation()}>
        <button className="row-plus" disabled={busy || atMax} title={atMax ? t("lib.row.completed") : t("lib.row.addEpisode")} onClick={() => void bump()}>+1</button>
        <button className="row-edit" title={t("lib.row.edit")} onClick={() => onSelect(item)}>✎</button>
      </div>
    </article>
  );
}

function MangaLibraryView({ items, loading, onSelect, onRefresh }: {
  items: MediaItem[]; loading: boolean; onSelect: (item: MediaItem) => void; onRefresh: () => void;
}) {
  const { t, titleLanguage } = useApp();
  const [filter, setFilter] = useState<Filter>("CURRENT");
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<SortKey>("TITLE");
  const [formatFilter, setFormatFilter] = useState<string>("ALL");

  const counts = Object.fromEntries((["CURRENT", "PLANNING", "COMPLETED", "PAUSED", "DROPPED"] as Filter[]).map((status) => [status, items.filter((item) => item.status === status).length])) as Record<Filter, number> & { total: number };
  counts.total = items.length;
  const formats = useMemo(() => Array.from(new Set(items.map((item) => item.format).filter((format): format is string => Boolean(format)))).sort(), [items]);
  const visible = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase();
    const result = items
      .map((item) => ({ ...item, title: displayTitle(item, titleLanguage) }))
      .filter(
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
  }, [filter, formatFilter, items, query, sort, titleLanguage]);

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
      statusLabels={{ CURRENT: t("filter.reading"), PLANNING: t("filter.planning"), COMPLETED: t("filter.completed"), PAUSED: t("filter.paused"), DROPPED: t("filter.dropped"), ALL: t("filter.all") }}
      searchPlaceholder={t("lib.search.manga")}
      onRefresh={onRefresh}
    />
    {loading ? <Empty title={t("lib.loading.manga")} /> : visible.length === 0 ? <Empty title={t("common.noResults")} detail={t("common.tryOtherFilter")} /> : (
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
  const { t } = useApp();
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

  // ponytail: group consecutive same-media items; expand if per-episode detail is needed
  const grouped = useMemo(() => visible.reduce<(ActivityItem & { count: number; minProg: number | null; maxProg: number | null })[]>(
    (acc, item) => {
      const last = acc.at(-1);
      const prog = item.progress !== null ? parseInt(item.progress) : null;
      if (last?.media_id === item.media_id) {
        last.count++;
        if (prog !== null && !isNaN(prog)) {
          last.minProg = last.minProg === null ? prog : Math.min(last.minProg, prog);
          last.maxProg = last.maxProg === null ? prog : Math.max(last.maxProg, prog);
        }
      } else {
        acc.push({ ...item, count: 1, minProg: prog !== null && !isNaN(prog) ? prog : null, maxProg: prog !== null && !isNaN(prog) ? prog : null });
      }
      return acc;
    },
    []
  ), [visible]);

  if (!items.length) return <Empty title={t("activity.none")} />;
  return <>
    <div className="season-filters">
      <select value={type} onChange={(event) => setType(event.target.value)}>
        <option value="ALL">{t("activity.type.all")}</option>
        <option value="PROGRESS">{t("activity.type.progress")}</option>
        <option value="STATUS">{t("activity.type.status")}</option>
      </select>
      <select value={status} onChange={(event) => setStatus(event.target.value)}>
        <option value="ALL">{t("activity.status.all")}</option>
        {statuses.map((value) => <option key={value} value={value}>{value}</option>)}
      </select>
      <input type="date" value={dateFrom} onChange={(event) => setDateFrom(event.target.value)} aria-label={t("activity.from")} />
    </div>
    {grouped.length === 0 ? <Empty title={t("common.noResults")} detail={t("common.tryOtherFilter")} /> : <section className="activity-list">{grouped.map((item) => {
      const progLabel = item.maxProg !== null
        ? item.minProg !== item.maxProg ? `${t("activity.ep")} ${item.minProg}–${item.maxProg}` : `${t("activity.ep")} ${item.maxProg}`
        : item.status;
      return (
        <article className="activity-row clickable" key={item.id} onClick={() => onSelect(item.media_id)}>
          <div className="activity-cover" style={item.cover_image ? { backgroundImage: `url(${item.cover_image})` } : undefined} />
          <div><strong>{item.title}</strong><span>{progLabel}{item.count > 1 ? ` · ×${item.count}` : ""}</span></div>
          <time>{new Intl.DateTimeFormat("es", { dateStyle: "medium", timeStyle: "short" }).format(item.created_at * 1000)}</time>
        </article>
      );
    })}</section>}
    {hasMore && <button className="primary load-more" disabled={loadingMore} onClick={() => void onLoadMore()}>{loadingMore ? t("common.loading") : t("activity.loadMore")}</button>}
  </>;
}

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
  const { t } = useApp();
  const labels: Record<Season, string> = { WINTER: t("season.winter"), SPRING: t("season.spring"), SUMMER: t("season.summer"), FALL: t("season.fall") };
  const groupToken: Record<SeasonFormatKey, string> = { TV: "tv", TV_SHORT: "tvshort", ONA_OVA_SPECIAL: "special", MOVIE: "movies", OTHER: "other" };
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
    <div className="season-filters"><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder={t("seasons.search")} /><select value={format} onChange={(event) => setFormat(event.target.value)}><option value="ALL">{t("lib.format.all")}</option><option value="TV">TV</option><option value="TV_SHORT">TV Short</option><option value="ONA">ONA</option><option value="OVA">OVA</option><option value="SPECIAL">{t("seasons.fmt.special")}</option><option value="MOVIE">{t("seasons.fmt.movie")}</option></select><select value={sort} onChange={(event) => setSort(event.target.value)}><option value="POPULARITY">{t("seasons.sort.popularity")}</option><option value="TITLE">{t("seasons.sort.title")}</option><option value="DATE">{t("seasons.sort.date")}</option><option value="SCORE">{t("seasons.sort.score")}</option></select></div>
    {!visibleItems.length ? <Empty title={t("seasons.empty")} /> : groups.map((group) => {
      const groupItems = visibleItems.filter((item) => seasonFormatKey(item.format) === group.key);
      if (!groupItems.length) return null;
      return (
        <section key={group.key} className="season-group">
          <h3 className="season-group-title">{t(`seasons.group.${groupToken[group.key]}`)}</h3>
          <section className="media-grid">{groupItems.map((item) => {
            const libraryEntry = libraryMap.get(item.id);
            return (
              <article className="media-card clickable" key={item.id} onClick={() => onSelect(item.id)}>
                <div className="poster" style={item.cover_image ? { backgroundImage: `url(${item.cover_image})` } : undefined}>
                  {libraryEntry && <span className="season-library-badge">{t(`badge.${libraryEntry.status}`)}</span>}
                </div>
                <div className="media-info"><strong title={item.title}>{item.title}</strong><span className="season-studio">{item.studios.slice(0, 2).join(", ") || t("seasons.studioUnknown")}</span><span>{item.format ?? t("common.anime")} · {item.episodes ?? "?"} {t("seasons.episodes")} · {formatFuzzyDate(item.start_date)}</span><span>{item.average_score ? `${item.average_score}%` : t("seasons.noScore")}{item.next_airing_at && item.next_airing_at > Date.now() / 1000 ? ` · Ep ${item.next_episode ?? "?"} ${t("seasons.epIn")} ${formatCountdown(item.next_airing_at)}` : ""}</span></div>
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
  const { t } = useApp();
  const [tab, setTab] = useState<"ANIME" | "MANGA">("ANIME");

  if (!statistics) return <Empty title={t("stats.none")} />;
  const stats = tab === "ANIME" ? statistics.anime : statistics.manga;
  const isAnime = tab === "ANIME";

  const byStatus = (label: string) => stats.statuses.find((s) => s.label === label)?.count ?? 0;
  const completed = byStatus("COMPLETED");
  const inProgress = byStatus("CURRENT") + byStatus("REPEATING");
  const planned = byStatus("PLANNING");
  const completionRate = stats.count ? Math.round((completed / stats.count) * 100) : 0;
  const hours = Math.round(stats.minutes_watched / 60);
  const days = stats.minutes_watched / 60 / 24;
  const perTitle = stats.count ? Math.round(stats.episodes_watched / stats.count) : 0;

  return (
    <>
      <div className="stat-tabs">
        <button className={tab === "ANIME" ? "active" : ""} onClick={() => setTab("ANIME")}>{t("stats.tab.anime")}</button>
        <button className={tab === "MANGA" ? "active" : ""} onClick={() => setTab("MANGA")}>{t("stats.tab.manga")}</button>
      </div>
      {stats.count === 0 ? <Empty title={isAnime ? t("stats.empty.anime") : t("stats.empty.manga")} /> : <>
      <section className="stat-hero">
        <StatHero label={isAnime ? t("stats.hero.animeCount") : t("stats.hero.mangaCount")} value={stats.count.toLocaleString("es")} accent="purple" sub={`${completionRate}% ${t("stats.completedPct")}`} />
        <StatHero label={isAnime ? t("stats.hero.episodes") : t("stats.hero.chapters")} value={stats.episodes_watched.toLocaleString("es")} accent="green" sub={perTitle ? `≈ ${perTitle} ${t("stats.perTitle")}` : undefined} />
        {isAnime && hours > 0
          ? <StatHero label={t("stats.watchTime")} value={`${hours.toLocaleString("es")} h`} accent="blue" sub={days >= 1 ? `${days.toFixed(1)} ${t("stats.days")}` : undefined} />
          : <StatHero label={t("stats.inProgress")} value={inProgress.toLocaleString("es")} accent="blue" sub={planned ? `${planned} ${t("stats.planned")}` : undefined} />}
        <StatHero label={t("stats.meanScore")} value={stats.mean_score > 0 ? stats.mean_score.toFixed(1) : "—"} accent="gold" sub={stats.mean_score > 0 ? t("stats.outOf100") : t("stats.unscored")} />
      </section>
      <section className="stat-mini">
        <StatMini label={t("stats.completed")} value={completed} />
        <StatMini label={t("stats.inProgress")} value={inProgress} />
        <StatMini label={t("filter.planning")} value={planned} />
        <StatMini label={t("stats.paused")} value={byStatus("PAUSED")} />
        <StatMini label={t("stats.dropped")} value={byStatus("DROPPED")} />
      </section>
      <section className="stat-panels">
        <StatBars title={t("stats.genres")} items={stats.genres} />
        <StatBars title={t("stats.formats")} items={stats.formats} />
        <StatBars title={t("stats.years")} items={stats.release_years} />
        {stats.studios.length > 0 && <StatBars title={t("stats.studios")} items={stats.studios} />}
        {stats.countries.length > 0 && <StatBars title={t("stats.countries")} items={stats.countries} />}
      </section>
      <section className="stat-export">
        <button onClick={onExport}>{t("stats.export")}</button>
      </section>
      </>}
    </>
  );
}

function StatHero({ label, value, sub, accent }: { label: string; value: string; sub?: string; accent: string }) {
  return (
    <article className={`stat-hero-card accent-${accent}`}>
      <span className="stat-hero-label">{label}</span>
      <strong className="stat-hero-value">{value}</strong>
      {sub && <span className="stat-hero-sub">{sub}</span>}
    </article>
  );
}

function StatMini({ label, value }: { label: string; value: number }) {
  return (
    <article className="stat-mini-card">
      <strong>{value.toLocaleString("es")}</strong>
      <span>{label}</span>
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

function MediaCard({ item, mediaType, onSelect }: { item: MediaItem; mediaType: MediaType; onSelect: (item: MediaItem) => void }) {
  const total = mediaType === "MANGA" ? (item.chapters ?? 0) : (item.episodes ?? 0);
  const percentage = total ? Math.min(100, item.progress / total * 100) : 0;
  const progressLabel = mediaType === "MANGA"
    ? `${item.progress} / ${item.chapters ?? "?"} capítulos${item.volumes ? ` · ${item.volumes} vol.` : ""}`
    : `${item.progress} / ${item.episodes ?? "?"} episodios`;
  return <article className="media-card clickable" onClick={() => onSelect(item)}>
    <div className="poster" style={item.cover_image ? { backgroundImage: `url(${item.cover_image})` } : undefined} />
    <div className="media-info"><strong title={item.title}>{item.title}</strong><span>{progressLabel}</span><div className="progress"><i style={{ width: `${percentage}%` }} /></div>{(item.tags ?? []).length > 0 && <div className="media-tags">{item.tags?.map((tag) => <span key={tag}>{tag}</span>)}</div>}</div>
  </article>;
}

function TagEditor({ canonicalId, onChanged }: { canonicalId: number; onChanged?: () => void }) {
  const { t } = useApp();
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
      <h4>{t("tags.title")}</h4>
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
          placeholder={t("tags.placeholder")}
          disabled={loading}
        />
        <button onClick={() => void add()} disabled={loading || !newTag.trim()}>{t("tags.add")}</button>
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

function DetailsModal({ details, canonicalId, mediaType, detailAccount, onClose, onChanged, onSelect }: {
  details: MediaDetails;
  canonicalId: number | null;
  mediaType: "ANIME" | "MANGA";
  detailAccount: ActiveAccount;
  onClose: () => void;
  onChanged: () => Promise<void>;
  onSelect?: (id: number, type: "ANIME" | "MANGA") => void;
}) {
  const { t, titleLanguage } = useApp();
  const isManga = mediaType === "MANGA";
  const entry = details.list_entry;
  const [tab, setTab] = useState<"info" | "reparto" | "recomendaciones" | "edit">("info");
  const [status, setStatus] = useState(entry?.status ?? "PLANNING");
  const [progress, setProgress] = useState(entry?.progress ?? 0);
  const [score, setScore] = useState(scoreFromCanonical(entry?.score ?? 0, details.score_format));
  const [repeat, setRepeat] = useState(entry?.repeat ?? 0);
  const [privateEntry, setPrivateEntry] = useState(entry?.private ?? false);
  const [notes, setNotes] = useState(entry?.notes ?? "");
  const [startedAt, setStartedAt] = useState(dateToInput(entry?.started_at));
  const [completedAt, setCompletedAt] = useState(dateToInput(entry?.completed_at));
  const [saving, setSaving] = useState(false);
  const [modalError, setModalError] = useState<string | null>(null);
  const [modalSuccess, setModalSuccess] = useState<string | null>(null);
  const [updateResults, setUpdateResults] = useState<AccountUpdateResult[] | null>(null);
  const [undoUpdate, setUndoUpdate] = useState<MediaEntryUpdate | null>(null);
  const [undoDelete, setUndoDelete] = useState(false);
  const scoreConfig = scoreInputConfig(details.score_format);

  const save = async () => {
    const normalizedScore = normalizeScoreInput(score, details.score_format);
    if (normalizedScore == null) {
      setModalError(`La puntuación debe estar entre 0 y ${scoreConfig.max}.`);
      return;
    }
    setSaving(true);
    setModalError(null);
    setModalSuccess(null);
    setUpdateResults(null);
    const update: MediaEntryUpdate = {
      status,
      progress,
      score: scoreToCanonical(normalizedScore, details.score_format),
      repeat,
      private: privateEntry,
      notes,
    };
    update.started_at = startedAt ? inputToDate(startedAt) : null;
    update.completed_at = completedAt ? inputToDate(completedAt) : null;
    const destructiveMessage = describeDestructiveEntryChange(entry, update);
    if (destructiveMessage && !window.confirm(destructiveMessage)) {
      setSaving(false);
      return;
    }
    try {
      const targetId = canonicalId ?? details.id;
      const result = await api.bulkUpdateEntry(targetId, update);
      await onChanged();
      setUndoUpdate(entry ? snapshotEntryUpdate(entry) : null);
      setUndoDelete(false);
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
    setUpdateResults(null);
    try {
      await api.deleteEntry(entry.id, detailAccount);
      await onChanged();
      setUndoUpdate(snapshotEntryUpdate(entry));
      setUndoDelete(true);
      setTab("info");
      setModalSuccess(`${isManga ? "Manga" : "Anime"} eliminado de tu lista.`);
    } catch (reason) {
      setModalError(errorMessage(reason, "No se pudo eliminar la entrada"));
    } finally {
      setSaving(false);
    }
  };

  const undoLastChange = async () => {
    if (!undoUpdate) return;
    setSaving(true);
    setModalError(null);
    setModalSuccess(null);
    setUpdateResults(null);
    try {
      const targetId = canonicalId ?? details.id;
      const result = await api.bulkUpdateEntry(targetId, undoUpdate);
      await onChanged();
      setUndoUpdate(null);
      setUndoDelete(false);
      setUpdateResults(result.results);
      setModalSuccess(undoDelete ? "Eliminación revertida." : "Cambio revertido.");
    } catch (reason) {
      setModalError(errorMessage(reason, "No se pudo deshacer el cambio"));
    } finally {
      setSaving(false);
    }
  };

  const description = details.description ? new DOMParser().parseFromString(details.description, "text/html").body.textContent : null;
  const alternativeTitles = Array.from(new Set([details.title_romaji, details.title_english, details.title_native, ...details.synonyms].filter(Boolean)));

  return <div className="modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
    <section className="details-modal">
      <button className="modal-close" onClick={onClose} aria-label={t("detail.close")}>×</button>
      <div className="detail-banner" style={details.banner_image ? { backgroundImage: `linear-gradient(0deg, #11151f 0%, transparent 75%), url(${details.banner_image})` } : undefined} />
      <div className="detail-heading">
        <div className="detail-poster" style={details.cover_image ? { backgroundImage: `url(${details.cover_image})` } : undefined} />
        <div><p className="eyebrow">{details.format ?? (isManga ? "MANGA" : "ANIME")} {details.season ? `· ${details.season} ${details.season_year ?? ""}` : ""}</p><h2>{displayTitle(details, titleLanguage)}</h2><div className="genre-list">{details.genres.map((genre) => <span key={genre}>{genre}</span>)}</div></div>
      </div>
      <div className="detail-tabs">
        <button className={tab === "info" ? "selected" : ""} onClick={() => setTab("info")}>{t("detail.tab.info")}</button>
        {((details.characters ?? []).length > 0 || (details.staff ?? []).length > 0) && (
          <button className={tab === "reparto" ? "selected" : ""} onClick={() => setTab("reparto")}>{t("detail.tab.cast")}</button>
        )}
        {(details.recommendations ?? []).length > 0 && (
          <button className={tab === "recomendaciones" ? "selected" : ""} onClick={() => setTab("recomendaciones")}>{t("detail.tab.recommendations")}</button>
        )}
        <button className={tab === "edit" ? "selected" : ""} onClick={() => setTab("edit")}>{entry ? t("detail.tab.editList") : t("detail.tab.addList")}</button>
      </div>
      {modalError && <div className="modal-error">{modalError}</div>}
      {modalSuccess && <div className="modal-success">{modalSuccess}</div>}
      {undoUpdate && (
        <div className="undo-bar">
          <span>{t("detail.changeSaved")}</span>
          <button className="undo-change" disabled={saving} onClick={() => void undoLastChange()}>
            {t("detail.undo")}
          </button>
        </div>
      )}
      {updateResults && (
        <div className="update-results">
          {updateResults.map((result) => (
            <div key={`${result.provider}-${result.alias}`} className={result.success ? "update-success" : "update-failure"}>
              <span>{result.provider} · {result.alias}</span>
              <span>{result.success ? t("detail.result.saved") : result.error ?? t("detail.result.failed")}</span>
            </div>
          ))}
        </div>
      )}
      {tab === "info" && <div className="detail-body">
        {description && <div className="synopsis"><h3>{t("detail.synopsis")}</h3><p>{description}</p></div>}
        <div className="detail-facts">
          <Fact label={t("detail.fact.status")} value={details.status} />
          <Fact label={t("detail.fact.source")} value={details.source} />
          {isManga ? (
            <>
              <Fact label={t("detail.fact.chapters")} value={details.chapters} />
              <Fact label={t("detail.fact.volumes")} value={details.volumes} />
            </>
          ) : (
            <>
              <Fact label={t("detail.fact.episodes")} value={details.episodes} />
              <Fact label={t("detail.fact.duration")} value={details.duration ? `${details.duration} min` : null} />
            </>
          )}
          {!isManga && (
            <>
              <Fact label={t("detail.fact.studios")} value={details.studios.join(", ")} />
              <Fact label={t("detail.fact.country")} value={details.country} />
              <Fact label={t("detail.fact.nextEp")} value={details.next_episode ? `${details.next_episode}${details.next_airing_at ? ` · ${new Date(details.next_airing_at * 1000).toLocaleString("es")}` : ""}` : null} />
            </>
          )}
          <Fact label={t("detail.fact.score")} value={details.average_score ? `${details.average_score}%` : null} />
        </div>
        {alternativeTitles.length > 1 && <div className="alternative-titles"><h3>{t("detail.altTitles")}</h3><p>{alternativeTitles.join(" · ")}</p></div>}
        {details.trailer && details.trailer.site === "youtube" && (
          <a className="external-link" href={`https://www.youtube.com/watch?v=${details.trailer.id}`} target="_blank" rel="noreferrer">{t("detail.trailer")}</a>
        )}
        {(details.relations ?? []).filter(r => r.format !== "MUSIC").length > 0 && (
          <div className="detail-section">
            <h3>{t("detail.related")}</h3>
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
        <a className="external-link" href={details.site_url} target="_blank" rel="noreferrer">{t("detail.openIn")} {detailAccount.provider === "mal" ? "MyAnimeList" : detailAccount.provider === "kitsu" ? "Kitsu" : "AniList"} ↗</a>
      </div>}
      {tab === "reparto" && <div className="detail-body">
        {!isManga && (details.characters ?? []).length > 0 && (
          <div className="detail-section">
            <h3>{t("detail.characters")}</h3>
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
                    <span className="portrait-sub">{edge.role === "MAIN" ? t("detail.main") : t("detail.secondary")}</span>
                    {va?.name?.full && <span className="portrait-va">{va.name.full}</span>}
                  </div>
                );
              })}
            </div>
          </div>
        )}
        {(details.staff ?? []).length > 0 && (
          <div className="detail-section">
            <h3>{t("detail.staff")}</h3>
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
        <label>{t("detail.edit.status")}<select value={status} onChange={(event) => setStatus(event.target.value)}><option value="CURRENT">{t("badge.CURRENT")}</option><option value="PLANNING">{t("badge.PLANNING")}</option><option value="COMPLETED">{t("badge.COMPLETED")}</option><option value="PAUSED">{t("badge.PAUSED")}</option><option value="DROPPED">{t("badge.DROPPED")}</option></select></label>
        <label>{t("detail.edit.progress")}<input type="number" min="0" max={isManga ? (details.chapters ?? undefined) : (details.episodes ?? undefined)} value={progress} onChange={(event) => setProgress(Number(event.target.value))} /></label>
        <label>{t("detail.edit.score")}<input type="number" min="0" max={scoreConfig.max} step={scoreConfig.step} value={score} onChange={(event) => setScore(Number(event.target.value))} /></label>
        <label>{t("detail.edit.repeat")}<input type="number" min="0" value={repeat} onChange={(event) => setRepeat(Number(event.target.value))} /></label>
        <label>{t("detail.edit.startDate")}<input type="date" value={startedAt} onChange={(event) => setStartedAt(event.target.value)} /></label>
        <label>{t("detail.edit.endDate")}<input type="date" value={completedAt} onChange={(event) => setCompletedAt(event.target.value)} /></label>
        <label className="notes-field">{t("detail.edit.notes")}<textarea rows={4} value={notes} onChange={(event) => setNotes(event.target.value)} /></label>
        <label className="checkbox-field"><input type="checkbox" checked={privateEntry} onChange={(event) => setPrivateEntry(event.target.checked)} /> {t("detail.edit.private")}</label>
        <div className="edit-actions"><button className="primary" disabled={saving} onClick={() => void save()}>{saving ? t("detail.edit.saving") : entry ? t("detail.edit.saveChanges") : t("detail.edit.addToList")}</button>{entry && <button className="danger" disabled={saving} onClick={() => void remove()}>{t("detail.edit.delete")}</button>}</div>
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
  const { t } = useApp();
  return <div><span>{label}</span><strong>{value ?? t("common.unknown")}</strong></div>;
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

function scoreFromCanonical(value: number, format: string): number {
  if (!value) return 0;
  if (format === "POINT_100") return value;
  if (format === "POINT_10_DECIMAL") return Number((value / 10).toFixed(1));
  if (format === "POINT_10") return Math.round(value / 10);
  if (format === "POINT_5") return Math.round(value / 20);
  if (format === "POINT_3") {
    if (value >= 90) return 3;
    if (value >= 55) return 2;
    return 1;
  }
  return Math.round(value / 10);
}

function scoreToCanonical(value: number, format: string): number {
  if (!value) return 0;
  if (format === "POINT_100") return value;
  if (format === "POINT_10_DECIMAL" || format === "POINT_10") return value * 10;
  if (format === "POINT_5") return value * 20;
  if (format === "POINT_3") return value * 33 + 1;
  return value * 10;
}

function normalizeScoreInput(value: number, format: string): number | null {
  if (!Number.isFinite(value)) return null;
  const config = scoreInputConfig(format);
  if (value < 0 || value > config.max) return null;
  if (config.step === 0.1) return Number(value.toFixed(1));
  return Math.round(value);
}

function snapshotEntryUpdate(entry: MediaDetails["list_entry"]): MediaEntryUpdate {
  return {
    status: entry?.status ?? null,
    progress: entry?.progress ?? 0,
    score: entry?.score ?? 0,
    repeat: entry?.repeat ?? 0,
    private: entry?.private ?? false,
    notes: entry?.notes ?? "",
    started_at: entry?.started_at ?? null,
    completed_at: entry?.completed_at ?? null,
  };
}

function describeDestructiveEntryChange(
  previous: MediaDetails["list_entry"],
  next: MediaEntryUpdate,
): string | null {
  if (!previous) return null;
  const clearedFields: string[] = [];
  if (previous.progress > 0 && typeof next.progress === "number" && next.progress < previous.progress) {
    return "Vas a reducir el progreso guardado. ¿Continuar?";
  }
  if (previous.status === "COMPLETED" && next.status && next.status !== "COMPLETED") {
    return "La entrada dejará de figurar como completada. ¿Continuar?";
  }
  if (previous.score > 0 && (next.score ?? 0) === 0) clearedFields.push("puntuación");
  if (dateToInput(previous.started_at) && next.started_at === null) clearedFields.push("fecha de inicio");
  if (dateToInput(previous.completed_at) && next.completed_at === null) clearedFields.push("fecha de término");
  if ((previous.notes ?? "").trim() && (next.notes ?? "").trim() === "") clearedFields.push("notas");
  if (clearedFields.length === 0) return null;
  return `Vas a borrar ${clearedFields.join(", ")}. ¿Continuar?`;
}

function Empty({ title, detail }: { title: string; detail?: string }) {
  return <div className="empty"><strong>{title}</strong>{detail && <span>{detail}</span>}</div>;
}

function PendingLocalReminder({ onSelect, onSeeMore }: { onSelect: (id: number) => void; onSeeMore?: () => void }) {
  const { t } = useApp();
  const [items, setItems] = useState<PendingLocalItem[]>([]);

  useEffect(() => { void api.pendingLocal().then(setItems).catch(() => {}); }, []);

  if (items.length === 0) return null;
  return <div className="pending-local">
    <h3>{t("np.local.title")} ({items.length})</h3>
    <div className="pending-local-list">
      {items.map((item) => (
        <article key={item.media_id} className="pending-local-item clickable" onClick={() => onSelect(item.external_id)} title={item.title}>
          <div className="poster" style={item.cover_image ? { backgroundImage: `url(${item.cover_image})` } : undefined} />
          <div className="pending-local-info">
            <strong>{item.title}</strong>
            <span>{t("np.local.episode")} {item.next_episode}{item.available_count > 1 ? ` · ${item.available_count} ${t("np.local.available")}` : ""}</span>
          </div>
          <button className="pending-local-play" title={t("np.local.play")} onClick={(e) => { e.stopPropagation(); void openPath(item.next_path); }}>▶</button>
        </article>
      ))}
    </div>
    {onSeeMore && <button className="small" onClick={onSeeMore}>{t("local.seeMore")}</button>}
  </div>;
}
