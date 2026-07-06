import assert from "node:assert/strict";
import test from "node:test";

await import("../src/adapters.js");
const { classifyContent, parseEpisodeFromTitle } = globalThis.NyankoSiteAdapters;

test("classifies long trailers and openings", () => {
  assert.equal(classifyContent("Official Trailer", 600), "trailer");
  assert.equal(classifyContent("Creditless Opening", 240), "opening");
  assert.equal(classifyContent("Regular Episode", 1440), "unknown");
});

test("classifies short generic videos as previews", () => {
  assert.equal(classifyContent("Next week", 30), "preview");
});

test("extracts explicit season and episode labels", () => {
  assert.deepEqual(parseEpisodeFromTitle("Season 2 Episode 7"), { season: 2, episode: 7 });
  assert.deepEqual(parseEpisodeFromTitle("S03E12"), { season: 3, episode: 12 });
  assert.deepEqual(parseEpisodeFromTitle("Episode 9"), { season: null, episode: 9 });
});

test("crunchyroll identifier stays stable across episode urls", () => {
  const json = JSON.stringify({
    "@type": "TVEpisode",
    name: "Episode 12",
    episodeNumber: 12,
    partOfSeries: { name: "Frieren: Beyond Journey's End" },
    partOfSeason: {
      "@id": "https://www.crunchyroll.com/series/G6/frieren-beyond-journeys-end",
      name: "Season 1",
      seasonNumber: 1,
    },
  });
  globalThis.document = {
    title: "Episode 12",
    querySelector: () => null,
    querySelectorAll: () => [{ textContent: json }],
  };
  globalThis.location = new URL("https://www.crunchyroll.com/watch/AAAA/episode-12");

  const adapter = globalThis.NyankoSiteAdapters.select();
  const first = adapter.detect({ duration: 1440 });
  globalThis.location = new URL("https://www.crunchyroll.com/watch/BBBB/episode-11");
  const second = adapter.detect({ duration: 1440 });

  assert.equal(first.siteIdentifier, second.siteIdentifier);
  assert.equal(first.siteIdentifier, "crunchyroll:frieren:-beyond-journey's-end:season-1:1");
});

test("crunchyroll reads embedded json when the url slug is only the episode title", () => {
  const json = JSON.stringify({
    props: {
      pageProps: {
        media: {
          episodeNumber: 11,
          name: "As a Partner",
          seriesTitle: "Ace of the Diamond",
          partOfSeason: {
            "@id": "https://www.crunchyroll.com/es-es/series/GY8VEQ95Y/ace-of-the-diamond",
            name: "Season 3",
            seasonNumber: 3,
          },
        },
      },
    },
  });
  globalThis.document = {
    title: "As a Partner",
    querySelector: () => null,
    querySelectorAll: () => [{ textContent: json, type: "application/json" }],
  };
  globalThis.location = new URL("https://www.crunchyroll.com/es-es/watch/GE00375473JAJP/as-a-partner");

  const detected = globalThis.NyankoSiteAdapters.select().detect({ duration: 1440 });

  assert.equal(detected.animeTitle, "Ace of the Diamond Season 3");
  assert.equal(detected.episode, 11);
  assert.equal(detected.siteIdentifier, "crunchyroll:ace-of-the-diamond:season-3:3");
  assert.deepEqual(detected.searchHints, []);
});

test("animeflv derives stable series and episode from the watch url", () => {
  globalThis.document = { title: "One Piece 1000", querySelector: () => null, querySelectorAll: () => [] };
  globalThis.location = new URL("https://www3.animeflv.net/ver/one-piece-1000");

  const detected = globalThis.NyankoSiteAdapters.select().detect({ duration: 1440 });
  assert.equal(detected.animeTitle, "One Piece");
  assert.equal(detected.episode, 1000);
  assert.equal(detected.siteIdentifier, "animeflv:one-piece");
  assert.equal(detected.contentKind, "episode");
});

test("animeflv keeps numbers inside the series slug out of the episode", () => {
  globalThis.document = { title: "86 Eighty Six 7", querySelector: () => null, querySelectorAll: () => [] };
  globalThis.location = new URL("https://www3.animeflv.net/ver/86-eighty-six-7");

  const detected = globalThis.NyankoSiteAdapters.select().detect({ duration: 1440 });
  assert.equal(detected.animeTitle, "86 Eighty Six");
  assert.equal(detected.episode, 7);
  assert.equal(detected.siteIdentifier, "animeflv:86-eighty-six");
});

test("jkanime derives series and episode from the watch url", () => {
  globalThis.document = { title: "Black Clover", querySelector: () => null, querySelectorAll: () => [] };
  globalThis.location = new URL("https://jkanime.net/black-clover/12/");

  const detected = globalThis.NyankoSiteAdapters.select().detect({ duration: 1440 });
  assert.equal(detected.animeTitle, "Black Clover");
  assert.equal(detected.episode, 12);
  assert.equal(detected.siteIdentifier, "jkanime:black-clover");
});

test("jkanime derives series and high episode numbers from the real watch url", () => {
  globalThis.document = { title: "One Piece 1168 - Jkanime", querySelector: () => null, querySelectorAll: () => [] };
  globalThis.location = new URL("https://jkanime.net/one-piece/1168/");

  const detected = globalThis.NyankoSiteAdapters.select().detect({ duration: 1440 });
  assert.equal(detected.animeTitle, "One Piece");
  assert.equal(detected.episode, 1168);
  assert.equal(detected.siteIdentifier, "jkanime:one-piece");
  assert.equal(detected.contentKind, "episode");
});

test("generic adapter prefers JSON-LD series and episode over page selectors", () => {
  const json = JSON.stringify({
    "@type": "TVEpisode",
    name: "Episode 8",
    episodeNumber: 8,
    partOfSeries: { name: "Spy x Family" },
  });
  globalThis.document = {
    title: "watch online",
    querySelector: () => null,
    querySelectorAll: () => [{ textContent: json, type: "application/ld+json" }],
  };
  globalThis.location = new URL("https://anysite.test/watch/123");

  const detected = globalThis.NyankoSiteAdapters.select().detect({ duration: 1440 });
  assert.equal(detected.animeTitle, "Spy x Family");
  assert.equal(detected.episode, 8);
});

test("generic adapter uses page selectors when JSON-LD lacks series/episode", () => {
  const json = JSON.stringify({ "@type": "VideoObject", name: "Some Clip" });
  globalThis.document = {
    title: "Fallback Title",
    querySelector: (selector) => (selector.includes("og:title") ? { content: "Metadata Title" } : null),
    querySelectorAll: () => [{ textContent: json, type: "application/ld+json" }],
  };
  globalThis.location = new URL("https://anysite.test/watch/123");

  const detected = globalThis.NyankoSiteAdapters.select().detect({ duration: 1440 });
  assert.equal(detected.rawTitle, "Metadata Title");
});

test("animefire derives series and episode from the /animes/ watch url", () => {
  globalThis.document = { title: "High School DxD Born", querySelector: () => null, querySelectorAll: () => [] };
  globalThis.location = new URL("https://animefire.vip/animes/high-school-dxd-born/6");

  const detected = globalThis.NyankoSiteAdapters.select().detect({ duration: 1440 });
  assert.equal(detected.animeTitle, "High School Dxd Born");
  assert.equal(detected.episode, 6);
  assert.equal(detected.siteIdentifier, "animefire:high-school-dxd-born");
});

test("generic adapter exposes rel=next as nextEpisodeUrl when the site provides it", () => {
  globalThis.document = {
    title: "Episode 5",
    querySelector: (selector) => (selector.includes('rel="next"') ? { href: "https://example.com/anime/ep-6" } : null),
    querySelectorAll: () => [],
  };
  globalThis.location = new URL("https://example.com/anime/ep-5");

  const detected = globalThis.NyankoSiteAdapters.select().detect({ duration: 1440 });
  assert.equal(detected.nextEpisodeUrl, "https://example.com/anime/ep-6");
});

test("nextEpisodeUrl stays null when the site exposes no next link", () => {
  globalThis.document = { title: "Episode 5", querySelector: () => null, querySelectorAll: () => [] };
  globalThis.location = new URL("https://example.com/anime/ep-5");

  const detected = globalThis.NyankoSiteAdapters.select().detect({ duration: 1440 });
  assert.equal(detected.nextEpisodeUrl, null);
});

test("tioanime derives series and episode from the /ver/slug-N url", () => {
  globalThis.document = { title: "Mahouka", querySelector: () => null, querySelectorAll: () => [] };
  globalThis.location = new URL("https://tioanime.com/ver/mahouka-koukou-no-rettousei-25");

  const detected = globalThis.NyankoSiteAdapters.select().detect({ duration: 1440 });
  assert.equal(detected.animeTitle, "Mahouka Koukou No Rettousei");
  assert.equal(detected.episode, 25);
  assert.equal(detected.siteIdentifier, "tioanime:mahouka-koukou-no-rettousei");
});

test("otakustv reads round-N as the episode and treats pelicula as one", () => {
  globalThis.document = { title: "High Score Girl", querySelector: () => null, querySelectorAll: () => [] };
  globalThis.location = new URL("https://www1.otakustv.com/anime/high-score-girl/round-7/");
  let detected = globalThis.NyankoSiteAdapters.select().detect({ duration: 1440 });
  assert.equal(detected.episode, 7);
  assert.equal(detected.siteIdentifier, "otakustv:high-score-girl");

  globalThis.location = new URL("https://www1.otakustv.com/anime/kizumonogatari/pelicula");
  detected = globalThis.NyankoSiteAdapters.select().detect({ duration: 1440 });
  assert.equal(detected.episode, 1);
  assert.equal(detected.siteIdentifier, "otakustv:kizumonogatari");
});

test("animeav1 and hentaila derive series and episode from /media/slug/N", () => {
  globalThis.document = { title: "Mao", querySelector: () => null, querySelectorAll: () => [] };
  globalThis.location = new URL("https://animeav1.com/media/mao/13");
  let detected = globalThis.NyankoSiteAdapters.select().detect({ duration: 1440 });
  assert.equal(detected.animeTitle, "Mao");
  assert.equal(detected.episode, 13);
  assert.equal(detected.siteIdentifier, "animeav1:mao");

  globalThis.location = new URL("https://hentaila.com/media/septem-charm-magical-kanan/2");
  detected = globalThis.NyankoSiteAdapters.select().detect({ duration: 1440 });
  assert.equal(detected.episode, 2);
  assert.equal(detected.siteIdentifier, "hentaila:septem-charm-magical-kanan");
});

test("an1me derives series and episode from /wm/slug/episode-N", () => {
  globalThis.document = { title: "One Piece", querySelector: () => null, querySelectorAll: () => [] };
  globalThis.location = new URL("https://an1me.to/wm/one-piece/episode-312/");

  const detected = globalThis.NyankoSiteAdapters.select().detect({ duration: 1440 });
  assert.equal(detected.episode, 312);
  assert.equal(detected.siteIdentifier, "an1me:one-piece");
});

test("catalog exposes a name+label per adapter for the app's tracking toggles", () => {
  const { catalog } = globalThis.NyankoSiteAdapters;
  assert.ok(Array.isArray(catalog) && catalog.length > 0);
  for (const entry of catalog) {
    assert.equal(typeof entry.name, "string");
    assert.ok(entry.label && typeof entry.label === "string");
  }
  const names = catalog.map((entry) => entry.name);
  assert.equal(new Set(names).size, names.length, "adapter names are unique");
  assert.ok(names.includes("generic"), "generic is offered as an opt-in");
  assert.ok(names.includes("animexin") && names.includes("crunchyroll"));
});

test("ported MAL-Sync slug sites derive series and episode from the watch url", () => {
  // [url, expected siteIdentifier, expected episode] — urls taken from MAL-Sync tests.json.
  const cases = [
    ["https://animexin.vip/the-daily-life-of-the-immortal-king-episode-8-subbed/", "animexin:the-daily-life-of-the-immortal-king", 8],
    ["https://animeko.co/skip-to-loafer-episode-01-vostfr", "animeko:skip-to-loafer", 1],
    ["https://www.luciferdonghua.co.in/tales-of-demons-and-gods-season-6-episode-50-multi-sub/", "luciferdonghua:tales-of-demons-and-gods-season-6", 50],
    ["https://kaguya.app/anime/watch/124410/gogo/kanojo-okarishimasu-2nd-season-dub-episode-1", "kaguya:kanojo-okarishimasu-2nd-season-dub", 1],
    ["https://betteranime.net/anime/dublado/one-piece-dublado-2020/episodio-132", "betteranime:one-piece-dublado-2020", 132],
    ["https://otakufr.co/episode/ahiru-no-sora-21-vostfr/", "otakufr:ahiru-no-sora", 21],
    ["https://moeclip.com/high-school-dxd-hero-05-sub-indo/", "moeclip:high-school-dxd-hero", 5],
    ["https://desu-online.pl/maou-gakuin-odcinek-3/", "desuonline:maou-gakuin", 3],
    ["https://www.animezone.pl/odcinek/black-clover-tv/131", "animezone:black-clover-tv", 131],
    ["https://anime-odcinki.pl/anime/cop-craft/1", "animeodcinki:cop-craft", 1],
    ["https://docchi.pl/production/as/nanatsu-no-maken-ga-shihai-suru/2", "docchi:nanatsu-no-maken-ga-shihai-suru", 2],
    ["https://aniyan.net/w/12271/otonari-no-tenshi-sama-episodio-1/", "aniyan:otonari-no-tenshi-sama", 1],
    ["https://www.turkanime.co/video/no-game-no-life-6-bolum", "turkanime:no-game-no-life", 6],
    ["https://anidream.cc/watch/no-game-no-life-episodio-1", "anidream:no-game-no-life", 1],
    ["https://ani.wtf/anime/188-yuri-on-ice/episode_3-subtitles", "sovetromantica:yuri-on-ice", 3],
    ["https://aninexus.to/episode/the-do-over-damsel/1-1", "aninexus:the-do-over-damsel", 1],
    ["https://kickassanime.am/overlord-iii-5092/ep-10-9b9161", "kickassanime:overlord-iii-5092", 10],
    ["https://okanime.tv/animes/romeo-no-aoi-sora/episodes/romeo-no-aoi-sora-001-%D8%A7%D9%84", "okanime:romeo-no-aoi-sora", 1],
  ];
  for (const [url, siteIdentifier, episode] of cases) {
    globalThis.document = { title: "x", querySelector: () => null, querySelectorAll: () => [] };
    globalThis.location = new URL(url);
    const detected = globalThis.NyankoSiteAdapters.select().detect({ duration: 1440 });
    assert.equal(detected.siteIdentifier, siteIdentifier, `siteIdentifier for ${url}`);
    assert.equal(detected.episode, episode, `episode for ${url}`);
    assert.equal(detected.contentKind, "episode", `contentKind for ${url}`);
  }
});

test("crunchyroll does not use watch slugs as series identifiers", () => {
  globalThis.document = {
    title: "My Fight",
    querySelector: () => null,
    querySelectorAll: () => [],
  };
  globalThis.location = new URL("https://www.crunchyroll.com/es-es/watch/GE00375472JAJP/my-fight");

  const detected = globalThis.NyankoSiteAdapters.select().detect({ duration: 1440 });

  assert.equal(detected.siteIdentifier, null);
  assert.deepEqual(detected.searchHints, []);
});
