import { useEffect, useState } from "react";
import { api } from "./api";
import { useApp, type Lang, type Theme, type TitleLanguage } from "./i18n";
import { AccountSettingsView } from "./AccountSettingsView";
import { ConflictSettingsView } from "./ConflictSettingsView";
import { ExtensionSettingsView } from "./ExtensionSettingsView";
import { LibrarySettingsView } from "./LibrarySettingsView";
import { TorrentsSettingsView } from "./TorrentsSettingsView";
import { getWindowPrefs, setWindowPrefs, type WindowPrefs } from "./windowPrefs";
import type { CacheStatusResponse, DetectorInfo, PlaybackPreferences, ProgressPolicy, ProviderCapabilities, UserPreferences } from "./types";

type SettingsTab = "proveedores" | "biblioteca" | "aplicacion" | "reconocimiento" | "torrents";

const SOON_OPTIONS = [
  "Buscar actualizaciones",
];

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
};

export function DetectorSettingsView({ authenticated, activeAccount, capabilities, onSync, onPreferencesChanged, onLogout, onConnectAccount, onAccountChanged, autostart, onToggleAutostart }: {
  authenticated: boolean;
  activeAccount: { provider: string; alias: string };
  capabilities: ProviderCapabilities;
  onSync: () => Promise<void>;
  onPreferencesChanged: () => Promise<void>;
  onLogout: () => Promise<void>;
  onConnectAccount: (provider: string, alias: string) => Promise<void>;
  onAccountChanged: (provider: string, alias: string) => Promise<void>;
  autostart: boolean;
  onToggleAutostart: () => Promise<void>;
}) {
  const { t, lang, setLang, theme, setTheme, titleLanguage, setTitleLanguage, discordRpc, setDiscordRpc, discordFields, setDiscordFields } = useApp();
  const providerLabel = PROVIDER_LABELS[activeAccount.provider] ?? activeAccount.provider;
  const [tab, setTab] = useState<SettingsTab>("proveedores");
  const [appTab, setAppTab] = useState<"anime" | "general">("anime");
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
    void api.getScanSettings().then((s) => setScanOnStartup(s.scan_on_startup)).catch(() => {});
  }, [authenticated]);

  const toggleScanOnStartup = async () => {
    if (scanOnStartup === null) return;
    const next = !scanOnStartup;
    setScanOnStartup(next);
    try {
      await api.setScanSettings(next);
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

  const logout = async () => {
    if (!window.confirm(`¿Cerrar la sesión de ${providerLabel} en Nyanko?`)) return;
    try {
      await onLogout();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudo cerrar la sesión");
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
    </div>

    {message && <div className="modal-success">{message}</div>}
    {error && <div className="modal-error">{error}</div>}

    {tab === "proveedores" && (
      <AccountSettingsView
        activeAccount={activeAccount}
        onConnect={onConnectAccount}
        onAccountChanged={onAccountChanged}
        generalExtras={<>
          {preferences && <div className="profile-settings">
            <div className="profile-heading">
              <div><h2>Preferencias de {providerLabel}</h2></div>
            </div>
            {capabilities.preferences_editable ? <>
              <div className="preference-fields">
                <label>Idioma de títulos<select value={titleLanguage} onChange={(event) => setTitleLanguage(event.target.value as TitleLanguage)}><option value="ROMAJI">Romaji</option><option value="ENGLISH">Inglés</option><option value="NATIVE">Nativo</option></select></label>
                {activeAccount.provider === "anilist" && <label>Formato de puntuación<select value={preferences.score_format} onChange={(event) => setPreferences({ ...preferences, score_format: event.target.value as UserPreferences["score_format"] })}><option value="POINT_100">100 puntos</option><option value="POINT_10_DECIMAL">10 puntos decimal</option><option value="POINT_10">10 puntos</option><option value="POINT_5">5 estrellas</option><option value="POINT_3">3 emociones</option></select></label>}
                <label className="checkbox-field"><input type="checkbox" checked={preferences.display_adult_content} onChange={(event) => setPreferences({ ...preferences, display_adult_content: event.target.checked })} /> Mostrar contenido adulto</label>
              </div>
              <div className="profile-actions"><button className="primary" disabled={savingPreferences} onClick={() => void savePreferences()}>{savingPreferences ? "Guardando…" : "Guardar preferencias"}</button><button className="danger" onClick={() => void logout()}>Cerrar sesión</button></div>
            </> : <>
              <p className="preference-readonly">{providerLabel} no permite editar estas preferencias desde la API. Gestiona tu perfil en la web de {providerLabel}.</p>
              <div className="profile-actions"><button className="danger" onClick={() => void logout()}>Cerrar sesión</button></div>
            </>}
          </div>}
          <ConflictSettingsView />
        </>}
      />
    )}

    {tab === "biblioteca" && <LibrarySettingsView />}

    {tab === "aplicacion" && <>
      <div className="settings-tabs provider-subtabs">
        <button className={appTab === "anime" ? "active" : ""} onClick={() => setAppTab("anime")}>{t("settings.subtab.anime")}</button>
        <button className={appTab === "general" ? "active" : ""} onClick={() => setAppTab("general")}>{t("settings.subtab.general")}</button>
      </div>

      {appTab === "general" && <>
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
            <h2>Sincronización y caché</h2>
            <p>{cache?.last_updated
              ? `Última actualización: ${new Date(cache.last_updated * 1000).toLocaleString("es")}`
              : "Todavía no hay información cacheada."}</p>
            <small>{cache?.entries.length ?? 0} conjuntos · {(cacheSize / 1024).toFixed(1)} KB{staleEntries ? ` · ${staleEntries} vencidos disponibles sin conexión` : ""}</small>
          </div>
          <button className="primary" disabled={syncing} onClick={() => void sync()}>{syncing ? "Sincronizando…" : "Sincronizar ahora"}</button>
        </div>
        <div className="detector-list">
          <article>
            <div><strong>Iniciar con Windows</strong><span>Nyanko se abrirá al iniciar sesión en Windows</span></div>
            <button className={autostart ? "toggle enabled" : "toggle"} onClick={() => void onToggleAutostart()} aria-pressed={autostart}><i /></button>
          </article>
          {windowPrefs && <>
            <article>
              <div><strong>Iniciar minimizada</strong><span>Arranca oculta en la bandeja del sistema</span></div>
              <button className={windowPrefs.start_minimized ? "toggle enabled" : "toggle"} onClick={() => void toggleWindowPref("start_minimized")} aria-pressed={windowPrefs.start_minimized}><i /></button>
            </article>
            <article>
              <div><strong>Cerrar a la bandeja</strong><span>Al cerrar la ventana, seguir corriendo en la bandeja</span></div>
              <button className={windowPrefs.close_to_tray ? "toggle enabled" : "toggle"} onClick={() => void toggleWindowPref("close_to_tray")} aria-pressed={windowPrefs.close_to_tray}><i /></button>
            </article>
            <article>
              <div><strong>Minimizar a la bandeja</strong><span>Al minimizar, ocultar en la bandeja en vez de la barra de tareas</span></div>
              <button className={windowPrefs.minimize_to_tray ? "toggle enabled" : "toggle"} onClick={() => void toggleWindowPref("minimize_to_tray")} aria-pressed={windowPrefs.minimize_to_tray}><i /></button>
            </article>
          </>}
          {scanOnStartup !== null && <article>
            <div><strong>Escanear carpetas al iniciar</strong><span>Buscar episodios disponibles en local al abrir Nyanko</span></div>
            <button className={scanOnStartup ? "toggle enabled" : "toggle"} onClick={() => void toggleScanOnStartup()} aria-pressed={scanOnStartup}><i /></button>
          </article>}
          <article>
            <div><strong>Discord Rich Presence</strong><span>Mostrar en Discord lo que estás viendo</span></div>
            <button className={discordRpc ? "toggle enabled" : "toggle"} onClick={() => setDiscordRpc(!discordRpc)} aria-pressed={discordRpc}><i /></button>
          </article>
        </div>
        {discordRpc && <div className="preference-fields" style={{ marginTop: "4px" }}>
          <label className="checkbox-field"><input type="checkbox" checked={discordFields.title} onChange={(e) => setDiscordFields({ ...discordFields, title: e.target.checked })} /> Serie y episodio</label>
          <label className="checkbox-field"><input type="checkbox" checked={discordFields.user} onChange={(e) => setDiscordFields({ ...discordFields, user: e.target.checked })} /> Usuario y plataforma</label>
          <label className="checkbox-field"><input type="checkbox" checked={discordFields.elapsed} onChange={(e) => setDiscordFields({ ...discordFields, elapsed: e.target.checked })} /> Tiempo viendo</label>
        </div>}
        <div className="settings-explanation"><h2>Más opciones <span className="soon-tag">{t("settings.soon")}</span></h2><p>Funciones en camino; aún no están activas.</p></div>
        <div className="detector-list">{SOON_OPTIONS.map((option) => (
          <article key={option}>
            <div><strong>{option}</strong></div>
            <button className="toggle" disabled aria-disabled="true"><i /></button>
          </article>
        ))}</div>
      </>}
    </>}

    {tab === "reconocimiento" && <>
      <div className="settings-tabs provider-subtabs">
        <button className={recogTab === "general" ? "active" : ""} onClick={() => setRecogTab("general")}>{t("settings.subtab.general")}</button>
        <button className={recogTab === "reproductores" ? "active" : ""} onClick={() => setRecogTab("reproductores")}>{t("settings.subtab.players")}</button>
        <button className={recogTab === "plataformas" ? "active" : ""} onClick={() => setRecogTab("plataformas")}>{t("settings.subtab.streaming")}</button>
      </div>

      {recogTab === "general" && <>
        {playbackPreferences && <div className="profile-settings">
          <div className="profile-heading"><div><h2>Automatización de reproducción</h2><span>Confirma el progreso detectado sin intervención cuando la confianza sea alta</span></div></div>
          <div className="preference-fields">
            <label className="checkbox-field"><input type="checkbox" checked={playbackPreferences.auto_confirm} onChange={(event) => setPlaybackPreferences({ ...playbackPreferences, auto_confirm: event.target.checked })} /> Confirmar progreso automáticamente</label>
            <label>Umbral de confianza ({Math.round(playbackPreferences.confidence_threshold * 100)}%)<input type="range" min="0" max="1" step="0.05" value={playbackPreferences.confidence_threshold} onChange={(event) => setPlaybackPreferences({ ...playbackPreferences, confidence_threshold: Number(event.target.value) })} /></label>
            <label>Confirmar cuando…
              <select value={playbackPreferences.progress_policy} onChange={(event) => setPlaybackPreferences({ ...playbackPreferences, progress_policy: event.target.value as ProgressPolicy })}>
                <option value="end">el episodio esté cerca de terminar</option>
                <option value="middle">el episodio lleve la mitad</option>
                <option value="start">el episodio empiece</option>
                <option value="seconds">haya pasado un tiempo</option>
                <option value="always">haya una coincidencia (inmediato)</option>
                <option value="never">nunca</option>
              </select>
            </label>
            {playbackPreferences.progress_policy === "seconds" && (
              <label>Segundos reproducidos antes de confirmar
                <input type="number" min="0" step="1" value={playbackPreferences.progress_seconds} onChange={(event) => setPlaybackPreferences({ ...playbackPreferences, progress_seconds: Math.max(0, Number(event.target.value)) })} />
              </label>
            )}
          </div>
          <div className="profile-actions"><button className="primary" disabled={savingPlaybackPreferences} onClick={() => void savePlaybackPreferences()}>{savingPlaybackPreferences ? "Guardando…" : "Guardar automatización"}</button></div>
        </div>}
        {!playbackPreferences && <p style={{ color: "#8f97aa" }}>Cargando preferencias…</p>}
      </>}

      {recogTab === "reproductores" && <>
        <div className="settings-explanation">
          <h2>Detectores de reproducción</h2>
          <p>Desactiva los reproductores que no utilizas. La ventana activa es menos precisa y debe quedar como fallback.</p>
        </div>
        <div className="detector-list">{detectors.map((detector) => (
          <article key={detector.name}>
            <div><strong>{LABELS[detector.name] ?? detector.name}</strong><span>Prioridad {detector.priority} · {detector.available ? "disponible" : "no detectado"}</span></div>
            <button
              className={detector.enabled ? "toggle enabled" : "toggle"}
              disabled={saving === detector.name}
              onClick={() => void toggle(detector)}
              aria-pressed={detector.enabled}
            ><i /></button>
          </article>
        ))}</div>
      </>}

      {recogTab === "plataformas" && <ExtensionSettingsView />}
    </>}

    {tab === "torrents" && <TorrentsSettingsView />}
  </section>;
}
