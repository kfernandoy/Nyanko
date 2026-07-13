# Phase 2: Main core — sidecar lifecycle + logging - Pattern Map

**Mapped:** 2026-07-10
**Files analyzed:** 8 (5 new, 3 modified)
**Analogs found:** 6 / 8 (2 files are net-new roles with no in-repo analog)

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `apps/desktop/electron/main/sidecar.ts` (new) | service | process-lifecycle / event-driven | `apps/desktop/electron/main/compat-paths.ts` (pure module + self-check) + backend `instance.py` (port-file contract) | role-match |
| `apps/desktop/electron/main/logging.ts` (new) | config/utility | file-I/O | `apps/desktop/electron/main/compat-paths.ts` (small focused module) | partial (new dep `electron-log`) |
| `apps/desktop/electron/main/splash.ts` (+ inline/local HTML) (new) | provider (window) | request-response | `createWindow()` in `apps/desktop/electron/main/index.ts` (BrowserWindow + secure webPreferences) | role-match |
| `apps/desktop/electron/main/index.ts` (modified) | bootstrap/orchestrator | event-driven | itself (extend existing `whenReady` sequence) | self |
| `apps/desktop/electron/main/ipc.ts` (new) | middleware (IPC) | request-response | none (no `ipcMain.handle` exists yet) | **no analog** |
| `apps/desktop/electron/preload/index.ts` (modified) | preload bridge | request-response | itself (existing `contextBridge.exposeInMainWorld`) | self |
| `apps/desktop/src/DetectorSettingsView.tsx` (modified — "acerca" tab) | component | request-response | itself (existing button rows in `detector-list`) | self |
| `apps/desktop/electron/main/sidecar.test.ts` (new) | test | — | `apps/desktop/electron/main/compat-paths.test.ts` (`node:test` under `tsx`) | exact |

## Backend Contract (read-only — frozen, do NOT modify)

The sidecar readiness gate is built entirely against these existing signals:

- **Port file path:** `<NYANKO_DATA_DIR>/port` — `config.py:84-85` `port_file = self.data_dir / "port"` (no extension). `data_dir` is anchored to `NYANKO_DATA_DIR` when absolute (`config.py:70-77`).
- **Port file format:** plain text, the port number as a string — `instance.py:58-60` `write_port_file` does `path.write_text(str(port))`; `instance.py:48-55` `read_port_file` does `int(text.strip())`. The main should parse identically: read file, `.trim()`, `parseInt`.
- **Write timing:** the sidecar writes the port file at startup inside `lifespan` — `main.py:1343` `write_port_file(settings.port_file, settings.api_port)`. This is the signal the main waits for. **D-01 step 2:** delete the stale `port` file before spawn so the wait only accepts a file written after this line runs.
- **Readiness endpoint:** `GET http://127.0.0.1:<port>/api/health` → `200` — `main.py:1392-1396`. Returns `HealthResponse` unconditionally (no auth required), so `200` == ready. No `/api/library/status`, `/api/bootstrap`, or `/api/shutdown` exist (D-03, D-09).
- **`NYANKO_DATA_DIR` value:** `compat-paths.userDataDir(app.getPath("appData"))` → `%APPDATA%\app.nyanko.desktop` (see below). Pass this exact value as the sidecar's `NYANKO_DATA_DIR` env so it reads/writes the same userData the main locked.

## Pattern Assignments

### `apps/desktop/electron/main/sidecar.ts` (service, process-lifecycle)

**Analogs:** `compat-paths.ts` (module shape + self-check discipline), backend `instance.py` (port-file contract).

**Module-shape pattern** — small, focused, named exports, Electron-thin so pure logic is testable (from `compat-paths.ts:1-23`):
```typescript
import { join } from "node:path";
// Fuente única de verdad ... ELECTRON-FREE a propósito: el self-check lo ejecuta
// bajo Node plano, sin mock de electron.
export const LEGACY_APP_ID = "app.nyanko.desktop";
export function userDataDir(appDataPath: string): string {
  return join(appDataPath, LEGACY_APP_ID);
}
```
Apply the same split here: keep pure helpers (port-file parse, health-URL builder, dev/prod decision) as Electron-free named exports so `sidecar.test.ts` can drive them under plain Node; keep `spawn`/`app`/`net` calls in a thin non-tested wrapper.

**Port-file parse pattern** (mirror `instance.py:48-60` in TS) — read `<userData>/port`, trim, `parseInt`, return `null` on missing/NaN. Pure function → self-checkable.

**Dev/prod gate (D-10):** branch on `app.isPackaged`. In dev (`!app.isPackaged`) skip spawn entirely (backend runs by hand). Keep the boolean decision in a pure helper for the self-check.

**Spawn env pattern:** pass `NYANKO_DATA_DIR = userDataDir(app.getPath("appData"))` (same value `index.ts:11` locks) so sidecar and main agree on the data dir. Locate the packaged `nyanko-api.exe` relative to resources (planner/research to confirm PyInstaller onedir layout).

**Kill pattern (D-07, exposed reusable for updater D-08):** export a single `killSidecar()` — graceful attempt, wait ~3-5s, then `taskkill /PID <pid> /T /F` (spawn `taskkill`, the `/T` kills the PyInstaller child tree on Windows). Reference: renderer already assumes a `stop_sidecar` primitive today (`DetectorSettingsView.tsx:93` `await invoke("stop_sidecar")`) — the Electron equivalent must be callable from both `before-quit` and the updater path.

**Re-spawn (D-04/D-05/D-06):** fail-fast on early `child.on("exit")` (don't wait the full 30s); one automatic re-spawn after cleanup (delete port file, wait 500-1000ms); second failure surfaces the splash error state.

---

### `apps/desktop/electron/main/logging.ts` (config/utility, file-I/O)

**Analog:** `compat-paths.ts` shape. **New dependency:** `electron-log` (not yet in `package.json` — add to `dependencies`, it is not currently installed anywhere per grep).

**Pattern to establish:** initialize `electron-log` transports for `main.log` + `sidecar.log` under `app.getPath('logs')`, and export `openLogsFolder()`:
```typescript
// D-11: exact target
shell.openPath(app.getPath("logs"));
```
Pipe sidecar `stdout`/`stderr` into the `sidecar.log` transport (Claude's discretion — stream vs electron-log transport). Defaults for rotation/level unless a need appears (Claude's discretion per CONTEXT). Keep `openLogsFolder` as the single exported function reused by both the IPC handler and the optional native menu item (D-12).

---

### `apps/desktop/electron/main/splash.ts` (provider/window, request-response)

**Analog:** `createWindow()` in `index.ts:14-41`.

**Secure-window pattern to copy verbatim** (`index.ts:15-40`) — these `webPreferences` are load-bearing (CLAUDE.md security constraint) and the splash MUST match them:
```typescript
const win = new BrowserWindow({
  width: 1180, height: 760,        // splash: smaller
  frame: false, show: false,
  webPreferences: {
    preload: join(__dirname, "../preload/index.cjs"),
    contextIsolation: true,
    nodeIntegration: false,
    sandbox: true,
    webSecurity: true,
  },
});
win.on("ready-to-show", () => win.show());
```
Splash loads local HTML with no backend (D-01 step 1; inline data URL vs local file is Claude's discretion). Error state (D-01 step 7 / D-06) needs Retry / Open logs / Exit buttons — those buttons call back via IPC (`openLogsFolder`, retry, `app.quit`).

**`__dirname` in ESM** (main is ESM, `"type":"module"`) — copy the derivation from `index.ts:6`:
```typescript
const __dirname = dirname(fileURLToPath(import.meta.url));
```

---

### `apps/desktop/electron/main/index.ts` (modified — bootstrap orchestrator)

**Self-analog.** Existing sequence (`index.ts:11-48`): `setPath("userData")` → `assertUserDataDir` → `whenReady().then(createWindow)` → `window-all-closed → app.quit()`.

**Insert the startup gate (D-01) between `whenReady` and the main window** — the existing `app.whenReady().then(createWindow)` (line 43) becomes an orchestrated async sequence:
1. open splash immediately,
2. if `app.isPackaged`: delete stale port file → spawn sidecar → await port file (≤30s) → `GET /api/health` 200,
3. on OK: `createWindow()` (reuse existing fn), await its `ready-to-show`, close splash,
4. on fail: put splash in error state.

**Register kill on both exit paths (D-08):** add `app.on("before-quit", killSidecar)` (updater path in Phase 5 calls the same `killSidecar` before `quitAndInstall`). Keep the existing `window-all-closed → app.quit()` (`index.ts:45-48`).

**Dev short-circuit:** when `!app.isPackaged`, skip steps 2's spawn/wait (D-10) and go straight to `createWindow` (renderer already resolves the port itself via `VITE_API_URL` — `api.ts:85`).

---

### `apps/desktop/electron/main/ipc.ts` (new — IPC middleware) — NO ANALOG

No `ipcMain.handle` exists in the repo yet (grep-confirmed). Establish the pattern here: register `ipcMain.handle("openLogsFolder", () => openLogsFolder())` (delegates to `logging.ts`). Keep it a thin registrar called once from `index.ts` after `whenReady`. This becomes the analog for future IPC in Phase 3's `native.ts`.

---

### `apps/desktop/electron/preload/index.ts` (modified — preload bridge)

**Self-analog** (current file, `preload/index.ts:1-8`):
```typescript
import { contextBridge } from "electron";
contextBridge.exposeInMainWorld("nyanko", {
  appVersion: process.env.npm_package_version ?? "",
});
```
**Extend the same `nyanko` namespace** — add `openLogsFolder: () => ipcRenderer.invoke("openLogsFolder")` (import `ipcRenderer` alongside `contextBridge`). Do NOT expose raw Node/ipcRenderer to the renderer (sandbox:true — comment at `preload/index.ts:3-5`). Build output stays `.cjs` — enforced by `electron.vite.config.ts:12-22` (`format: "cjs", entryFileNames: "index.cjs"`); no config change needed.

---

### `apps/desktop/src/DetectorSettingsView.tsx` (modified — logs button)

**Self-analog.** Host the "Open logs folder" button in the existing **"acerca" (about) tab** next to the update button — it already has the diagnostics-flavored `detector-list` rows (`DetectorSettingsView.tsx:336-351`):
```tsx
<article>
  <div><strong>{t("about.updates")}</strong><span>{t("about.updates.d")}</span></div>
  <button className="small" ... onClick={() => void checkForUpdates()}>...</button>
</article>
```
Add a sibling `<article>` with a button calling the preload bridge. **Environment guard pattern** (this codebase gates desktop-only actions on the window global): existing code uses `"__TAURI_INTERNALS__" in window` (`DetectorSettingsView.tsx:72`, `LibrarySettingsView.tsx:79`). Under Electron that global is absent — gate on `"nyanko" in window` / `window.nyanko?.openLogsFolder` instead, calling `window.nyanko.openLogsFolder()`. Use the `t(...)` i18n helper for labels (add keys) consistent with every other string here. Error handling follows the local `try/catch → setError(reason instanceof Error ? reason.message : ...)` pattern used throughout this file (e.g. lines 96-99).

**Note for planner:** the renderer still ships Tauri `invoke`/plugin imports (`DetectorSettingsView.tsx:2-6`) — those are Phase 3's concern (`native.ts`). For Phase 2 only add the logs button via `window.nyanko`; do not rip out Tauri calls.

---

### `apps/desktop/electron/main/sidecar.test.ts` (new — self-check)

**Analog:** `compat-paths.test.ts` (exact). Copy the `node:test` + `node:assert/strict` no-framework structure (`compat-paths.test.ts:1-8`):
```typescript
import { test } from "node:test";
import assert from "node:assert/strict";
import { parsePortFile, isDevMode } from "./sidecar";

test("parsePortFile lee texto plano y devuelve el número", () => {
  assert.equal(parsePortFile("8765\n"), 8765);
});
test("parsePortFile devuelve null en contenido inválido", () => {
  assert.equal(parsePortFile("nope"), null);
});
```
**Wire the npm script** like the existing one (`package.json:12`): add e.g. `"test:sidecar": "node --import tsx --test electron/main/sidecar.test.ts"`. Test ONLY the pure helpers (port parse, health-URL build, dev/prod decision) — never `spawn`/`taskkill`.

## Shared Patterns

### Secure BrowserWindow config
**Source:** `apps/desktop/electron/main/index.ts:15-28`
**Apply to:** splash window (and every future window). `contextIsolation:true / nodeIntegration:false / sandbox:true / webSecurity:true` + preload `../preload/index.cjs`. Non-negotiable (CLAUDE.md Security constraint).

### Data-dir single source of truth
**Source:** `apps/desktop/electron/main/compat-paths.ts:11-13`
**Apply to:** sidecar spawn env. `NYANKO_DATA_DIR` = `userDataDir(app.getPath("appData"))` — the same value `index.ts:11` locks into `userData`. Diverging here re-creates the "6 divergent DBs" bug.

### ESM `__dirname`
**Source:** `apps/desktop/electron/main/index.ts:6`
**Apply to:** any new main/ module using relative paths (`splash.ts`, sidecar exe resolution).
```typescript
const __dirname = dirname(fileURLToPath(import.meta.url));
```

### Pure-logic + Node self-check
**Source:** `compat-paths.ts` (Electron-free exports) + `compat-paths.test.ts` (`node:test` under `tsx`)
**Apply to:** all non-trivial parsing/decision logic (port-file parse, dev/prod gate). Keep it Electron-free, cover it with one `node --import tsx --test` file.

### ContextBridge namespace (no raw Node to renderer)
**Source:** `apps/desktop/electron/preload/index.ts:6-8`
**Apply to:** the `openLogsFolder` bridge — extend the single `nyanko` namespace via `ipcRenderer.invoke`, never expose `ipcRenderer`/Node directly.

## No Analog Found

| File | Role | Data Flow | Reason / Guidance |
|------|------|-----------|-------------------|
| `apps/desktop/electron/main/ipc.ts` | middleware (IPC) | request-response | No `ipcMain.handle` exists yet. Establish the thin-registrar pattern; it becomes the analog for Phase 3 `native.ts`. |
| `apps/desktop/electron/main/logging.ts` | config | file-I/O | No `electron-log` usage exists (grep-confirmed). New dependency; follow `compat-paths.ts` module shape but the transport setup is net-new. |

## Metadata

**Analog search scope:** `apps/desktop/electron/**`, `apps/desktop/src/*SettingsView.tsx`, `apps/desktop/src/api.ts`, `apps/backend/nyanko_api/{instance,config,main}.py`, `apps/desktop/{electron.vite.config.ts,package.json}`
**Files scanned:** 12
**Pattern extraction date:** 2026-07-10
