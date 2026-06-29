import { useCallback, useEffect, useState } from "react";

import { api } from "./api";
import { useApp } from "./i18n";
import type { TorrentFilter, TorrentSettings, TorrentSource } from "./types";

const FIELDS = ["title", "group", "resolution", "episode"];
const OPS = ["contains", "not_contains", "equals", "gt", "lt", "regex"];
const ACTIONS = ["include", "exclude", "prefer"];

const blankSource = (): Omit<TorrentSource, "id"> => ({ name: "", url: "", enabled: true });
const blankFilter = (): Omit<TorrentFilter, "id"> => ({ field: FIELDS[0]!, op: OPS[0]!, value: "", action: ACTIONS[0]!, enabled: true, priority: 0 });

export function TorrentsSettingsView() {
  const { t } = useApp();
  const [sources, setSources] = useState<TorrentSource[]>([]);
  const [filters, setFilters] = useState<TorrentFilter[]>([]);
  const [settings, setSettings] = useState<TorrentSettings | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [newSource, setNewSource] = useState<Omit<TorrentSource, "id">>(blankSource);
  const [newFilter, setNewFilter] = useState<Omit<TorrentFilter, "id">>(blankFilter);

  const loadSources = useCallback(async () => { setSources(await api.torrentSources()); }, []);
  const loadFilters = useCallback(async () => { setFilters(await api.torrentFilters()); }, []);
  const loadSettings = useCallback(async () => { setSettings(await api.torrentSettings()); }, []);

  useEffect(() => {
    void loadSources().catch(() => {});
    void loadFilters().catch(() => {});
    void loadSettings().catch(() => {});
  }, [loadSources, loadFilters, loadSettings]);

  const err = (reason: unknown) => setError(reason instanceof Error ? reason.message : "Error");

  // Sources
  const addSource = async () => {
    if (!newSource.name || !newSource.url) return;
    setError(null);
    try { await api.addTorrentSource(newSource); setNewSource(blankSource()); await loadSources(); } catch (reason) { err(reason); }
  };
  const toggleSource = async (src: TorrentSource) => {
    try { await api.updateTorrentSource(src.id, { name: src.name, url: src.url, enabled: !src.enabled }); await loadSources(); } catch (reason) { err(reason); }
  };
  const deleteSource = async (src: TorrentSource) => {
    if (!window.confirm(`¿Eliminar "${src.name}"?`)) return;
    try { await api.deleteTorrentSource(src.id); await loadSources(); } catch (reason) { err(reason); }
  };

  // Filters
  const addFilter = async () => {
    setError(null);
    try { await api.addTorrentFilter(newFilter); setNewFilter(blankFilter()); await loadFilters(); } catch (reason) { err(reason); }
  };
  const toggleFilter = async (f: TorrentFilter) => {
    try { await api.updateTorrentFilter(f.id, { field: f.field, op: f.op, value: f.value, action: f.action, enabled: !f.enabled, priority: f.priority }); await loadFilters(); } catch (reason) { err(reason); }
  };
  const deleteFilter = async (f: TorrentFilter) => {
    try { await api.deleteTorrentFilter(f.id); await loadFilters(); } catch (reason) { err(reason); }
  };

  // Settings
  const patchSettings = async (patch: Partial<TorrentSettings>) => {
    if (!settings) return;
    try { setSettings(await api.putTorrentSettings({ ...settings, ...patch })); } catch (reason) { err(reason); }
  };

  return (
    <section className="account-settings">
      <div className="account-heading">
        <div><h2>{t("settings.tab.torrents")}</h2></div>
      </div>

      {error && <div className="modal-error">{error}</div>}

      {/* Fuentes RSS */}
      <div className="sync-settings">
        <h3>{t("torrents.sources")}</h3>
        <table className="torrents-table">
          <thead><tr><th>Nombre</th><th>URL</th><th>Activa</th><th /></tr></thead>
          <tbody>
            {sources.map((src) => (
              <tr key={src.id}>
                <td>{src.name}</td>
                <td><code>{src.url}</code></td>
                <td><input type="checkbox" checked={src.enabled} onChange={() => void toggleSource(src)} /></td>
                <td><button className="danger small" onClick={() => void deleteSource(src)}>{t("torrents.delete")}</button></td>
              </tr>
            ))}
            <tr>
              <td><input type="text" value={newSource.name} placeholder="Nombre" onChange={(e) => setNewSource({ ...newSource, name: e.target.value })} /></td>
              <td><input type="text" value={newSource.url} placeholder="https://…" onChange={(e) => setNewSource({ ...newSource, url: e.target.value })} /></td>
              <td><input type="checkbox" checked={newSource.enabled} onChange={(e) => setNewSource({ ...newSource, enabled: e.target.checked })} /></td>
              <td><button className="primary small" onClick={() => void addSource()}>{t("torrents.add")}</button></td>
            </tr>
          </tbody>
        </table>
      </div>

      {/* Reglas */}
      <div className="sync-settings">
        <h3>{t("torrents.filters")}</h3>
        <table className="torrents-table">
          <thead><tr><th>Campo</th><th>Op</th><th>Valor</th><th>Acción</th><th>Activa</th><th>Prio</th><th /></tr></thead>
          <tbody>
            {filters.map((f) => (
              <tr key={f.id}>
                <td>{f.field}</td>
                <td>{f.op}</td>
                <td>{f.value}</td>
                <td>{f.action}</td>
                <td><input type="checkbox" checked={f.enabled} onChange={() => void toggleFilter(f)} /></td>
                <td>{f.priority}</td>
                <td><button className="danger small" onClick={() => void deleteFilter(f)}>{t("torrents.delete")}</button></td>
              </tr>
            ))}
            <tr>
              <td><select value={newFilter.field} onChange={(e) => setNewFilter({ ...newFilter, field: e.target.value })}>{FIELDS.map((v) => <option key={v} value={v}>{v}</option>)}</select></td>
              <td><select value={newFilter.op} onChange={(e) => setNewFilter({ ...newFilter, op: e.target.value })}>{OPS.map((v) => <option key={v} value={v}>{v}</option>)}</select></td>
              <td><input type="text" value={newFilter.value} placeholder="Valor" onChange={(e) => setNewFilter({ ...newFilter, value: e.target.value })} /></td>
              <td><select value={newFilter.action} onChange={(e) => setNewFilter({ ...newFilter, action: e.target.value })}>{ACTIONS.map((v) => <option key={v} value={v}>{v}</option>)}</select></td>
              <td><input type="checkbox" checked={newFilter.enabled} onChange={(e) => setNewFilter({ ...newFilter, enabled: e.target.checked })} /></td>
              <td><input type="number" value={newFilter.priority} onChange={(e) => setNewFilter({ ...newFilter, priority: Number(e.target.value) })} /></td>
              <td><button className="primary small" onClick={() => void addFilter()}>{t("torrents.add")}</button></td>
            </tr>
          </tbody>
        </table>
      </div>

      {/* Ajustes */}
      {settings && (
        <div className="sync-settings">
          <h3>{t("settings.tab.torrents")}</h3>
          <div className="preferences-block">
            <label className="checkbox-field">
              <input type="checkbox" checked={settings.auto_check} onChange={(e) => void patchSettings({ auto_check: e.target.checked })} />
              {t("torrents.autoCheck")}
            </label>
            <label className="preference-field">
              <span>{t("torrents.interval")}</span>
              <input type="number" min={1} value={settings.interval_min} onChange={(e) => void patchSettings({ interval_min: Number(e.target.value) })} />
            </label>
            <label className="preference-field">
              <span>{t("torrents.downloadMode")}</span>
              <select value={settings.download_mode} onChange={(e) => void patchSettings({ download_mode: e.target.value })}>
                <option value="magnet">Magnet</option>
                <option value="folder">Carpeta</option>
              </select>
            </label>
            {settings.download_mode === "folder" && (
              <label className="preference-field">
                <span>{t("torrents.watchFolder")}</span>
                <input type="text" value={settings.watch_folder} onChange={(e) => void patchSettings({ watch_folder: e.target.value })} />
              </label>
            )}
            <label className="preference-field">
              <span>{t("torrents.preferredResolution")}</span>
              <input type="text" value={settings.preferred_resolution} onChange={(e) => void patchSettings({ preferred_resolution: e.target.value })} />
            </label>
          </div>
        </div>
      )}
    </section>
  );
}
