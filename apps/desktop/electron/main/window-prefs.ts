import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { join } from "node:path";

// Paridad D-05 con el viejo window_prefs.rs: el fichero vive en el data dir de la
// app (%APPDATA%\app.nyanko.desktop\window_prefs.json), esquema de exactamente tres
// booleanos, todos por defecto false. Los prefs de prod existentes cargan SIN
// migración (JSON malformado/ausente → defaults).
//
// Núcleo ELECTRON-FREE a propósito (como compat-paths.ts): loadWindowPrefs /
// saveWindowPrefs son puras y toman el dir, así el self-check (window-prefs.test.ts)
// corre bajo `node --import tsx` sin importar electron. El dir real
// (app.getPath("userData")) lo inyecta index.ts al sembrar la caché en el arranque.

export type WindowPrefs = {
  close_to_tray: boolean;
  minimize_to_tray: boolean;
  start_minimized: boolean;
};

const PREFS_FILE = "window_prefs.json";

function defaults(): WindowPrefs {
  return { close_to_tray: false, minimize_to_tray: false, start_minimized: false };
}

// T-04-05 (Tampering): coacciona el payload del renderer a EXACTAMENTE tres
// booleanos y descarta cualquier clave extra antes de persistir — sin JSON
// arbitrario ni contaminación de prototipo.
export function coercePrefs(input: unknown): WindowPrefs {
  const o = (input ?? {}) as Record<string, unknown>;
  return {
    close_to_tray: Boolean(o.close_to_tray),
    minimize_to_tray: Boolean(o.minimize_to_tray),
    start_minimized: Boolean(o.start_minimized),
  };
}

export function loadWindowPrefs(dir: string): WindowPrefs {
  try {
    return coercePrefs(JSON.parse(readFileSync(join(dir, PREFS_FILE), "utf-8")));
  } catch {
    // Fichero ausente o corrupto → defaults (paridad: prod carga sin migración).
    return defaults();
  }
}

// T-04-04 (Tampering): la escritura queda hard-scoped a `dir` (userData); `dir`
// nunca viene del renderer, solo de app.getPath("userData"). Sin path traversal.
export function saveWindowPrefs(dir: string, input: unknown): WindowPrefs {
  const coerced = coercePrefs(input);
  mkdirSync(dir, { recursive: true });
  writeFileSync(join(dir, PREFS_FILE), JSON.stringify(coerced, null, 2));
  return coerced;
}

// ── Caché en memoria (equivale a WindowPrefsState del Rust) ──
// index.ts la siembra en el arranque; la bandeja y los listeners close/minimize la
// leen vía currentWindowPrefs() sin tocar disco en cada evento.
let cache: WindowPrefs = defaults();
let cacheDir = "";

export function seedWindowPrefs(dir: string): WindowPrefs {
  cacheDir = dir;
  cache = loadWindowPrefs(dir);
  return cache;
}

export function currentWindowPrefs(): WindowPrefs {
  return cache;
}

// Handler de window-prefs:set — persiste (coaccionado) y refresca la caché.
export function updateWindowPrefs(input: unknown): WindowPrefs {
  cache = saveWindowPrefs(cacheDir, input);
  return cache;
}
