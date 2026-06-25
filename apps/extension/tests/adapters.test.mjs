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
