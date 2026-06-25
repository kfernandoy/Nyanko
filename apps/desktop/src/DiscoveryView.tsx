import { useEffect, useState } from "react";
import { api } from "./api";
import type { SearchFilters, SearchResult } from "./types";

const ANIME_FORMATS = ["TV", "TV_SHORT", "MOVIE", "SPECIAL", "OVA", "ONA"];
const MANGA_FORMATS = ["MANGA", "NOVEL", "ONE_SHOT"];
const STATUSES = ["RELEASING", "FINISHED", "NOT_YET_RELEASED", "CANCELLED", "HIATUS"];

const DEFAULT_FILTERS: SearchFilters = {
  query: "",
  page: 1,
  per_page: 20,
  genre: null,
  format: null,
  year: null,
  status: null,
  is_adult: false,
  media_type: "ANIME",
  sort: "POPULARITY",
};

type MediaType = "ANIME" | "MANGA";

function formatLabel(format: string | null): string | null {
  return format ? format.replace("_", " ") : null;
}

function resultSubtitle(item: SearchResult, mediaType: MediaType): string {
  const parts: (string | null)[] = [formatLabel(item.format), item.status];
  if (mediaType === "ANIME") {
    parts.push(item.episodes ? `${item.episodes} eps` : null);
  } else {
    parts.push(item.chapters ? `${item.chapters} caps` : null, item.volumes ? `${item.volumes} vols` : null);
  }
  parts.push(item.average_score ? `${item.average_score}%` : null);
  return parts.filter(Boolean).join(" · ");
}

export function DiscoveryView({ onSelect }: { onSelect: (mediaId: number, mediaType: MediaType) => void }) {
  const [filters, setFilters] = useState<SearchFilters>(DEFAULT_FILTERS);
  const [results, setResults] = useState<SearchResult[]>([]);
  const [hasNextPage, setHasNextPage] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState<{ id: number; status: string } | null>(null);
  const [addError, setAddError] = useState<string | null>(null);

  const mediaType = filters.media_type;
  const isAnime = mediaType === "ANIME";
  const formats = isAnime ? ANIME_FORMATS : MANGA_FORMATS;

  const search = async (nextFilters: SearchFilters) => {
    setLoading(true);
    setError(null);
    try {
      const response = await api.discover(nextFilters);
      setResults(response.results);
      setHasNextPage(response.has_next_page);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudo buscar");
      setResults([]);
      setHasNextPage(false);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void search(filters);
    }, 300);
    return () => window.clearTimeout(timer);
  }, [filters.query, filters.page, filters.genre, filters.format, filters.year, filters.status, filters.is_adult, filters.media_type, filters.sort]);

  const updatePage = (offset: number) => {
    setFilters((previous) => ({ ...previous, page: Math.max(1, previous.page + offset) }));
  };

  const update = (partial: Partial<SearchFilters>) => {
    setFilters((previous) => ({ ...previous, page: 1, ...partial }));
  };

  const setMediaType = (next: MediaType) => {
    setFilters((previous) => ({
      ...previous,
      page: 1,
      media_type: next,
      format: null,
      year: next === "MANGA" ? null : previous.year,
      status: null,
      genre: null,
      is_adult: false,
    }));
  };

  const addToList = async (item: SearchResult, status: string) => {
    setAdding({ id: item.id, status });
    setAddError(null);
    try {
      await api.editEntry(item.id, { status, progress: 0 });
    } catch (reason) {
      setAddError(reason instanceof Error ? reason.message : "No se pudo añadir");
    } finally {
      setAdding(null);
    }
  };

  return (
    <section className="discovery-view">
      <div className="discovery-toolbar">
        <select value={mediaType} onChange={(event) => setMediaType(event.target.value as MediaType)}>
          <option value="ANIME">Anime</option>
          <option value="MANGA">Manga</option>
        </select>
        <input
          value={filters.query}
          onChange={(event) => update({ query: event.target.value })}
          placeholder={isAnime ? "Buscar anime…" : "Buscar manga…"}
        />
        <select
          value={filters.sort}
          onChange={(event) => update({ sort: event.target.value as "POPULARITY" | "SCORE" })}
        >
          <option value="POPULARITY">Más popular</option>
          <option value="SCORE">Mejor valorado</option>
        </select>
        <select value={filters.format ?? ""} onChange={(event) => update({ format: event.target.value || null })}>
          <option value="">Cualquier formato</option>
          {formats.map((value) => <option key={value} value={value}>{value.replace("_", " ")}</option>)}
        </select>
        <select value={filters.status ?? ""} onChange={(event) => update({ status: event.target.value || null })}>
          <option value="">Cualquier estado</option>
          {STATUSES.map((value) => <option key={value} value={value}>{value.replace("_", " ")}</option>)}
        </select>
        {isAnime && (
          <input
            type="number"
            value={filters.year ?? ""}
            onChange={(event) => update({ year: event.target.value ? Number(event.target.value) : null })}
            placeholder="Año"
            min={1970}
            max={2099}
          />
        )}
        <input
          value={filters.genre ?? ""}
          onChange={(event) => update({ genre: event.target.value || null })}
          placeholder="Género"
        />
        <label className="discovery-adult">
          <input
            type="checkbox"
            checked={filters.is_adult}
            onChange={(event) => update({ is_adult: event.target.checked })}
          />
          Incluir adulto
        </label>
      </div>
      {error && <div className="modal-error">{error}</div>}
      {addError && <div className="modal-error">{addError}</div>}
      {loading ? (
        <div className="empty"><strong>Buscando…</strong></div>
      ) : results.length === 0 ? (
        <div className="empty"><strong>No se encontraron resultados</strong></div>
      ) : (
        <>
          <div className="discovery-grid">
            {results.map((item) => (
              <article
                key={item.id}
                className="discovery-card"
                onClick={() => onSelect(item.id, mediaType)}
              >
                {item.cover_image && <img src={item.cover_image} alt="" loading="lazy" />}
                <div>
                  <strong>{item.title}</strong>
                  <small>{resultSubtitle(item, mediaType)}</small>
                  <div className="discovery-actions" onClick={(event) => event.stopPropagation()}>
                    <button
                      className="primary small"
                      disabled={adding?.id === item.id && adding?.status === "CURRENT"}
                      onClick={() => void addToList(item, "CURRENT")}
                    >
                      {isAnime ? "Añadir a Viendo" : "Añadir a Leyendo"}
                    </button>
                    <button
                      className="small"
                      disabled={adding?.id === item.id && adding?.status === "PLANNING"}
                      onClick={() => void addToList(item, "PLANNING")}
                    >
                      A Planeados
                    </button>
                  </div>
                </div>
              </article>
            ))}
          </div>
          <div className="discovery-pagination">
            <button disabled={filters.page <= 1 || loading} onClick={() => updatePage(-1)}>Anterior</button>
            <span>Página {filters.page}</span>
            <button disabled={!hasNextPage || loading} onClick={() => updatePage(1)}>Siguiente</button>
          </div>
        </>
      )}
    </section>
  );
}
