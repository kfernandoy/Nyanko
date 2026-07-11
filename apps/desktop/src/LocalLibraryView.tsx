import { useEffect, useMemo, useState } from "react";
import { native } from "./native";
import { useApp, mediaFormatLabel } from "./i18n";
import { api } from "./api";
import { useContextMenu, type CtxItem } from "./ContextMenu";
import { useCompact } from "./hooks";
import { displayTitle } from "./title";
import type { LocalSeries, SearchResult } from "./types";

const LIST_STATUSES = ["PLANNING", "CURRENT", "COMPLETED", "PAUSED", "DROPPED"] as const;
type LocalLayout = "grid" | "list";

export function LocalLibraryView({ onBack, onSelect }: { onBack: () => void; onSelect: (series: LocalSeries) => void }) {
  const { t, titleLanguage } = useApp();
  const compact = useCompact();
  const [items, setItems] = useState<LocalSeries[]>([]);
  const [loading, setLoading] = useState(true);
  const [layout, setLayout] = useState<LocalLayout>(() => (localStorage.getItem("local-layout") as LocalLayout) || "grid");
  const setLayoutPersist = (next: LocalLayout) => { setLayout(next); localStorage.setItem("local-layout", next); };
  const [assocSeries, setAssocSeries] = useState<LocalSeries | null>(null);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [status, setStatus] = useState<string>("PLANNING");
  const [busy, setBusy] = useState(false);

  const statusLabels = useMemo<Record<string, string>>(() => ({
    PLANNING: t("filter.planning"),
    CURRENT: t("filter.watching"),
    COMPLETED: t("filter.completed"),
    PAUSED: t("filter.paused"),
    DROPPED: t("filter.dropped"),
  }), [t]);

  const load = () => api.getLocalLibrary().then((d) => setItems(d)).catch(() => {}).finally(() => setLoading(false));
  useEffect(() => { void load(); }, []);

  // Búsqueda en el catálogo del proveedor activo (como Descubrir), con debounce.
  useEffect(() => {
    const q = query.trim();
    if (assocSeries === null || q.length < 2) { setResults([]); return; }
    const timer = setTimeout(() => {
      setSearching(true);
      api.searchGlobal(q)
        .then((r) => setResults(r.results.slice(0, 10)))
        .catch(() => setResults([]))
        .finally(() => setSearching(false));
    }, 400);
    return () => clearTimeout(timer);
  }, [query, assocSeries]);

  const openAssociate = (series: LocalSeries) => {
    setAssocSeries(series);
    // Precargar el título de la serie: si el catálogo la tiene con ese nombre exacto,
    // el match aparece de inmediato sin escribir nada.
    setQuery(series.title);
    setResults([]);
  };

  const closeAssociate = () => {
    setAssocSeries(null);
    setQuery("");
    setResults([]);
  };

  const associate = async (series: LocalSeries, target: SearchResult | null) => {
    setBusy(true);
    try {
      await api.associateLocal({
        title: series.title,
        from_media_id: series.media_id,
        external_id: target ? target.id : null,
        status: target ? status : null,
        media: target,
      });
      closeAssociate();
      await load();
    } catch {
      // el backend informa por HTTP; sin cambios locales que revertir
    } finally {
      setBusy(false);
    }
  };

  // Respetar el idioma de títulos que el usuario configuró para el proveedor.
  const shown = useMemo(
    () => items.map((s) => ({ ...s, title: displayTitle(s, titleLanguage) })),
    [items, titleLanguage],
  );

  const { openMenu, menu } = useContextMenu();
  const seriesMenu = (s: LocalSeries): CtxItem[] => [
    ...(s.external_id != null ? [{ label: t("ctx.info"), onClick: () => onSelect(s) }] : []),
    ...(s.next_path ? [
      {
        label: `${t("np.local.play")}${s.next_episode != null ? ` · ${t("np.local.episode")} ${s.next_episode}` : ""}`,
        onClick: () => void native.openPath(s.next_path!),
      },
      { label: t("ctx.openFolder"), onClick: () => void native.revealItemInDir(s.next_path!) },
    ] : []),
    { sep: true } as CtxItem,
    { label: s.matched ? t("local.fixMatch") : t("local.associate"), onClick: () => openAssociate(s) },
    ...(s.matched ? [{ label: t("local.unlink"), danger: true, onClick: () => void associate(s, null) }] : []),
  ];

  return (
    <section className="local-library">
      <header className="local-library-header">
        <button className="small" onClick={onBack}>← {t("local.back")}</button>
        {!compact && <div className="layout-toggle">
          <button className={layout === "grid" ? "active" : ""} title={t("lib.layout.grid")} onClick={() => setLayoutPersist("grid")}>▦</button>
          <button className={layout === "list" ? "active" : ""} title={t("lib.layout.list")} onClick={() => setLayoutPersist("list")}>☰</button>
        </div>}
      </header>
      {loading && <p className="empty">{t("local.loading")}</p>}
      {!loading && items.length === 0 && <p className="empty">{t("local.empty")}</p>}
      {layout === "grid" && !compact ? (
      <section className="media-grid">
        {shown.map((s, i) => {
          const percentage = s.progress != null && s.episodes ? Math.min(100, s.progress / s.episodes * 100) : null;
          return (
            <article
              key={s.media_id ?? `u-${s.title}-${i}`}
              className={`media-card${s.external_id != null ? " clickable" : ""}`}
              onClick={s.external_id != null ? () => onSelect(s) : undefined}
              onContextMenu={(e) => openMenu(e, seriesMenu(s))}
            >
              <div className="poster" style={s.cover_image ? { backgroundImage: `url(${s.cover_image})` } : undefined}>
                {s.next_path && (
                  <button
                    className="pending-local-play poster-play"
                    title={`${t("np.local.play")}${s.next_episode != null ? ` · ${t("np.local.episode")} ${s.next_episode}` : ""}`}
                    onClick={(e) => { e.stopPropagation(); void native.openPath(s.next_path!); }}
                  >▶</button>
                )}
              </div>
              <div className="media-info">
                <strong title={s.title}>{s.title}</strong>
                <span>
                  {s.progress != null ? `${s.progress} / ${s.episodes ?? "?"} · ` : ""}
                  {s.episode_count} {t("local.episodes")}
                  {!s.matched ? ` · ${t("local.unmatched")}` : ""}
                </span>
                {percentage != null && <div className="progress"><i style={{ width: `${percentage}%` }} /></div>}
                <button
                  className="small local-associate"
                  onClick={(e) => { e.stopPropagation(); openAssociate(s); }}
                >{s.matched ? t("local.fixMatch") : t("local.associate")}</button>
              </div>
            </article>
          );
        })}
      </section>
      ) : (
      <section className="media-list">
        {shown.map((s, i) => (
          <article
            key={s.media_id ?? `u-${s.title}-${i}`}
            className="media-row"
            onClick={s.external_id != null ? () => onSelect(s) : undefined}
            onContextMenu={(e) => openMenu(e, seriesMenu(s))}
          >
            {s.cover_image ? <img src={s.cover_image} alt="" loading="lazy" /> : <div className="media-row-noimg" />}
            <div className="media-row-main">
              <strong>{s.title}</strong>
              <small>
                {s.episode_count} {t("local.episodes")}
                {!s.matched ? ` · ${t("local.unmatched")}` : ""}
              </small>
            </div>
            <span className="media-row-progress">{s.progress != null ? `${s.progress} / ${s.episodes ?? "?"}` : "—"}</span>
            <div className="media-row-actions" onClick={(e) => e.stopPropagation()}>
              {s.next_path && (
                <button
                  className="row-plus"
                  title={`${t("np.local.play")}${s.next_episode != null ? ` · ${t("np.local.episode")} ${s.next_episode}` : ""}`}
                  onClick={() => void native.openPath(s.next_path!)}
                >▶</button>
              )}
              <button className="row-edit" title={s.matched ? t("local.fixMatch") : t("local.associate")} onClick={() => openAssociate(s)}>⚲</button>
            </div>
          </article>
        ))}
      </section>
      )}
      {menu}
      {assocSeries && (
        <div className="modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && closeAssociate()}>
          <section className="local-assoc-modal">
            <button className="modal-close" onClick={closeAssociate} aria-label={t("detail.close")}>×</button>
            <p className="eyebrow">{assocSeries.matched ? t("local.fixMatch") : t("local.associate")}</p>
            <h3>{assocSeries.title}</h3>
            <input
              autoFocus
              placeholder={t("local.searchCatalog")}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onFocus={(e) => e.currentTarget.select()}
            />
            <label className="local-assoc-status">
              {t("local.statusIfAdded")}
              <select value={status} onChange={(e) => setStatus(e.target.value)}>
                {LIST_STATUSES.map((value) => (
                  <option key={value} value={value}>{statusLabels[value]}</option>
                ))}
              </select>
            </label>
            <div className="local-assoc-results">
              {searching && <p className="local-assoc-empty">{t("local.loading")}</p>}
              {!searching && query.trim().length >= 2 && results.length === 0 && (
                <p className="local-assoc-empty">{t("local.noResults")}</p>
              )}
              {results.map((m) => (
                <button
                  key={m.id}
                  className="local-assoc-result"
                  disabled={busy}
                  onClick={() => void associate(assocSeries, m)}
                >
                  <i style={m.cover_image ? { backgroundImage: `url(${m.cover_image})` } : undefined} />
                  <span>
                    <strong>{m.title}</strong>
                    <small>{[m.format ? mediaFormatLabel(t, m.format) : null, m.year, m.episodes ? `${m.episodes} ep` : null].filter(Boolean).join(" · ")}</small>
                  </span>
                </button>
              ))}
            </div>
            {assocSeries.matched && (
              <button className="small local-assoc-unlink" disabled={busy} onClick={() => void associate(assocSeries, null)}>
                {t("local.unlink")}
              </button>
            )}
          </section>
        </div>
      )}
    </section>
  );
}
