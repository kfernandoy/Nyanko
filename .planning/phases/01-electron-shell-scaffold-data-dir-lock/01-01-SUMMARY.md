---
phase: 01-electron-shell-scaffold-data-dir-lock
plan: 01
subsystem: desktop-shell
tags: [electron, electron-vite, security, data-dir, migration]
requires: []
provides:
  - electron-vite-scaffold
  - compat-paths-module
  - secure-frameless-window
  - userdata-lock
affects:
  - apps/desktop
tech-stack:
  added: [electron@43, electron-vite@5, tsx@4]
  patterns:
    - electron-vite main/preload/renderer three-section config
    - CommonJS (.cjs) preload for sandboxed renderer
    - electron-free pure compat-paths module (unit-testable under plain Node)
key-files:
  created:
    - apps/desktop/electron.vite.config.ts
    - apps/desktop/electron/main/index.ts
    - apps/desktop/electron/main/compat-paths.ts
    - apps/desktop/electron/preload/index.ts
  modified:
    - apps/desktop/package.json
    - package-lock.json
decisions:
  - Preload emitted as CommonJS .cjs because sandbox:true renderers cannot load ESM preloads (package is type:module).
  - compat-paths expressed as pure userDataDir(appData) + assertUserDataDir(path) instead of a const, so the DATA-01 crash-guard is unit-testable without booting Electron.
metrics:
  duration: ~15m
  completed: 2026-07-10
  tasks: 3
  files: 6
status: complete
---

# Phase 01 Plan 01: Electron Shell Scaffold + Data-Dir Lock Summary

Turned `apps/desktop` into an electron-vite project: a secure frameless BrowserWindow loads the existing React renderer unchanged (port 1420), with `userData` locked to the legacy Tauri dir `%APPDATA%\app.nyanko.desktop` before any path access.

## What Was Built

- **electron-vite scaffold** (`electron.vite.config.ts`): three-section config. Renderer reuses the existing `index.html` + `src/` unchanged (root `.`, `react()` plugin, `envPrefix ["VITE_","TAURI_ENV_"]`) and stays pinned to `port 1420` (`strictPort`) — load-bearing for the backend CORS allowlist (`desktop_url = http://localhost:1420`). Main entry `electron/main/index.ts`, preload entry `electron/preload/index.ts`.
- **Minimal secure preload** (`electron/preload/index.ts`): exposes only a `window.nyanko` placeholder (`appVersion`) via `contextBridge`. Does NOT define `__TAURI_INTERNALS__`, so the renderer degrades gracefully (custom titlebar / native calls stay dormant). Built as CommonJS `.cjs`.
- **compat-paths.ts** (`electron/main/compat-paths.ts`): electron-free single source of truth. Exports `LEGACY_APP_ID = "app.nyanko.desktop"`, `userDataDir(appData)` (uses only `node:path`), and `assertUserDataDir(resolved)` (throws unless the path ends in the legacy id). Verified to run under plain Node via `tsx` — no electron import.
- **main/index.ts bootstrap**: in exact order — `app.setPath('userData', userDataDir(app.getPath('appData')))` BEFORE any path access, then `assertUserDataDir(...)` crash-guard, then `whenReady` → frameless `BrowserWindow` (1180×760, min 760×560, `frame:false`, `show:false` → show on `ready-to-show`) with the mandatory secure `webPreferences` (`contextIsolation:true`, `nodeIntegration:false`, `sandbox:true`, `webSecurity:true`). Dual-path renderer load: `ELECTRON_RENDERER_URL` in dev, `loadFile` in prod. Quits on `window-all-closed`. No tray/sidecar/CSP/single-instance (deferred to later phases).
- **package.json**: added `electron`, `electron-vite`, `tsx` devDeps; `main: "out/main/index.js"`; scripts `dev`/`build`/`preview` → `electron-vite …`; `check` and `tauri` kept. `@tauri-apps/*` deps left untouched (removal is Phase 3 / SHELL-02).

## Verification

- `cd apps/desktop && npx electron-vite build` → main (`out/main/index.js`), preload (`out/preload/index.cjs`), and renderer (`out/renderer/…`) all compile with no errors.
- compat-paths ran under plain Node via `tsx`: `userDataDir` produces `…\app.nyanko.desktop`, `assertUserDataDir` accepts the legacy path and rejects a wrong one (`%APPDATA%\Nyanko`). This pre-validates the Plan 02 DATA-01 self-check.
- Runtime window proof (start backend :8765 + `npm run dev`) is the interactive human-check consolidated into Plan 02's checkpoint per the plan.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Sandboxed preload must be CommonJS, not ESM**
- **Found during:** Task 2/3 build gate.
- **Issue:** With `"type": "module"` in package.json, electron-vite emitted the preload as `out/preload/index.mjs` (ESM). A renderer with the mandatory `sandbox:true` cannot load an ESM preload — it must be CommonJS.
- **Fix:** Forced the preload build to CommonJS with `rollupOptions.output { format: "cjs", entryFileNames: "index.cjs" }` in `electron.vite.config.ts`, and pointed `webPreferences.preload` at `../preload/index.cjs` in `main/index.ts`.
- **Files modified:** `apps/desktop/electron.vite.config.ts`, `apps/desktop/electron/main/index.ts`.
- **Commits:** 01eedbe (config), 0dc06ce (main reference).

### Process notes (non-code)

- **Shared build gate:** Task 2's `electron-vite build` verify cannot pass without `electron/main/index.ts` (created in Task 3), since the config points the main entry there. The build was run once after Task 3; each task was still committed atomically (Task 2 = config/preload/package.json/lock; Task 3 = compat-paths/main).
- **.gitignore convention:** This repo intentionally keeps all `.gitignore` files untracked (root `.gitignore` line 1 is `.gitignore`). Added a local `apps/desktop/out/` rule to the (untracked) root `.gitignore` to keep electron-vite build output out of commits; the rule is active locally but, per repo convention, not committed. `apps/desktop/out/` is verified ignored.
- **Unrelated working-tree changes left untouched:** pre-existing deletions under `apps/desktop/src-tauri/` and modifications to `.planning/STATE.md` / `.planning/config.json` were present before this run and are out of scope — not staged.

## Known Stubs

- `window.nyanko` preload namespace exposes only `appVersion` — intentional placeholder; the full native bridge is Phase 3. The frameless window has no functional titlebar in this phase (HAS_TAURI is false); window controls are Phase 4 (NATIVE-04). Both are documented deferrals in the plan (key_findings #1, #4), not blocking stubs.

## Self-Check: PASSED

All five artifacts exist on disk; both task commits (01eedbe, 0dc06ce) exist in git.
