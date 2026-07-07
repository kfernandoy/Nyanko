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

    // Identificador ESTABLE por serie/temporada (no por episodio): sin esto, el mapeo
    // aprendido (media + offset de episodio) cambiaba de clave en cada episodio y nunca
    // se reutilizaba. Con series+temporada, "One Piece Season 22" mantiene un solo mapeo.
    const stableId = seriesName
      ? `series:${(season != null && Number(season) > 1 ? `${seriesName}:s${season}` : seriesName)
          .toLowerCase().replace(/\s+/g, "-")}`
      : genericSiteIdentifier();

    return {
      rawTitle,
      animeTitle,
      season: season !== null ? Number(season) : null,
      episode: episode !== null ? parseFloat(episode) : null,
      contentKind: episode != null ? "episode" : classifyContent(rawTitle, video?.duration, episode),
      siteIdentifier: stableId,
      searchHints: [],
      nextEpisodeUrl: findNextEpisodeUrl(),
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
      nextEpisodeUrl: findNextEpisodeUrl(),
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

  function slugToTitle(slug) {
    return slug ? slug.replace(/[-_]+/g, " ").replace(/\b\w/g, (char) => char.toUpperCase()).trim() : null;
  }

  function findNextEpisodeUrl() {
    // ponytail: rel="next" is the web-standard "next in series" link; site adapters
    // override with a better source when they expose one. Optional, never required.
    const link = document.querySelector('link[rel="next"], a[rel="next"]');
    return link?.href || null;
  }

  // Fan sites without JSON-LD carry a stable series slug and the episode number in the
  // watch URL. Derive both from the path and seed the title from the slug; the backend
  // resolves it against the provider catalogue. content.js only runs detect() when a
  // <video> plays, so listing/search pages never reach here. ``episodeFallback`` covers
  // patterns where the episode segment is optional (e.g. a movie page).
  function slugAdapter(name, hostPattern, pathPattern, episodeFallback = null) {
    return {
      name,
      matches: () => hostPattern.test(location.hostname),
      detect(video) {
        const base = detectFromMetadata(video);
        const match = location.pathname.match(pathPattern);
        if (!match) return base;
        const slug = match[1].toLowerCase();
        return {
          ...base,
          animeTitle: slugToTitle(slug),
          episode: match[2] != null ? parseFloat(match[2]) : episodeFallback,
          contentKind: "episode",
          siteIdentifier: `${name}:${slug}`,
        };
      },
    };
  }

  const generic = {
    name: "generic",
    matches: () => true,
    detect(video) {
      // Policy: JSON-LD is the primary source. Fall back to page selectors only when the
      // structured data omits the series/episode fields (partOfSeries/partOfSeason/
      // episodeNumber) — a bare VideoObject must not suppress the metadata fallback.
      const structured = extractFromStructuredMedia(video);
      if (structured && (structured.episode != null || structured.animeTitle)) return structured;
      return detectFromMetadata(video) || structured;
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

  // Each entry: site name, host matcher, watch-URL path pattern (group 1 = series slug,
  // group 2 = episode), and an optional fallback episode for slug-only/movie paths.
  // Hosts that rotate TLDs are matched on the bare name. Patterns ported from MAL-Sync's
  // page definitions and verified against their test fixtures.
  const animeflv = slugAdapter("animeflv", /(^|\.)animeflv\.net$/i, /\/ver\/(.+?)-(\d+(?:\.5)?)\/?$/i);
  const jkanime = slugAdapter("jkanime", /(^|\.)jkanime\.net$/i, /^\/([^/]+)\/(\d+(?:\.5)?)\/?$/);
  const animefire = slugAdapter("animefire", /(^|\.)animefire\.[a-z]+$/i, /^\/animes\/([^/]+)\/(\d+(?:\.5)?)\/?$/i);
  const latanime = slugAdapter("latanime", /(^|\.)latanime\.[a-z]+$/i, /\/ver\/(.+)-episodio-(\d+(?:\.5)?)\/?$/i);
  const tioanime = slugAdapter("tioanime", /(^|\.)tioanime\.[a-z]+$/i, /\/ver\/(.+)-(\d+(?:\.5)?)\/?$/i);
  const otakustv = slugAdapter("otakustv", /(^|\.)otakustv\.com$/i, /\/anime\/([^/]+)\/(?:round-(\d+)|pelicula)/i, 1);
  const animeid = slugAdapter("animeid", /(^|\.)animeid\.[a-z]+$/i, /\/v\/(.+)-(\d+(?:\.5)?)\/?$/i);
  const an1me = slugAdapter("an1me", /(^|\.)an1me\.[a-z]+$/i, /\/wm\/([^/]+)\/episode-(\d+(?:\.5)?)\/?$/i);
  const animeav1 = slugAdapter("animeav1", /(^|\.)animeav1\.[a-z]+$/i, /\/media\/([^/]+)\/(\d+(?:\.5)?)\/?$/i);
  const hentaila = slugAdapter("hentaila", /(^|\.)hentaila\.[a-z]+$/i, /\/media\/([^/]+)\/(\d+(?:\.5)?)\/?$/i);

  // More MAL-Sync anime sites whose watch URL carries the series slug and episode.
  // Sites whose watch URL is only a numeric/hash id (AnimeUnity, AnimesOnline, HinataSoul,
  // Animelon, Animeworld, AnimeOnsen, Proxer, Shinden…) need DOM/API scraping — out of the
  // lightweight model; the generic JSON-LD/metadata adapter covers them when they expose it.
  const slugEpisode = /^\/(.+?)-episode-(\d+(?:\.5)?)\b.*$/i; // slug-episode-N(-lang)
  const animexin = slugAdapter("animexin", /(^|\.)animexin\.[a-z.]+$/i, slugEpisode);
  const animeko = slugAdapter("animeko", /(^|\.)animeko\.[a-z]+$/i, slugEpisode);
  const luciferdonghua = slugAdapter("luciferdonghua", /(^|\.)luciferdonghua\.[a-z.]+$/i, slugEpisode);
  const kaguya = slugAdapter("kaguya", /(^|\.)kaguya\.app$/i, /\/anime\/watch\/\d+\/[^/]+\/(.+?)-episode-(\d+(?:\.5)?)\/?$/i);
  const betteranime = slugAdapter("betteranime", /(^|\.)betteranime\.[a-z]+$/i, /\/anime\/[^/]+\/([^/]+)\/episodio-(\d+(?:\.5)?)\/?$/i);
  const otakufr = slugAdapter("otakufr", /(^|\.)otakufr\.[a-z]+$/i, /^\/episode\/(.+?)-(\d+(?:\.5)?)-[a-z]+\/?$/i);
  const moeclip = slugAdapter("moeclip", /(^|\.)moeclip\.com$/i, /^\/(.+?)-(\d+(?:\.5)?)-sub[a-z-]*\/?$/i);
  const desuonline = slugAdapter("desuonline", /(^|\.)desu-online\.[a-z]+$/i, /^\/(.+?)-odcinek-(\d+(?:\.5)?)\/?$/i);
  const animezone = slugAdapter("animezone", /(^|\.)animezone\.[a-z]+$/i, /^\/odcinek\/([^/]+)\/(\d+(?:\.5)?)\/?$/i);
  const animeodcinki = slugAdapter("animeodcinki", /(^|\.)anime-odcinki\.[a-z]+$/i, /^\/anime\/([^/]+)\/(\d+(?:\.5)?)\/?$/i);
  const docchi = slugAdapter("docchi", /(^|\.)docchi\.[a-z]+$/i, /^\/production\/[a-z]+\/([^/]+)\/(\d+(?:\.5)?)\/?$/i);
  const aniyan = slugAdapter("aniyan", /(^|\.)aniyan\.[a-z]+$/i, /^\/w\/\d+\/(.+?)-episodio-(\d+(?:\.5)?)\/?$/i);
  const turkanime = slugAdapter("turkanime", /(^|\.)turkanime\.[a-z.]+$/i, /^\/video\/(.+?)-(\d+(?:\.5)?)-bolum\/?$/i);
  const anidream = slugAdapter("anidream", /(^|\.)anidream\.[a-z]+$/i, /^\/watch\/(.+?)-episodio-(\d+(?:\.5)?)\/?$/i);
  const sovetromantica = slugAdapter("sovetromantica", /(^|\.)sovetromantica\.com$|(^|\.)ani\.wtf$/i, /^\/anime\/\d+-([^/]+)\/episode_(\d+(?:\.5)?)\b/i);
  const aninexus = slugAdapter("aninexus", /(^|\.)aninexus\.[a-z]+$/i, /^\/episode\/([^/]+)\/(\d+)(?:-\d+)?\/?$/i);
  const kickassanime = slugAdapter("kickassanime", /(^|\.)(kickassanime|kaas|kaa)\.[a-z]+$/i, /^\/([^/]+)\/ep-(\d+(?:\.5)?)-[a-z0-9]+\/?$/i);
  const okanime = slugAdapter("okanime", /(^|\.)okanime\.[a-z]+$/i, /^\/animes\/([^/]+)\/episodes\/.+?-(\d+)(?:[-/]|$)/i);

  const adapters = [
    crunchyroll, animeflv, jkanime, animefire, latanime, tioanime,
    otakustv, animeid, an1me, animeav1, hentaila,
    animexin, animeko, luciferdonghua, kaguya, betteranime, otakufr, moeclip,
    desuonline, animezone, animeodcinki, docchi, aniyan, turkanime, anidream,
    sovetromantica, aninexus, kickassanime, okanime,
    plex, jellyfin, generic,
  ];
  // Display labels for the app's per-adapter tracking toggles. Derived from the
  // adapters array so a new adapter only needs an entry here, never a parallel list.
  // The app (apps/desktop ExtensionSettingsView) mirrors these name+label pairs.
  const labels = {
    crunchyroll: "Crunchyroll", animeflv: "AnimeFLV", jkanime: "Jkanime",
    animefire: "AnimeFire", latanime: "Latanime",
    tioanime: "TioAnime", otakustv: "OtakusTV", animeid: "AnimeID", an1me: "An1me",
    animeav1: "AnimeAV1", hentaila: "Hentaila", animexin: "AnimeXin", animeko: "AnimeKO",
    luciferdonghua: "LuciferDonghua", kaguya: "Kaguya", betteranime: "BetterAnime",
    otakufr: "OtakuFR", moeclip: "moeclip", desuonline: "Desu-Online",
    animezone: "AnimeZone", animeodcinki: "Anime-Odcinki", docchi: "Docchi",
    aniyan: "Aniyan", turkanime: "TürkAnime", anidream: "AniDream",
    sovetromantica: "SovetRomantica", aninexus: "AniNexus", kickassanime: "KickAssAnime",
    okanime: "Okanime", plex: "Plex", jellyfin: "Jellyfin",
    generic: "Cualquier otro sitio (genérico)",
  };
  const catalog = adapters.map((adapter) => ({ name: adapter.name, label: labels[adapter.name] || adapter.name }));

  global.NyankoSiteAdapters = {
    classifyContent,
    parseEpisodeFromTitle,
    catalog,
    select: () => adapters.find((adapter) => adapter.matches()) || generic,
  };
})(globalThis);
