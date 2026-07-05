import { useCallback, useEffect, useState } from "react";

import { api } from "./api";
import { useApp } from "./i18n";
import type { TorrentCondition, TorrentFilter, TorrentSettings, TorrentSource } from "./types";

const ELEMENTS = [
  "filename", "title", "group", "resolution", "episode", "size", "seeders",
  "version", "user_status", "media_status", "local_available",
];
const OPS = ["is", "is_not", "contains", "not_contains", "begins_with", "ends_with", "gt", "lt", "regex"];
const ACTIONS = ["select", "discard", "prefer"];

// Valores sugeridos para elementos con dominio conocido.
const VALUE_OPTIONS: Record<string, string[]> = {
  user_status: ["CURRENT", "PLANNING", "COMPLETED", "PAUSED", "DROPPED", "REPEATING", "NOT_IN_LIST"],
  media_status: ["RELEASING", "FINISHED", "NOT_YET_RELEASED"],
  local_available: ["true", "false"],
  resolution: ["2160p", "1080p", "720p", "480p"],
};

type FilterDraft = Omit<TorrentFilter, "id">;
type Translate = (key: string) => string;

const blankSource = (): Omit<TorrentSource, "id"> => ({ name: "", url: "", enabled: true, kind: "release" });
const blankFilter = (): FilterDraft => ({
  name: "", action: "select", match: "all", scope: "all", enabled: true,
  conditions: [{ element: "title", operator: "contains", value: "" }], anime_ids: [],
});

// Presets estilo Taiga: plantillas de un clic, editables después.
const PRESETS: { labelKey: string; make: (t: Translate) => FilterDraft }[] = [
  {
    labelKey: "tor.preset.group",
    make: (t) => ({
      name: t("tor.preset.group"), action: "prefer", match: "all", scope: "all", enabled: true,
      conditions: [{ element: "group", operator: "is", value: t("tor.preset.groupValue") }], anime_ids: [],
    }),
  },
  {
    labelKey: "tor.preset.badQuality",
    make: (t) => ({
      name: t("tor.preset.badQuality"), action: "discard", match: "any", scope: "all", enabled: true,
      conditions: ["avi", "divx", "lq", "rmvb", "sd", "wmv", "xvid"].map((keyword) => (
        { element: "filename", operator: "contains", value: keyword }
      )),
      anime_ids: [],
    }),
  },
  {
    labelKey: "tor.preset.newVersions",
    make: (t) => ({
      name: t("tor.preset.newVersions"), action: "prefer", match: "all", scope: "all", enabled: true,
      conditions: [{ element: "version", operator: "gt", value: "1" }], anime_ids: [],
    }),
  },
  {
    labelKey: "tor.preset.watching",
    make: (t) => ({
      name: t("tor.preset.watching"), action: "select", match: "any", scope: "all", enabled: true,
      conditions: [{ element: "user_status", operator: "is", value: "CURRENT" }], anime_ids: [],
    }),
  },
  {
    labelKey: "tor.preset.airingPlanned",
    make: (t) => ({
      name: t("tor.preset.airingPlanned"), action: "select", match: "all", scope: "all", enabled: true,
      conditions: [
        { element: "media_status", operator: "is", value: "RELEASING" },
        { element: "user_status", operator: "is", value: "PLANNING" },
      ],
      anime_ids: [],
    }),
  },
  {
    labelKey: "tor.preset.dropped",
    make: (t) => ({
      name: t("tor.preset.dropped"), action: "discard", match: "all", scope: "all", enabled: true,
      conditions: [{ element: "user_status", operator: "is", value: "DROPPED" }], anime_ids: [],
    }),
  },
  {
    labelKey: "tor.preset.onDisk",
    make: (t) => ({
      name: t("tor.preset.onDisk"), action: "discard", match: "all", scope: "all", enabled: true,
      conditions: [{ element: "local_available", operator: "is", value: "true" }], anime_ids: [],
    }),
  },
];

// Etiqueta legible de un valor de condición (estados de lista/emisión, booleanos).
function valueLabel(t: Translate, element: string, value: string): string {
  if (element === "user_status") {
    if (value === "NOT_IN_LIST") return t("tor.notInList");
    const label = t(`badge.${value}`);
    return label === `badge.${value}` ? value : label;
  }
  if (element === "media_status") {
    const label = t(`mstatus.${value}`);
    return label === `mstatus.${value}` ? value : label;
  }
  if (element === "local_available") return value === "true" ? t("common.yes") : t("common.no");
  return value;
}

export function TorrentsSettingsView() {
  const { t } = useApp();
  const [sources, setSources] = useState<TorrentSource[]>([]);
  const [filters, setFilters] = useState<TorrentFilter[]>([]);
  const [settings, setSettings] = useState<TorrentSettings | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [newSource, setNewSource] = useState<Omit<TorrentSource, "id">>(blankSource);
  const [draft, setDraft] = useState<FilterDraft | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [preset, setPreset] = useState(0);

  const elementLabel = (element: string) => t(`tor.el.${element}`);
  const opLabel = (op: string) => t(`tor.op.${op}`);
  const actionLabel = (action: string) => t(`tor.act.${action}`);
  const conditionSummary = (condition: TorrentCondition): string =>
    `${elementLabel(condition.element)} ${opLabel(condition.operator)} "${valueLabel(t, condition.element, condition.value)}"`;

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
    try { await api.updateTorrentSource(src.id, { name: src.name, url: src.url, enabled: !src.enabled, kind: src.kind }); await loadSources(); } catch (reason) { err(reason); }
  };
  const deleteSource = async (src: TorrentSource) => {
    if (!window.confirm(`${t("tor.deleteConfirm")} "${src.name}"?`)) return;
    try { await api.deleteTorrentSource(src.id); await loadSources(); } catch (reason) { err(reason); }
  };

  // Filters
  const saveDraft = async () => {
    if (!draft || !draft.name.trim() || draft.conditions.some((c) => !c.value.trim())) return;
    setError(null);
    try {
      if (editingId !== null) await api.updateTorrentFilter(editingId, draft);
      else await api.addTorrentFilter(draft);
      setDraft(null);
      setEditingId(null);
      await loadFilters();
    } catch (reason) { err(reason); }
  };
  const toggleFilter = async (f: TorrentFilter) => {
    const { id, ...rest } = f;
    try { await api.updateTorrentFilter(id, { ...rest, enabled: !f.enabled }); await loadFilters(); } catch (reason) { err(reason); }
  };
  const deleteFilter = async (f: TorrentFilter) => {
    if (!window.confirm(`${t("tor.deleteRuleConfirm")} "${f.name}"?`)) return;
    try { await api.deleteTorrentFilter(f.id); await loadFilters(); } catch (reason) { err(reason); }
  };
  const editFilter = (f: TorrentFilter) => {
    const { id, ...rest } = f;
    setEditingId(id);
    setDraft({ ...rest, conditions: rest.conditions.map((c) => ({ ...c })) });
  };
  const addPreset = () => {
    setEditingId(null);
    setDraft(PRESETS[preset]!.make(t));
  };

  const patchDraftCondition = (index: number, patch: Partial<TorrentCondition>) => {
    if (!draft) return;
    const conditions = draft.conditions.map((c, i) => (i === index ? { ...c, ...patch } : c));
    setDraft({ ...draft, conditions });
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
          <thead><tr><th>{t("tor.name")}</th><th>URL</th><th>{t("tor.active")}</th><th /></tr></thead>
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
              <td><input type="text" value={newSource.name} placeholder={t("tor.name")} onChange={(e) => setNewSource({ ...newSource, name: e.target.value })} /></td>
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
        <div className="torrent-filter-list">
          {filters.map((f) => (
            <article key={f.id} className={`torrent-filter${f.enabled ? "" : " disabled"}`}>
              <div className="torrent-filter-info">
                <strong>{f.name}</strong>
                <span>
                  {actionLabel(f.action)} · {f.match === "any" ? t("tor.anyCond") : t("tor.allCond")}
                  {f.scope === "limited" ? ` · ${f.anime_ids.length} anime(s)` : ""}
                </span>
                <small>{f.conditions.map(conditionSummary).join(" · ")}</small>
              </div>
              <div className="torrent-filter-actions">
                <button className={f.enabled ? "toggle enabled" : "toggle"} onClick={() => void toggleFilter(f)} aria-pressed={f.enabled}><i /></button>
                <button className="small" onClick={() => editFilter(f)}>{t("tor.edit")}</button>
                <button className="danger small" onClick={() => void deleteFilter(f)}>{t("torrents.delete")}</button>
              </div>
            </article>
          ))}
          {filters.length === 0 && <p className="local-assoc-empty">{t("tor.noRules")}</p>}
        </div>

        <div className="torrent-presets">
          <select value={preset} onChange={(e) => setPreset(Number(e.target.value))}>
            {PRESETS.map((p, i) => <option key={p.labelKey} value={i}>{t(p.labelKey)}</option>)}
          </select>
          <button className="small" onClick={addPreset}>{t("tor.usePreset")}</button>
          <button className="small" onClick={() => { setEditingId(null); setDraft(blankFilter()); }}>{t("tor.newRule")}</button>
        </div>

        {draft && (
          <div className="torrent-filter-editor">
            <div className="preference-fields">
              <label>{t("tor.name")}<input type="text" value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} /></label>
              <label>{t("tor.action")}
                <select value={draft.action} onChange={(e) => setDraft({ ...draft, action: e.target.value })}>
                  {ACTIONS.map((a) => <option key={a} value={a}>{actionLabel(a)}</option>)}
                </select>
              </label>
              <label>{t("tor.match")}
                <select value={draft.match} onChange={(e) => setDraft({ ...draft, match: e.target.value })}>
                  <option value="all">{t("tor.matchAll")}</option>
                  <option value="any">{t("tor.matchAny")}</option>
                </select>
              </label>
            </div>
            {draft.conditions.map((condition, index) => (
              <div className="torrent-condition-row" key={index}>
                <select value={condition.element} onChange={(e) => patchDraftCondition(index, { element: e.target.value, value: "" })}>
                  {ELEMENTS.map((el) => <option key={el} value={el}>{elementLabel(el)}</option>)}
                </select>
                <select value={condition.operator} onChange={(e) => patchDraftCondition(index, { operator: e.target.value })}>
                  {OPS.map((op) => <option key={op} value={op}>{opLabel(op)}</option>)}
                </select>
                {VALUE_OPTIONS[condition.element] ? (
                  <select value={condition.value} onChange={(e) => patchDraftCondition(index, { value: e.target.value })}>
                    <option value="">—</option>
                    {VALUE_OPTIONS[condition.element]!.map((v) => <option key={v} value={v}>{valueLabel(t, condition.element, v)}</option>)}
                  </select>
                ) : (
                  <input type="text" value={condition.value} placeholder={t("tor.value")} onChange={(e) => patchDraftCondition(index, { value: e.target.value })} />
                )}
                <button
                  className="small"
                  disabled={draft.conditions.length === 1}
                  onClick={() => setDraft({ ...draft, conditions: draft.conditions.filter((_, i) => i !== index) })}
                >✕</button>
              </div>
            ))}
            <div className="torrent-presets">
              <button className="small" onClick={() => setDraft({ ...draft, conditions: [...draft.conditions, { element: "title", operator: "contains", value: "" }] })}>{t("tor.addCond")}</button>
              <button className="primary small" onClick={() => void saveDraft()}>{editingId !== null ? t("tor.saveChanges") : t("tor.createRule")}</button>
              <button className="small" onClick={() => { setDraft(null); setEditingId(null); }}>{t("acc.cancel")}</button>
            </div>
          </div>
        )}
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
              <span>{t("tor.onNew")}</span>
              <select value={settings.on_new} onChange={(e) => void patchSettings({ on_new: e.target.value })}>
                <option value="notify">{t("tor.notifyOnly")}</option>
                <option value="download">{t("tor.autoDownload")}</option>
              </select>
            </label>
            <label className="preference-field">
              <span>{t("torrents.downloadMode")}</span>
              <select value={settings.download_mode} onChange={(e) => void patchSettings({ download_mode: e.target.value })}>
                <option value="magnet">Magnet</option>
                <option value="folder">{t("tor.folder")}</option>
              </select>
            </label>
            {settings.download_mode === "folder" && <>
              <label className="preference-field">
                <span>{t("torrents.watchFolder")}</span>
                <input type="text" value={settings.watch_folder} onChange={(e) => void patchSettings({ watch_folder: e.target.value })} />
              </label>
              <label className="checkbox-field">
                <input type="checkbox" checked={settings.use_anime_folder} onChange={(e) => void patchSettings({ use_anime_folder: e.target.checked })} />
                {t("tor.useAnimeFolder")}
              </label>
              <label className="checkbox-field">
                <input type="checkbox" checked={settings.folder_per_series} onChange={(e) => void patchSettings({ folder_per_series: e.target.checked })} />
                {t("tor.folderPerSeries")}
              </label>
              <label className="checkbox-field">
                <input type="checkbox" checked={settings.append_episode} onChange={(e) => void patchSettings({ append_episode: e.target.checked })} />
                {t("tor.appendEpisode")}
              </label>
            </>}
            {settings.download_mode === "magnet" && (
              <label className="preference-field">
                <span>{t("tor.clientPath")}</span>
                <input type="text" value={settings.client_path} placeholder={t("tor.clientPlaceholder")} onChange={(e) => void patchSettings({ client_path: e.target.value })} />
              </label>
            )}
            <label className="preference-field">
              <span>{t("torrents.preferredResolution")}</span>
              <input type="text" value={settings.preferred_resolution} onChange={(e) => void patchSettings({ preferred_resolution: e.target.value })} />
            </label>
            <label className="checkbox-field">
              <input type="checkbox" checked={settings.filters_enabled} onChange={(e) => void patchSettings({ filters_enabled: e.target.checked })} />
              {t("tor.applyRules")}
            </label>
            <label className="checkbox-field">
              <input type="checkbox" checked={settings.global_discard_not_in_list} onChange={(e) => void patchSettings({ global_discard_not_in_list: e.target.checked })} />
              {t("tor.discardNotInList")}
            </label>
            <label className="checkbox-field">
              <input type="checkbox" checked={settings.global_discard_seen} onChange={(e) => void patchSettings({ global_discard_seen: e.target.checked })} />
              {t("tor.onlyNew")}
            </label>
            <label className="checkbox-field">
              <input type="checkbox" checked={settings.global_prefer_resolution} onChange={(e) => void patchSettings({ global_prefer_resolution: e.target.checked })} />
              {t("tor.preferRes")}
            </label>
          </div>
        </div>
      )}
    </section>
  );
}
