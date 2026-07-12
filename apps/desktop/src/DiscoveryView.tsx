import { useEffect, useState } from "react";
import { api } from "./api";
import { useApp, mediaFormatLabel } from "./i18n";
import type { SearchFilters, SearchResult } from "./types";

const ANIME_FORMATS = ["TV", "TV_SHORT", "MOVIE", "SPECIAL", "OVA", "ONA"];
const MANGA_FORMATS = ["MANGA", "NOVEL", "ONE_SHOT"];
const STATUSES = ["RELEASING", "FINISHED", "NOT_YET_RELEASED", "CANCELLED", "HIATUS"];
const GENRES = [
  "Action", "Adventure", "Comedy", "Drama", "Ecchi", "Fantasy", "Horror",
  "Mahou Shoujo", "Mecha", "Music", "Mystery", "Psychological", "Romance",
  "Sci-Fi", "Slice of Life", "Sports", "Supernatural", "Thriller",
];
const ADULT_GENRES = ["Hentai"];
const SEASONS = ["WINTER", "SPRING", "SUMMER", "FALL"];
const YEAR_OPTIONS = Array.from({ length: Math.max(0, new Date().getFullYear() + 3 - 1970) }, (_, i) => new Date().getFullYear() + 2 - i);

const DEFAULT_FILTERS: SearchFilters = {
  query: "",
  page: 1,
  per_page: 50,
  genre: null,
  format: null,
  year: null,
  season: null,
  status: null,
  is_adult: false,
  media_type: "ANIME",
  sort: "POPULARITY",
};

type MediaType = "ANIME" | "MANGA";

function airingStatusLabel(t: (key: string) => string, status: string | null): string | null {
  if (!status) return null;
  const label = t(`mstatus.${status}`);
  return label === `mstatus.${status}` ? status : label;
}

function resultSubtitle(t: (key: string) => string, item: SearchResult, mediaType: MediaType): string {
  const parts: (string | null)[] = [item.format ? mediaFormatLabel(t, item.format) : null, airingStatusLabel(t, item.status)];
  if (mediaType === "ANIME") {
    parts.push(item.episodes ? `${item.episodes} eps` : null);
  } else {
    parts.push(item.chapters ? `${item.chapters} caps` : null, item.volumes ? `${item.volumes} vols` : null);
  }
  parts.push(item.average_score ? `${item.average_score}%` : null);
  return parts.filter(Boolean).join(" · ");
}

function listStatusLabel(t: (key: string) => string, status: string, mediaType: MediaType): string {
  if (status === "CURRENT" && mediaType === "MANGA") return t("filter.reading");
  const label = t(`badge.${status}`);
  return label === `badge.${status}` ? status : label;
}

export function DiscoveryView({
  onSelect,
  provider,
  displayAdult,
  animeStatuses,
  mangaStatuses,
  onMediaTypeChange,
  onAdded,
}: {
  onSelect: (mediaId: number, mediaType: MediaType) => void;
  provider: string;
  displayAdult: boolean;
  animeStatuses: Map<number, string>;
  mangaStatuses: Map<number, string>;
  onMediaTypeChange?: (mediaType: MediaType) => void;
  onAdded?: (item: SearchResult, mediaType: MediaType, status: string) => Promise<void> | void;
}) {
  const { t } = useApp();
  const [filters, setFilters] = useState<SearchFilters>(DEFAULT_FILTERS);

  useEffect(() => { setFilters(DEFAULT_FILTERS); }, [provider]);
  const [results, setResults] = useState<SearchResult[]>([]);
  const [hasNextPage, setHasNextPage] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState<{ id: number; status: string } | null>(null);
  const [addError, setAddError] = useState<string | null>(null);
  const [wontWatch, setWontWatch] = useState<Set<string>>(new Set());
  const [showMarked, setShowMarked] = useState(true);
  const [hideLibraryItems, setHideLibraryItems] = useState(false);
  const [localStatuses, setLocalStatuses] = useState<Record<string, string>>({});

  useEffect(() => { setLocalStatuses({}); }, [provider]);

  useEffect(() => {
    let cancelled = false;
    void api.wontWatch().then((state) => {
      if (cancelled) return;
      setWontWatch(new Set(state.items.map((it) => it.external_id)));
      setShowMarked(state.show_marked);
    }).catch(() => {});
    return () => { cancelled = true; };
  }, [provider]);

  const toggleWontWatch = async (item: SearchResult) => {
    const id = String(item.id);
    const next = new Set(wontWatch);
    try {
      if (next.has(id)) {
        await api.removeWontWatch(item.id);
        next.delete(id);
      } else {
        await api.addWontWatch(item.id, item.title, item.cover_image);
        next.add(id);
      }
      setWontWatch(next);
    } catch (reason) {
      setAddError(reason instanceof Error ? reason.message : t("discover.updateError"));
    }
  };

  const toggleShowMarked = async () => {
    const next = !showMarked;
    setShowMarked(next);
    try { await api.setDiscoverShowMarked(next); } catch { /* keep optimistic */ }
  };

  const mediaType = filters.media_type;
  const isAnime = mediaType === "ANIME";
  const formats = isAnime ? ANIME_FORMATS : MANGA_FORMATS;
  const libraryStatuses = mediaType === "ANIME" ? animeStatuses : mangaStatuses;
  const visibleResults = results.filter((item) => {
    const marked = wontWatch.has(String(item.id));
    const libraryStatus = localStatuses[item.id] ?? libraryStatuses.get(item.id);
    return !(marked && !showMarked) && !(libraryStatus && hideLibraryItems);
  });

  const search = async (nextFilters: SearchFilters) => {
    setLoading(true);
    setError(null);
    try {
      const response = await api.discover(nextFilters);
      setResults(response.results);
      setHasNextPage(response.has_next_page);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t("discover.searchError"));
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
  }, [filters.query, filters.page, filters.genre, filters.format, filters.year, filters.season, filters.status, filters.is_adult, filters.media_type, filters.sort]);

  // if the profile stops allowing adult content, drop any active adult filter/genre
  useEffect(() => {
    if (!displayAdult) setFilters((previous) => {
      const adultGenre = ADULT_GENRES.includes(previous.genre ?? "");
      if (!previous.is_adult && !adultGenre) return previous;
      return { ...previous, is_adult: false, genre: adultGenre ? null : previous.genre, page: 1 };
    });
  }, [displayAdult]);

  const updatePage = (offset: number) => {
    setFilters((previous) => ({ ...previous, page: Math.max(1, previous.page + offset) }));
  };

  const update = (partial: Partial<SearchFilters>) => {
    setFilters((previous) => ({ ...previous, page: 1, ...partial }));
  };

  const setMediaType = (next: MediaType) => {
    onMediaTypeChange?.(next);
    setFilters((previous) => ({
      ...previous,
      page: 1,
      media_type: next,
      format: null,
      year: previous.year,
      season: null,
      status: null,
      genre: null,
      is_adult: false,
    }));
  };

  const addToList = async (item: SearchResult, status: string) => {
    setAdding({ id: item.id, status });
    setAddError(null);
    try {
      await api.editEntry(item.id, { status, progress: 0 }, mediaType);
      setLocalStatuses((current) => ({ ...current, [item.id]: status }));
      await onAdded?.(item, mediaType, status);
    } catch (reason) {
      setAddError(reason instanceof Error ? reason.message : t("discover.addError"));
    } finally {
      setAdding(null);
    }
  };

  return (
    <section className="discovery-view">
      <div className="discovery-toolbar">
        <select value={mediaType} onChange={(event) => setMediaType(event.target.value as MediaType)}>
          <option value="ANIME">{t("discover.anime")}</option>
          <option value="MANGA">{t("discover.manga")}</option>
        </select>
        <input
          value={filters.query}
          onChange={(event) => update({ query: event.target.value })}
          placeholder={isAnime ? t("discover.search.anime") : t("discover.search.manga")}
        />
        <select
          value={filters.sort}
          onChange={(event) => update({ sort: event.target.value as "POPULARITY" | "SCORE" })}
        >
          <option value="POPULARITY">{t("discover.sort.popularity")}</option>
          <option value="SCORE">{t("discover.sort.score")}</option>
        </select>
        <select value={filters.format ?? ""} onChange={(event) => update({ format: event.target.value || null })}>
          <option value="">{t("discover.format.any")}</option>
          {formats.map((value) => <option key={value} value={value}>{mediaFormatLabel(t, value)}</option>)}
        </select>
        <select value={filters.status ?? ""} onChange={(event) => update({ status: event.target.value || null })}>
          <option value="">{t("discover.status.any")}</option>
          {STATUSES.map((value) => <option key={value} value={value}>{t(`mstatus.${value}`)}</option>)}
        </select>
        <select value={filters.year ?? ""} onChange={(event) => update({ year: event.target.value ? Number(event.target.value) : null })}>
          <option value="">{t("discover.year")}</option>
          {YEAR_OPTIONS.map((year) => <option key={year} value={year}>{year}</option>)}
        </select>
        {isAnime && provider === "anilist" && (
          <select value={filters.season ?? ""} onChange={(event) => update({ season: event.target.value || null })}>
            <option value="">{t("discover.season.any")}</option>
            {SEASONS.map((value) => <option key={value} value={value}>{t(`season.${value.toLowerCase()}`)}</option>)}
          </select>
        )}
        <select value={filters.genre ?? ""} onChange={(event) => update({ genre: event.target.value || null })}>
          <option value="">{t("discover.genre.any")}</option>
          {(filters.is_adult ? [...GENRES, ...ADULT_GENRES] : GENRES).map((value) => <option key={value} value={value}>{value}</option>)}
        </select>
        {displayAdult && (
          <label className="discovery-adult">
            <input
              type="checkbox"
              checked={filters.is_adult}
              onChange={(event) => update(event.target.checked ? { is_adult: true } : { is_adult: false, genre: ADULT_GENRES.includes(filters.genre ?? "") ? null : filters.genre })}
            />
            {t("discover.adult")}
          </label>
        )}
        <label className="discovery-adult">
          <input type="checkbox" checked={showMarked} onChange={() => void toggleShowMarked()} />
          {t("discover.showWontWatch")}
        </label>
        <label className="discovery-adult">
          <input type="checkbox" checked={hideLibraryItems} onChange={(event) => setHideLibraryItems(event.target.checked)} />
          {t("discover.hideLibrary")}
        </label>
      </div>
      {error && <div className="modal-error">{error}</div>}
      {addError && <div className="modal-error">{addError}</div>}
      {loading ? (
        <div className="empty"><strong>{t("discover.loading")}</strong></div>
      ) : visibleResults.length === 0 ? (
        <div className="empty"><strong>{t("discover.empty")}</strong></div>
      ) : (
        <>
          <div className="discovery-grid">
            {visibleResults.map((item) => {
              const marked = wontWatch.has(String(item.id));
              const libraryStatus = localStatuses[item.id] ?? libraryStatuses.get(item.id);
              return (
              <article
                key={item.id}
                className={marked ? "discovery-card wont-watch" : "discovery-card"}
                onClick={() => onSelect(item.id, mediaType)}
              >
                {item.cover_image && <img src={item.cover_image} alt="" loading="lazy" />}
                <div>
                  <strong>{item.title}</strong>
                  <small>{resultSubtitle(t, item, mediaType)}</small>
                  {libraryStatus ? (
                    <div className="discovery-library-status" title={listStatusLabel(t, libraryStatus, mediaType)}>
                      {listStatusLabel(t, libraryStatus, mediaType)}
                    </div>
                  ) : <div className="discovery-semaphore" onClick={(event) => event.stopPropagation()}>
                    <button
                      className="sem sem-watch"
                      title={isAnime ? t("discover.add.watching") : t("discover.add.reading")}
                      aria-label={isAnime ? t("discover.add.watching") : t("discover.add.reading")}
                      disabled={adding?.id === item.id && adding?.status === "CURRENT"}
                      onClick={() => void addToList(item, "CURRENT")}
                    >
                      ▶
                    </button>
                    <button
                      className="sem sem-plan"
                      title={t("discover.add.planning")}
                      aria-label={t("discover.add.planning")}
                      disabled={adding?.id === item.id && adding?.status === "PLANNING"}
                      onClick={() => void addToList(item, "PLANNING")}
                    >
                      ＋
                    </button>
                    <button
                      className={marked ? "sem sem-skip active" : "sem sem-skip"}
                      title={marked ? t("discover.wontWatch.remove") : t("discover.wontWatch")}
                      aria-label={marked ? t("discover.wontWatch.remove") : t("discover.wontWatch")}
                      onClick={() => void toggleWontWatch(item)}
                    >
                      ✕
                    </button>
                  </div>}
                </div>
              </article>
              );
            })}
          </div>
          <div className="discovery-pagination">
            <button disabled={filters.page <= 1 || loading} onClick={() => updatePage(-1)}>{t("discover.prev")}</button>
            <span>{t("discover.page")} {filters.page}</span>
            <button disabled={!hasNextPage || loading} onClick={() => updatePage(1)}>{t("discover.next")}</button>
          </div>
        </>
      )}
    </section>
  );
}
