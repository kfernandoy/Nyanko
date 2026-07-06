import assert from "node:assert/strict";
import test from "node:test";

globalThis.chrome = { runtime: null };
await import("../src/content.js");

const { episodeSignature, progressKey, syntheticFromReport } = globalThis.NyankoPlaybackContent;

test("episode signature changes when only the episode changes", () => {
  const base = {
    siteIdentifier: "crunchyroll:series:g6",
    animeTitle: "Frieren",
    season: 1,
    rawTitle: "Frieren",
  };

  assert.notEqual(
    episodeSignature("crunchyroll", { ...base, episode: 12 }, "https://example.test/watch", "blob:1"),
    episodeSignature("crunchyroll", { ...base, episode: 13 }, "https://example.test/watch", "blob:1"),
  );
});

test("signature is stable across language/url variants of the same episode", () => {
  const detected = { siteIdentifier: "crunchyroll:frieren:season-1:1", season: 1, episode: 12 };

  assert.equal(
    episodeSignature("crunchyroll", { ...detected, rawTitle: "Episode 12", animeTitle: "Frieren" },
      "https://www.crunchyroll.com/watch/AAAA/episode-12", "blob:1"),
    episodeSignature("crunchyroll", { ...detected, rawTitle: "Episodio 12", animeTitle: "Frieren" },
      "https://www.crunchyroll.com/es-es/watch/AAAA/episodio-12", "blob:2"),
  );
});

test("signature without a stable id still distinguishes videos by url", () => {
  const detected = { siteIdentifier: "site:example.test/anime/", season: null, episode: null, animeTitle: null, rawTitle: "" };

  assert.notEqual(
    episodeSignature("generic", detected, "https://example.test/anime/ep-5", "blob:1"),
    episodeSignature("generic", detected, "https://example.test/anime/ep-6", "blob:1"),
  );
});

test("synthetic video is built from a fresh subframe report", () => {
  const now = 1_000_000;
  assert.deepEqual(
    syntheticFromReport({ position: 30, duration: 1440, paused: false, at: now - 1000 }, now),
    { currentTime: 30, duration: 1440, paused: false, ended: false },
  );
});

test("stale, empty or missing subframe reports yield no synthetic video", () => {
  const now = 1_000_000;
  assert.equal(syntheticFromReport({ position: 30, duration: 1440, paused: false, at: now - 9000 }, now), null);
  assert.equal(syntheticFromReport({ position: 0, duration: 0, paused: false, at: now }, now), null);
  assert.equal(syntheticFromReport(null, now), null);
});

test("progress keys are scoped by signature", () => {
  assert.equal(progressKey("a|b"), "nyanko-progress:a|b");
});
