import { useEffect, useState } from "react";
import { api } from "./api";
import { AccountSettingsView } from "./AccountSettingsView";
import { AssociationSettingsView } from "./AssociationSettingsView";
import { ConflictSettingsView } from "./ConflictSettingsView";
import { ExtensionSettingsView } from "./ExtensionSettingsView";
import type { CacheStatusResponse, DetectorInfo, PlaybackPreferences, ProgressPolicy, UserPreferences } from "./types";

type SettingsTab = "proveedores" | "preferencias" | "sistema";

const LABELS: Record<string, string> = {
  mpv: "mpv",
  "mpc-hc": "MPC-HC",
  potplayer: "PotPlayer",
  vlc: "VLC",
  "active-window": "Ventana activa (fallback)",
};

export function DetectorSettingsView({ authenticated, activeAccount, onSync, onPreferencesChanged, onLogout, onConnectAccount, onAccountChanged }: {
  authenticated: boolean;
  activeAccount: { provider: string; alias: string };
  onSync: () => Promise<void>;
  onPreferencesChanged: () => Promise<void>;
  onLogout: () => Promise<void>;
  onConnectAccount: (provider: string, alias: string) => Promise<void>;
  onAccountChanged: (provider: string, alias: string) => Promise<void>;
}) {
  const [tab, setTab] = useState<SettingsTab>("proveedores");
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
  }, [authenticated]);

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
      setMessage("Preferencias de AniList guardadas.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudieron guardar las preferencias");
    } finally {
      setSavingPreferences(false);
    }
  };

  const logout = async () => {
    if (!window.confirm("¿Cerrar la sesión de AniList en Nyanko?")) return;
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
      <button className={tab === "proveedores" ? "active" : ""} onClick={() => switchTab("proveedores")}>Proveedores</button>
      <button className={tab === "preferencias" ? "active" : ""} onClick={() => switchTab("preferencias")}>Preferencias</button>
      <button className={tab === "sistema" ? "active" : ""} onClick={() => switchTab("sistema")}>Sistema</button>
    </div>

    {message && <div className="modal-success">{message}</div>}
    {error && <div className="modal-error">{error}</div>}

    {tab === "proveedores" && <>
      <AccountSettingsView activeAccount={activeAccount} onConnect={onConnectAccount} onAccountChanged={onAccountChanged} />
      <AssociationSettingsView />
      <ConflictSettingsView />
      {preferences && <div className="profile-settings">
        <div className="profile-heading">
          {preferences.avatar && <img src={preferences.avatar} alt="Avatar" />}
          <div><h2>{preferences.username}</h2><span>Cuenta AniList conectada</span></div>
        </div>
        <div className="preference-fields">
          <label>Idioma de títulos<select value={preferences.title_language} onChange={(event) => setPreferences({ ...preferences, title_language: event.target.value as UserPreferences["title_language"] })}><option value="ROMAJI">Romaji</option><option value="ENGLISH">Inglés</option><option value="NATIVE">Nativo</option></select></label>
          <label>Formato de puntuación<select value={preferences.score_format} onChange={(event) => setPreferences({ ...preferences, score_format: event.target.value as UserPreferences["score_format"] })}><option value="POINT_100">100 puntos</option><option value="POINT_10_DECIMAL">10 puntos decimal</option><option value="POINT_10">10 puntos</option><option value="POINT_5">5 estrellas</option><option value="POINT_3">3 emociones</option></select></label>
          <label className="checkbox-field"><input type="checkbox" checked={preferences.display_adult_content} onChange={(event) => setPreferences({ ...preferences, display_adult_content: event.target.checked })} /> Mostrar contenido adulto</label>
        </div>
        <div className="profile-actions"><button className="primary" disabled={savingPreferences} onClick={() => void savePreferences()}>{savingPreferences ? "Guardando…" : "Guardar preferencias"}</button><button className="danger" onClick={() => void logout()}>Cerrar sesión</button></div>
      </div>}
    </>}

    {tab === "preferencias" && <>
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

    {tab === "sistema" && <>
      <ExtensionSettingsView />
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
  </section>;
}
