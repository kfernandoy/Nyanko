import { useEffect, useMemo, useState } from "react";
import { api } from "./api";
import type { PlaybackEvent } from "./types";

const STATUS_LABELS: Record<PlaybackEvent["status"], string> = {
  pending: "Pendiente",
  confirmed: "Confirmado",
  ignored: "Ignorado",
  undone: "Deshecho",
  failed: "Fallido",
};

export function PlaybackHistoryView({ refreshKey, onSelect, onRefresh }: {
  refreshKey: number;
  onSelect: (mediaId: number) => void;
  onRefresh?: () => void;
}) {
  const [events, setEvents] = useState<PlaybackEvent[]>([]);
  const [status, setStatus] = useState("");
  const [source, setSource] = useState("");
  const [query, setQuery] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    api.playbackHistory(status || undefined, source || undefined, dateFrom || undefined, dateTo || undefined)
      .then((result) => { if (!cancelled) setEvents(result); })
      .catch((reason) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "No se pudo cargar el historial");
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
    if (!window.confirm("¿Borrar todo el historial local de reproducción?")) return;
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
      setError(reason instanceof Error ? reason.message : "No se pudo reintentar");
    }
  };

  return <section className="history-view">
    <p className="section-help">Registro local de lo que Nyanko detectó y de las actualizaciones confirmadas, ignoradas, deshechas o fallidas. No es tu historial de reproducción de AniList.</p>
    <div className="history-toolbar">
      <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Buscar en el historial…" />
      <select value={status} onChange={(event) => setStatus(event.target.value)}>
        <option value="">Todos los estados</option>
        <option value="confirmed">Confirmados</option>
        <option value="ignored">Ignorados</option>
        <option value="undone">Deshechos</option>
        <option value="pending">Pendientes</option>
        <option value="failed">Fallidos</option>
      </select>
      <select value={source} onChange={(event) => setSource(event.target.value)}>
        <option value="">Todos los reproductores</option>
        {sources.map((value) => <option key={value} value={value}>{value}</option>)}
      </select>
      <input type="date" value={dateFrom} max={dateTo || undefined} onChange={(event) => setDateFrom(event.target.value)} aria-label="Desde" />
      <input type="date" value={dateTo} min={dateFrom || undefined} onChange={(event) => setDateTo(event.target.value)} aria-label="Hasta" />
      <button className="danger" onClick={() => void clear()}>Borrar historial</button>
    </div>
    {loading ? <div className="empty"><strong>Cargando historial…</strong></div> : error ? (
      <div className="modal-error">{error}</div>
    ) : visible.length === 0 ? (
      <div className="empty"><strong>No hay eventos para estos filtros</strong></div>
    ) : <div className="history-list">{visible.map((event) => (
      <article
        key={event.id}
        className={`history-event ${event.media_id ? "clickable" : ""}`}
        onClick={() => event.media_id && onSelect(event.media_id)}
      >
        <span className={`history-status ${event.status}`}>{STATUS_LABELS[event.status]}</span>
        <div><strong>{event.anime_title ?? event.raw_title}</strong><small>{event.source}{event.episode ? ` · Episodio ${event.episode}` : ""}{event.error_message ? ` · ${event.error_message}` : ""}</small></div>
        <div className="history-progress">{event.progress_after != null ? `${event.progress_before ?? 0} → ${event.progress_after}` : "—"}</div>
        <time>{new Intl.DateTimeFormat("es", { dateStyle: "medium", timeStyle: "short" }).format(new Date(`${event.detected_at}Z`))}</time>
        {event.status === "failed" && (
          <button
            className="secondary"
            onClick={(e) => { e.stopPropagation(); void retry(event); }}
          >
            Reintentar
          </button>
        )}
      </article>
    ))}</div>}
  </section>;
}
