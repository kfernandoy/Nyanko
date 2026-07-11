import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { loadWindowPrefs, saveWindowPrefs, coercePrefs } from "./window-prefs";

// Self-check T-04-05: save+load round-trip y descarte de claves desconocidas, bajo
// Node plano (sin electron), mismo estilo que compat-paths.test.ts.

test("save+load hace round-trip de {close_to_tray:true}", () => {
  const dir = mkdtempSync(join(tmpdir(), "nyanko-prefs-"));
  try {
    saveWindowPrefs(dir, { close_to_tray: true });
    const loaded = loadWindowPrefs(dir);
    assert.equal(loaded.close_to_tray, true);
    assert.equal(loaded.minimize_to_tray, false);
    assert.equal(loaded.start_minimized, false);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("save descarta claves extra y persiste solo las tres conocidas", () => {
  const dir = mkdtempSync(join(tmpdir(), "nyanko-prefs-"));
  try {
    saveWindowPrefs(dir, {
      close_to_tray: true,
      minimize_to_tray: true,
      start_minimized: true,
      __proto__: { polluted: true },
      hacker: "x",
    });
    const loaded = loadWindowPrefs(dir);
    assert.deepEqual(Object.keys(loaded).sort(), [
      "close_to_tray",
      "minimize_to_tray",
      "start_minimized",
    ]);
    assert.equal((loaded as Record<string, unknown>).hacker, undefined);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("coercePrefs convierte ausencia/valores raros a booleanos con defaults false", () => {
  assert.deepEqual(coercePrefs(undefined), {
    close_to_tray: false,
    minimize_to_tray: false,
    start_minimized: false,
  });
  assert.equal(coercePrefs({ close_to_tray: 1 }).close_to_tray, true);
});

test("loadWindowPrefs devuelve defaults si el fichero no existe", () => {
  const dir = mkdtempSync(join(tmpdir(), "nyanko-prefs-"));
  try {
    assert.deepEqual(loadWindowPrefs(dir), {
      close_to_tray: false,
      minimize_to_tray: false,
      start_minimized: false,
    });
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});
