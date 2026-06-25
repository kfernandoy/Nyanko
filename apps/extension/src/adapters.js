(function registerNyankoAdapters(global) {
  const text = (selector) => document.querySelector(selector)?.textContent?.trim() || null;
  const meta = (selector) => document.querySelector(selector)?.content?.trim() || null;

  function classifyContent(title, durationSeconds, episode) {
    if (!title) return "unknown";
    const normalized = title.toLowerCase();
    const hasEpisode = episode !== null && episode !== undefined;

    // Trailers, teasers and promotional material
    if (/\b(trailer|teaser|avance|previa)\b/.test(normalized)) return "trailer";
    if (/\b(pv\s*\d*|promo\s*\d*)\b/.test(normalized)) return "trailer";
    if (/\b(creditless opening|opening|op\s*\d*)\b/.test(normalized)) return "opening";
    if (/\b(creditless ending|ending|ed\s*\d*)\b/.test(normalized)) return "ending";
    if (/\b(sneak peek|preview|adelanto|vistazo)\b/.test(normalized)) return "preview";

    // Short content is usually a preview unless it has a clear episode number
    if (durationSeconds && durationSeconds < 45) return "preview";
    if (durationSeconds && durationSeconds < 90 && !hasEpisode) return "preview";

    return "unknown";
  }

  function parseEpisodeFromTitle(title) {
    if (!title) return { season: null, episode: null };

    const patterns = [
      // Season 2 Episode 5, Season2 Ep5, Temporada 2 Episodio 5
      /(?:season|temporada|saison)\s*(\d+).*?(?:episode|episodio|ep\.?|folge|cap[ií]tulo|cap)[\s#:.-]*(\d+(?:\.5)?)/i,
      // S02E05, S2 E5, S2E5
      /\bS(\d{1,2})\s*E\s*(\d+(?:\.5)?)\b/i,
      // Episode 5, Ep.5, Ep 5, E5, #5, Capítulo 5
      /(?:episode|episodio|ep\.?|cap[ií]tulo|cap|folge|ep)[\s#:.-]*(\d+(?:\.5)?)\b/i,
      // 5 - Title, 5: Title, #5 - Title
      /^\s*(\d+(?:\.5)?)\s*[\-:–]\s+/i,
    ];

    for (const pattern of patterns) {
      const match = title.match(pattern);
      if (!match) continue;
      if (match.length === 3) {
        return { season: Number(match[1]) || null, episode: parseFloat(match[2]) || null };
      }
      return { season: null, episode: parseFloat(match[1]) || null };
    }

    // Double episodes like "5-6" or "5~6" at the start
    const doubleMatch = title.match(/^\s*(\d+(?:\.5)?)\s*[\-~]\s*(\d+(?:\.5)?)\b/);
    if (doubleMatch) {
      return { season: null, episode: parseFloat(doubleMatch[1]) || null };
    }

    return { season: null, episode: null };
  }

  function collectJsonLd() {
    const results = [];
    for (const node of document.querySelectorAll("script")) {
      const body = node.textContent || "";
      const type = node.type || node.getAttribute?.("type") || "";
      if (type !== "application/ld+json" && !body.includes("episodeNumber")) continue;
      try {
        const parsed = JSON.parse(body);
        const queue = Array.isArray(parsed) ? [...parsed] : [parsed];
        while (queue.length) {
          const value = queue.shift();
          if (!value || typeof value !== "object") continue;
          if (value["@graph"]) queue.push(...value["@graph"]);
          for (const child of Object.values(value)) {
            if (child && typeof child === "object") queue.push(child);
          }
          results.push(value);
        }
      } catch { /* Ignore invalid page-owned JSON-LD. */ }
    }
    return results;
  }

  function isMediaObject(value) {
    if (!value) return false;
    if (value.episodeNumber != null && (value.partOfSeries || value.seriesTitle || value.series_title)) return true;
    if (!value["@type"]) return false;
    const types = Array.isArray(value["@type"]) ? value["@type"] : [value["@type"]];
    return types.some((type) =>
      ["VideoObject", "TVEpisode", "Episode", "Movie", "MovieClip"].includes(type)
    );
  }

  function findStructuredMedia() {
    const all = collectJsonLd();
    // Prefer objects that look like an episode
    const withEpisode = all.find((value) => isMediaObject(value) && value.episodeNumber != null);
    if (withEpisode) return withEpisode;
    return all.find(isMediaObject) || null;
  }

  function resolveName(value) {
    if (!value) return null;
    if (typeof value === "string") return value;
    return value.name || null;
  }

  function extractFromStructuredMedia(video) {
    const data = findStructuredMedia();
    if (!data) return null;

    const seriesName = resolveName(data.partOfSeries) ||
      resolveName(data.partOfSeason?.partOfSeries) ||
      data.seriesTitle ||
      data.series_title ||
      null;
    const season = data.partOfSeason?.seasonNumber ?? null;
    const episode = data.episodeNumber ?? null;
    const rawTitle = data.name || meta('meta[property="og:title"]') ||
      meta('meta[name="twitter:title"]') || document.title.trim();
    const animeTitle = seriesName && Number(season) > 1 ? `${seriesName} Season ${Number(season)}` : seriesName;

    return {
      rawTitle,
      animeTitle,
      season: season !== null ? Number(season) : null,
      episode: episode !== null ? parseFloat(episode) : null,
      contentKind: episode != null ? "episode" : classifyContent(rawTitle, video?.duration, episode),
      siteIdentifier: genericSiteIdentifier(),
      searchHints: [],
    };
  }

  function detectFromMetadata(video) {
    const rawTitle = meta('meta[property="og:title"]') ||
      meta('meta[name="twitter:title"]') ||
      meta('meta[name="title"]') ||
      document.title.trim();

    const parsed = parseEpisodeFromTitle(rawTitle);
    const series = meta('meta[property="og:series"]') ||
      meta('meta[name="series"]') || null;

    return {
      rawTitle,
      animeTitle: series,
      season: parsed.season,
      episode: parsed.episode,
      contentKind: parsed.episode ? "episode" : classifyContent(rawTitle, video?.duration, parsed.episode),
      siteIdentifier: genericSiteIdentifier(),
      searchHints: [],
    };
  }

  function crunchyrollSeriesIdentifier() {
    const seriesMatch = location.pathname.match(/\/series\/([^/]+)/i);
    if (seriesMatch) return `crunchyroll:series:${seriesMatch[1].toLowerCase()}`;
    return null;
  }

  function crunchyrollStructuredIdentifier() {
    const data = findStructuredMedia();
    if (!data) return null;
    const series = resolveName(data.partOfSeries) ||
      resolveName(data.partOfSeason?.partOfSeries) ||
      data.seriesTitle ||
      data.series_title ||
      null;
    const seasonName = resolveName(data.partOfSeason);
    const season = data.partOfSeason?.seasonNumber ?? null;
    const parts = [series, seasonName, season].filter((value) => value !== null && value !== undefined);
    if (!parts.length) return null;
    return `crunchyroll:${parts.join(":").toLowerCase().replace(/\s+/g, "-")}`;
  }

  function genericSiteIdentifier() {
    const path = location.pathname.replace(/\/[^/]+\/?$/, "/");
    return `site:${location.hostname.toLowerCase()}${path}`;
  }

  const generic = {
    name: "generic",
    matches: () => true,
    detect(video) {
      return extractFromStructuredMedia(video) || detectFromMetadata(video);
    },
  };

  const crunchyroll = {
    name: "crunchyroll",
    matches: () => /(^|\.)crunchyroll\.com$/i.test(location.hostname),
    detect(video) {
      const fromMedia = extractFromStructuredMedia(video);
      const hints = [];

      if (fromMedia?.episode != null && fromMedia.animeTitle) {
        fromMedia.searchHints = hints;
        fromMedia.siteIdentifier = crunchyrollStructuredIdentifier() || crunchyrollSeriesIdentifier();
        return fromMedia;
      }

      const fallback = detectFromMetadata(video);
      const heading = text("h1") || text('[data-t="series-title"]');
      const episodeText = text('[data-t="episode-title"]') || fallback.rawTitle;
      const parsed = parseEpisodeFromTitle(episodeText);

      return {
        ...fallback,
        rawTitle: episodeText,
        animeTitle: heading || fallback.animeTitle,
        season: parsed.season ?? fallback.season,
        episode: parsed.episode ?? fallback.episode,
        contentKind: (parsed.episode ?? fallback.episode) ? "episode" : classifyContent(episodeText, video?.duration, parsed.episode),
        siteIdentifier: crunchyrollStructuredIdentifier() || crunchyrollSeriesIdentifier(),
        searchHints: hints,
      };
    },
  };

  const plex = {
    name: "plex",
    matches: () => /(^|\.)plex\.tv$/i.test(location.hostname) || /:32400\/web\/index\.html/.test(location.href),
    detect(video) {
      const fromMedia = extractFromStructuredMedia(video);
      if (fromMedia?.episode != null && fromMedia.animeTitle) {
        return fromMedia;
      }
      return detectFromMetadata(video);
    },
  };

  const jellyfin = {
    name: "jellyfin",
    matches: () => /\/web\/index\.html/.test(location.href) && document.querySelector('[data-app="jellyfin"]'),
    detect(video) {
      const fromMedia = extractFromStructuredMedia(video);
      if (fromMedia?.episode != null && fromMedia.animeTitle) {
        return fromMedia;
      }
      return detectFromMetadata(video);
    },
  };

  const adapters = [crunchyroll, plex, jellyfin, generic];
  global.NyankoSiteAdapters = {
    classifyContent,
    parseEpisodeFromTitle,
    select: () => adapters.find((adapter) => adapter.matches()) || generic,
  };
})(globalThis);
