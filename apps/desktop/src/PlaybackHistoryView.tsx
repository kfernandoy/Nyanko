import { useEffect, useMemo, useState } from "react";
import { api } from "./api";
import { useApp } from "./i18n";
import type { PlaybackEvent } from "./types";

export function PlaybackHistoryView({ refreshKey, onSelect, onRefresh }: {
  refreshKey: number;
  onSelect: (mediaId: number) => void;
  onRefresh?: () => void;
}) {
  const { t, lang } = useApp();
  const [events, setEvents] = useState<PlaybackEvent[]>([]);
  const [status, setStatus] = useState("");
  const [source, setSource] = useState("");
  const [query, setQuery] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const statusLabels: Record<PlaybackEvent["status"], string> = {
    pending: t("hist.status.pending"),
    confirmed: t("hist.status.confirmed"),
    ignored: t("hist.status.ignored"),
    undone: t("hist.status.undone"),
    failed: t("hist.status.failed"),
  };

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    api.playbackHistory(status || undefined, source || undefined, dateFrom || undefined, dateTo || undefined)
      .then((result) => { if (!cancelled) setEvents(result); })
      .catch((reason) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : t("hist.loadError"));
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [dateFrom, dateTo, refreshKey, source, status]);

  const sources = useMemo(
    () => Array.from(new Set(events.map((event) => event.source))).sort(),
    [events],
  );
  const visible = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase();
    return events.filter((event) => !normalized ||
      (event.anime_title ?? event.raw_title).toLocaleLowerCase().includes(normalized));
  }, [events, query]);

  const clear = async () => {
    if (!window.confirm(t("hist.clearConfirm"))) return;
    await api.clearPlaybackHistory();
    setEvents([]);
  };

  const retry = async (event: PlaybackEvent) => {
    if (!event.media_id || event.progress_after == null) return;
    setError(null);
    try {
      await api.retryPlayback(event.id);
      onRefresh?.();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t("hist.retryError"));
    }
  };

  return <section className="history-view">
    <p className="section-help">{t("hist.help")}</p>
    <div className="history-toolbar">
      <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={t("hist.search")} />
      <select value={status} onChange={(event) => setStatus(event.target.value)}>
        <option value="">{t("hist.allStatuses")}</option>
        <option value="confirmed">{t("hist.f.confirmed")}</option>
        <option value="ignored">{t("hist.f.ignored")}</option>
        <option value="undone">{t("hist.f.undone")}</option>
        <option value="pending">{t("hist.f.pending")}</option>
        <option value="failed">{t("hist.f.failed")}</option>
      </select>
      <select value={source} onChange={(event) => setSource(event.target.value)}>
        <option value="">{t("hist.allSources")}</option>
        {sources.map((value) => <option key={value} value={value}>{value}</option>)}
      </select>
      <input type="date" value={dateFrom} max={dateTo || undefined} onChange={(event) => setDateFrom(event.target.value)} aria-label={t("hist.from")} />
      <input type="date" value={dateTo} min={dateFrom || undefined} onChange={(event) => setDateTo(event.target.value)} aria-label={t("hist.to")} />
      <button className="danger" onClick={() => void clear()}>{t("hist.clear")}</button>
    </div>
    {loading ? <div className="empty"><strong>{t("hist.loading")}</strong></div> : error ? (
      <div className="modal-error">{error}</div>
    ) : visible.length === 0 ? (
      <div className="empty"><strong>{t("hist.empty")}</strong></div>
    ) : <div className="history-list">{visible.map((event) => (
      <article
        key={event.id}
        className={`history-event ${event.media_id ? "clickable" : ""}`}
        onClick={() => event.media_id && onSelect(event.media_id)}
      >
        <span className={`history-status ${event.status}`}>{statusLabels[event.status]}</span>
        <div><strong>{event.anime_title ?? event.raw_title}</strong><small>{event.source}{event.episode ? ` · ${t("np.episode")} ${event.episode}` : ""}{event.error_message ? ` · ${event.error_message}` : ""}</small></div>
        <div className="history-progress">{event.progress_after != null ? `${event.progress_before ?? 0} → ${event.progress_after}` : "—"}</div>
        <time>{new Intl.DateTimeFormat(lang, { dateStyle: "medium", timeStyle: "short" }).format(new Date(`${event.detected_at}Z`))}</time>
        {event.status === "failed" && (
          <button
            className="secondary"
            onClick={(e) => { e.stopPropagation(); void retry(event); }}
          >
            {t("hist.retry")}
          </button>
        )}
      </article>
    ))}</div>}
  </section>;
}
