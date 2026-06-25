import assert from "node:assert/strict";
import test from "node:test";

globalThis.chrome = { runtime: null };
await import("../src/content.js");

const { episodeSignature, progressKey } = globalThis.NyankoPlaybackContent;

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

test("progress keys are scoped by signature", () => {
  assert.equal(progressKey("a|b"), "nyanko-progress:a|b");
});
