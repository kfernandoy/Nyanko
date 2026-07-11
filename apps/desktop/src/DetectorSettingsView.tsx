import { useEffect, useState } from "react";
import { native, isNative } from "./native";
import { api } from "./api";
import { KittenLogo } from "./KittenLogo";
import { useApp, type Lang, type Theme, type TitleLanguage } from "./i18n";
import { AccountSettingsView } from "./AccountSettingsView";
import { ConflictSettingsView } from "./ConflictSettingsView";
import { ExtensionSettingsView } from "./ExtensionSettingsView";
import { LibrarySettingsView } from "./LibrarySettingsView";
import { TorrentsSettingsView } from "./TorrentsSettingsView";
import { getWindowPrefs, setWindowPrefs, type WindowPrefs } from "./windowPrefs";
import type { CacheStatusResponse, DetectorInfo, PlaybackPreferences, ProgressPolicy, ProviderCapabilities, UserPreferences } from "./types";

type SettingsTab = "proveedores" | "biblioteca" | "aplicacion" | "reconocimiento" | "torrents" | "acerca";

// Solo Patreon: permite tiers con extras (temas personalizados, etc.) sin meter ads.
const PATREON_URL = "https://www.patreon.com/c/nyankoapp";

const PROVIDER_LABELS: Record<string, string> = {
  anilist: "AniList",
  mal: "MyAnimeList",
  kitsu: "Kitsu",
};

const LABELS: Record<string, string> = {
  mpv: "mpv",
  "mpc-hc": "MPC-HC",
  potplayer: "PotPlayer",
  vlc: "VLC",
  "active-window": "Ventana activa (fallback)",
  browser: "Extensión del navegador",
  process: "Archivo abierto (cualquier reproductor)",
};

export function DetectorSettingsView({ authenticated, activeAccount, capabilities, onSync, onPreferencesChanged, onConnectAccount, onAccountChanged, autostart, onToggleAutostart }: {
  authenticated: boolean;
  activeAccount: { provider: string; alias: string };
  capabilities: ProviderCapabilities;
  onSync: () => Promise<void>;
  onPreferencesChanged: () => Promise<void>;
  onConnectAccount: (provider: string, alias: string) => Promise<void>;
  onAccountChanged: (provider: string, alias: string) => Promise<void>;
  autostart: boolean;
  onToggleAutostart: () => Promise<void>;
}) {
  const { t, lang, setLang, theme, setTheme, titleLanguage, setTitleLanguage, discordRpc, setDiscordRpc, discordFields, setDiscordFields } = useApp();
  const providerLabel = PROVIDER_LABELS[activeAccount.provider] ?? activeAccount.provider;
  const [tab, setTab] = useState<SettingsTab>("proveedores");
  // ponytail: appTab removed — only "general" subtab remains
  const [recogTab, setRecogTab] = useState<"general" | "reproductores" | "plataformas">("general");
  const [detectors, setDetectors] = useState<DetectorInfo[]>([]);
  const [saving, setSaving] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cache, setCache] = useState<CacheStatusResponse | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [preferences, setPreferences] = useState<UserPreferences | null>(null);
  const [savingPreferences, setSavingPreferences] = useState(false);
  const [playbackPreferences, setPlaybackPreferences] = useState<PlaybackPreferences | null>(null);
  const [savingPlaybackPreferences, setSavingPlaybackPreferences] = useState(false);
  const [windowPrefs, setWindowPrefsState] = useState<WindowPrefs | null>(null);
  const [scanOnStartup, setScanOnStartup] = useState<boolean | null>(null);
  const [watchFolders, setWatchFolders] = useState<boolean>(false);
  const [appVersion, setAppVersion] = useState<string | null>(null);
  const [updateState, setUpdateState] = useState<"idle" | "checking" | "none" | "downloading" | "error">("idle");

  useEffect(() => {
    if (isNative) void native.appVersion().then(setAppVersion).catch(() => {});
  }, []);

  const checkForUpdates = async () => {
    setUpdateState("checking");
    setError(null);
    setMessage(null);
    try {
      // ponytail: flujo real de updater lo reconstruye Fase 5 en el main (PKG-02).
      // Hoy native.checkForUpdates es un throw-stub, así que el catch informa el error.
      await native.checkForUpdates();
    } catch (reason) {
      setUpdateState("error");
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  };

  useEffect(() => {
    void api.detectors().then(setDetectors).catch((reason) => {
      setError(reason instanceof Error ? reason.message : "No se pudieron cargar los detectores");
    });
    void api.cacheStatus().then(setCache).catch(() => {});
    if (authenticated) {
      void api.preferences().then(({ data }) => setPreferences(data)).catch((reason) => {
        setError(reason instanceof Error ? reason.message : "No se pudieron cargar las preferencias");
      });
    }
    void api.playbackPreferences().then(setPlaybackPreferences).catch(() => {});
    void getWindowPrefs().then(setWindowPrefsState).catch(() => {});
    void api.getScanSettings().then((s) => { setScanOnStartup(s.scan_on_startup); setWatchFolders(s.watch_folders); }).catch(() => {});
  }, [authenticated]);

  const saveScanSettings = async (nextStartup: boolean, nextWatch: boolean) => {
    setScanOnStartup(nextStartup);
    setWatchFolders(nextWatch);
    try {
      await api.setScanSettings(nextStartup, nextWatch);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudo guardar la opción de escaneo");
    }
  };

  const toggleWindowPref = async (key: keyof WindowPrefs) => {
    if (!windowPrefs) return;
    const next = { ...windowPrefs, [key]: !windowPrefs[key] };
    setWindowPrefsState(next);
    try {
      await setWindowPrefs(next);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudo guardar la opción de ventana");
    }
  };

  const switchTab = (next: SettingsTab) => {
    setTab(next);
    setMessage(null);
    setError(null);
  };

  const toggle = async (detector: DetectorInfo) => {
    const enabled = !detector.enabled;
    setSaving(detector.name);
    setMessage(null);
    setError(null);
    try {
      await api.updateDetector(detector.name, enabled);
      setDetectors((current) => current.map((item) =>
        item.name === detector.name ? { ...item, enabled } : item));
      setMessage(`${LABELS[detector.name] ?? detector.name} ${enabled ? "activado" : "desactivado"}.`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudo guardar el detector");
    } finally {
      setSaving(null);
    }
  };

  const sync = async () => {
    setSyncing(true);
    setError(null);
    setMessage(null);
    try {
      await onSync();
      setCache(await api.cacheStatus());
      setMessage("Sincronización completada.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudo sincronizar");
    } finally {
      setSyncing(false);
    }
  };

  const cacheSize = cache?.entries.reduce((total, entry) => total + entry.size, 0) ?? 0;
  const staleEntries = cache?.entries.filter((entry) => entry.stale).length ?? 0;

  const savePreferences = async () => {
    if (!preferences) return;
    setSavingPreferences(true);
    setError(null);
    setMessage(null);
    try {
      const updated = await api.updatePreferences({
        title_language: preferences.title_language,
        score_format: preferences.score_format,
        display_adult_content: preferences.display_adult_content,
      });
      setPreferences(updated);
      await onPreferencesChanged();
      setMessage(`Preferencias de ${providerLabel} guardadas.`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudieron guardar las preferencias");
    } finally {
      setSavingPreferences(false);
    }
  };

  const savePlaybackPreferences = async () => {
    if (!playbackPreferences) return;
    setSavingPlaybackPreferences(true);
    setError(null);
    setMessage(null);
    try {
      const updated = await api.updatePlaybackPreferences(playbackPreferences);
      setPlaybackPreferences(updated);
      setMessage("Automatización de reproducción guardada.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudieron guardar las preferencias de reproducción");
    } finally {
      setSavingPlaybackPreferences(false);
    }
  };

  return <section className="detector-settings">
    <div className="settings-tabs">
      <button className={tab === "proveedores" ? "active" : ""} onClick={() => switchTab("proveedores")}>{t("settings.tab.providers")}</button>
      <button className={tab === "biblioteca" ? "active" : ""} onClick={() => switchTab("biblioteca")}>{t("settings.tab.library")}</button>
      <button className={tab === "aplicacion" ? "active" : ""} onClick={() => switchTab("aplicacion")}>{t("settings.tab.app")}</button>
      <button className={tab === "reconocimiento" ? "active" : ""} onClick={() => switchTab("reconocimiento")}>{t("settings.tab.recognition")}</button>
      <button className={tab === "torrents" ? "active" : ""} onClick={() => switchTab("torrents")}>{t("settings.tab.torrents")}</button>
      <button className={tab === "acerca" ? "active" : ""} onClick={() => switchTab("acerca")}>{t("settings.tab.about")}</button>
    </div>

    {message && <div className="modal-success">{message}</div>}
    {error && <div className="modal-error">{error}</div>}

    {tab === "proveedores" && (
      <AccountSettingsView
        activeAccount={activeAccount}
        onConnect={onConnectAccount}
        onAccountChanged={onAccountChanged}
        generalExtras={<ConflictSettingsView />}
        providerExtras={(prov) => (prov === activeAccount.provider && preferences ? (
          <div className="profile-settings">
            <div className="profile-heading">
              <div><h2>{t("settings.providerPrefs")} {providerLabel}</h2></div>
            </div>
            <div className="preference-fields">
              <label>{t("settings.titleLanguage")}<select value={titleLanguage} onChange={(event) => setTitleLanguage(event.target.value as TitleLanguage)}><option value="ROMAJI">{t("settings.titleLang.romaji")}</option><option value="ENGLISH">{t("settings.titleLang.english")}</option><option value="NATIVE">{t("settings.titleLang.native")}</option></select></label>
            </div>
            {capabilities.preferences_editable ? <>
              <div className="preference-fields">
                {activeAccount.provider === "anilist" && <label>{t("settings.scoreFormat")}<select value={preferences.score_format} onChange={(event) => setPreferences({ ...preferences, score_format: event.target.value as UserPreferences["score_format"] })}><option value="POINT_100">100 puntos</option><option value="POINT_10_DECIMAL">10 puntos decimal</option><option value="POINT_10">10 puntos</option><option value="POINT_5">5 estrellas</option><option value="POINT_3">3 emociones</option></select></label>}
                <label className="checkbox-field"><input type="checkbox" checked={preferences.display_adult_content} onChange={(event) => setPreferences({ ...preferences, display_adult_content: event.target.checked })} /> {t("settings.adultContent")}</label>
              </div>
              <div className="profile-actions"><button className="primary" disabled={savingPreferences} onClick={() => void savePreferences()}>{savingPreferences ? t("common.saving") : t("settings.savePrefs")}</button></div>
            </> : (
              <p className="preference-readonly">{providerLabel} {t("settings.prefsReadonly")}</p>
            )}
          </div>
        ) : null)}
      />
    )}

    {tab === "biblioteca" && <LibrarySettingsView />}

    {tab === "aplicacion" && <>
        <div className="profile-settings">
          <div className="profile-heading"><div><h2>{t("settings.appearance.title")}</h2><span>{t("settings.appearance.subtitle")}</span></div></div>
          <div className="preference-fields">
            <label>{t("settings.appearance.language")}
              <select value={lang} onChange={(event) => setLang(event.target.value as Lang)}>
                <option value="es">{t("settings.lang.es")}</option>
                <option value="en">{t("settings.lang.en")}</option>
              </select>
            </label>
            <label>{t("settings.appearance.theme")}
              <select value={theme} onChange={(event) => setTheme(event.target.value as Theme)}>
                <option value="dark">{t("settings.theme.dark")}</option>
                <option value="light">{t("settings.theme.light")}</option>
              </select>
            </label>
          </div>
        </div>
        <div className="sync-settings">
          <div>
            <h2>{t("settings.syncCache")}</h2>
            <p>{cache?.last_updated
              ? `${t("settings.lastUpdate")} ${new Date(cache.last_updated * 1000).toLocaleString()}`
              : t("settings.noCache")}</p>
            <small>{cache?.entries.length ?? 0} {t("settings.cacheSets")} · {(cacheSize / 1024).toFixed(1)} KB{staleEntries ? ` · ${staleEntries} ${t("settings.staleOffline")}` : ""}</small>
          </div>
          <button className="primary" disabled={syncing} onClick={() => void sync()}>{syncing ? t("settings.syncing") : t("settings.syncNow")}</button>
        </div>
        <div className="detector-list">
          <article>
            <div><strong>{t("settings.autostart")}</strong><span>{t("settings.autostart.d")}</span></div>
            <button className={autostart ? "toggle enabled" : "toggle"} onClick={() => void onToggleAutostart()} aria-pressed={autostart}><i /></button>
          </article>
          {windowPrefs && <>
            <article>
              <div><strong>{t("settings.startMin")}</strong><span>{t("settings.startMin.d")}</span></div>
              <button className={windowPrefs.start_minimized ? "toggle enabled" : "toggle"} onClick={() => void toggleWindowPref("start_minimized")} aria-pressed={windowPrefs.start_minimized}><i /></button>
            </article>
            <article>
              <div><strong>{t("settings.closeTray")}</strong><span>{t("settings.closeTray.d")}</span></div>
              <button className={windowPrefs.close_to_tray ? "toggle enabled" : "toggle"} onClick={() => void toggleWindowPref("close_to_tray")} aria-pressed={windowPrefs.close_to_tray}><i /></button>
            </article>
            <article>
              <div><strong>{t("settings.minTray")}</strong><span>{t("settings.minTray.d")}</span></div>
              <button className={windowPrefs.minimize_to_tray ? "toggle enabled" : "toggle"} onClick={() => void toggleWindowPref("minimize_to_tray")} aria-pressed={windowPrefs.minimize_to_tray}><i /></button>
            </article>
          </>}
          {scanOnStartup !== null && <>
            <article>
              <div><strong>{t("settings.scanStart")}</strong><span>{t("settings.scanStart.d")}</span></div>
              <button className={scanOnStartup ? "toggle enabled" : "toggle"} onClick={() => void saveScanSettings(!scanOnStartup, watchFolders)} aria-pressed={scanOnStartup}><i /></button>
            </article>
            <article>
              <div><strong>{t("settings.watchFolders")}</strong><span>{t("settings.watchFolders.d")}</span></div>
              <button className={watchFolders ? "toggle enabled" : "toggle"} onClick={() => void saveScanSettings(scanOnStartup, !watchFolders)} aria-pressed={watchFolders}><i /></button>
            </article>
          </>}
          <article>
            <div><strong>{t("settings.discord")}</strong><span>{t("settings.discord.d")}</span></div>
            <button className={discordRpc ? "toggle enabled" : "toggle"} onClick={() => setDiscordRpc(!discordRpc)} aria-pressed={discordRpc}><i /></button>
          </article>
        </div>
        {discordRpc && <div className="preference-fields" style={{ marginTop: "4px" }}>
          <label className="checkbox-field"><input type="checkbox" checked={discordFields.title} onChange={(e) => setDiscordFields({ ...discordFields, title: e.target.checked })} /> {t("settings.discord.title")}</label>
          <label className="checkbox-field"><input type="checkbox" checked={discordFields.user} onChange={(e) => setDiscordFields({ ...discordFields, user: e.target.checked })} /> {t("settings.discord.user")}</label>
          <label className="checkbox-field"><input type="checkbox" checked={discordFields.elapsed} onChange={(e) => setDiscordFields({ ...discordFields, elapsed: e.target.checked })} /> {t("settings.discord.elapsed")}</label>
        </div>}
    </>}

    {tab === "acerca" && <>
      <div className="profile-settings">
        <div className="profile-heading">
          <span className="about-logo"><KittenLogo /></span>
          <div><h2>Nyanko</h2><span>{t("about.tagline")}</span></div>
        </div>
        <p className="about-desc">{t("about.d")}</p>
      </div>
      <div className="detector-list">
        <article>
          <div><strong>{t("about.version")}</strong><span>{appVersion ?? "—"}</span></div>
        </article>
        <article>
          <div><strong>{t("about.updates")}</strong><span>{t("about.updates.d")}</span></div>
          <button
            className="small"
            disabled={!appVersion || updateState === "checking" || updateState === "downloading"}
            title={!appVersion ? t("about.updatesNeedApp") : undefined}
            onClick={() => void checkForUpdates()}
          >
            {updateState === "checking" ? t("about.checking") : updateState === "downloading" ? t("about.downloading") : t("about.checkUpdates")}
          </button>
        </article>
        {"nyanko" in window && window.nyanko?.openLogsFolder && (
          <article>
            <div><strong>{t("about.logs")}</strong><span>{t("about.logs.d")}</span></div>
            <button
              className="small"
              onClick={() => {
                setError(null);
                void window.nyanko?.openLogsFolder?.().catch((reason: unknown) =>
                  setError(reason instanceof Error ? reason.message : String(reason)),
                );
              }}
            >
              {t("about.openLogs")}
            </button>
          </article>
        )}
      </div>
      <div className="about-support">
        <button className="about-patreon" onClick={() => void native.openExternal(PATREON_URL)}>❤ Patreon</button>
      </div>
    </>}

    {tab === "reconocimiento" && <>
      <div className="settings-tabs provider-subtabs">
        <button className={recogTab === "general" ? "active" : ""} onClick={() => setRecogTab("general")}>{t("settings.subtab.general")}</button>
        <button className={recogTab === "reproductores" ? "active" : ""} onClick={() => setRecogTab("reproductores")}>{t("settings.subtab.players")}</button>
        <button className={recogTab === "plataformas" ? "active" : ""} onClick={() => setRecogTab("plataformas")}>{t("settings.subtab.streaming")}</button>
      </div>

      {recogTab === "general" && <>
        {playbackPreferences && <div className="profile-settings">
          <div className="profile-heading"><div><h2>{t("settings.auto.title")}</h2><span>{t("settings.auto.d")}</span></div></div>
          <div className="preference-fields">
            <label className="checkbox-field"><input type="checkbox" checked={playbackPreferences.auto_confirm} onChange={(event) => setPlaybackPreferences({ ...playbackPreferences, auto_confirm: event.target.checked })} /> {t("settings.auto.confirm")}</label>
            <label>{t("settings.auto.threshold")} ({Math.round(playbackPreferences.confidence_threshold * 100)}%)<input type="range" min="0" max="1" step="0.05" value={playbackPreferences.confidence_threshold} onChange={(event) => setPlaybackPreferences({ ...playbackPreferences, confidence_threshold: Number(event.target.value) })} /></label>
            <label>{t("settings.auto.when")}
              <select value={playbackPreferences.progress_policy} onChange={(event) => setPlaybackPreferences({ ...playbackPreferences, progress_policy: event.target.value as ProgressPolicy })}>
                <option value="end">{t("settings.auto.end")}</option>
                <option value="middle">{t("settings.auto.middle")}</option>
                <option value="start">{t("settings.auto.start")}</option>
                <option value="seconds">{t("settings.auto.seconds")}</option>
                <option value="always">{t("settings.auto.always")}</option>
                <option value="never">{t("settings.auto.never")}</option>
              </select>
            </label>
            {playbackPreferences.progress_policy === "seconds" && (
              <label>{t("settings.auto.secondsLabel")}
                <input type="number" min="0" step="1" value={playbackPreferences.progress_seconds} onChange={(event) => setPlaybackPreferences({ ...playbackPreferences, progress_seconds: Math.max(0, Number(event.target.value)) })} />
              </label>
            )}
          </div>
          <div className="profile-actions"><button className="primary" disabled={savingPlaybackPreferences} onClick={() => void savePlaybackPreferences()}>{savingPlaybackPreferences ? t("common.saving") : t("settings.auto.save")}</button></div>
        </div>}
        {!playbackPreferences && <p style={{ color: "#8f97aa" }}>{t("settings.auto.loading")}</p>}
      </>}

      {recogTab === "reproductores" && <>
        <div className="settings-explanation">
          <h2>{t("settings.detectors.title")}</h2>
          <p>{t("settings.detectors.d")}</p>
        </div>
        <div className="detector-list">{detectors.filter((d) => d.name !== "browser").map((detector) => (
          <article key={detector.name}>
            <div><strong>{LABELS[detector.name] ?? detector.name}</strong><span>{t("settings.detectors.priority")} {detector.priority} · {detector.available ? t("settings.detectors.available") : t("settings.detectors.missing")}</span></div>
            <button
              className={detector.enabled ? "toggle enabled" : "toggle"}
              disabled={saving === detector.name}
              onClick={() => void toggle(detector)}
              aria-pressed={detector.enabled}
            ><i /></button>
          </article>
        ))}</div>
      </>}

      {recogTab === "plataformas" && <>
        {detectors.filter((d) => d.name === "browser").map((detector) => (
          <div className="detector-list" key={detector.name}>
            <article>
              <div><strong>{LABELS[detector.name]}</strong><span>{t("settings.detectors.priority")} {detector.priority} · {detector.available ? t("settings.detectors.available") : t("settings.detectors.missing")}</span></div>
              <button
                className={detector.enabled ? "toggle enabled" : "toggle"}
                disabled={saving === detector.name}
                onClick={() => void toggle(detector)}
                aria-pressed={detector.enabled}
              ><i /></button>
            </article>
          </div>
        ))}
        <ExtensionSettingsView />
      </>}
    </>}

    {tab === "torrents" && <TorrentsSettingsView />}
  </section>;
}
