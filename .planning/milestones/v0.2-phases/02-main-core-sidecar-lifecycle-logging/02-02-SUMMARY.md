---
phase: 02-main-core-sidecar-lifecycle-logging
plan: 02
subsystem: desktop-shell
tags: [electron, sidecar, startup-gate, ipc, splash, logging, obs]
requires:
  - electron-vite-scaffold
  - secure-frameless-window
  - userdata-lock
  - sidecar-module        # 02-01 sidecar.ts (startSidecar/killSidecar/isDevMode)
  - logging-module        # 02-01 logging.ts (setupLogging/openLogsFolder/pipeSidecarOutput)
provides:
  - startup-gate          # index.ts runStartup(): splash → (prod) sidecar+readiness → main window
  - sidecar-lifecycle-wired
  - ipc-registrar         # first ipcMain.handle in the repo (analog for Phase 3 native.ts)
  - open-logs-action      # OBS-01 UI action
affects:
  - apps/desktop
tech-stack:
  added: []
  patterns:
    - "runStartup() gate: main-side readiness (GET /api/health) before showing the window"
    - "first ipcMain.handle + contextBridge invoke/send bridge (sandbox-safe)"
    - "secure splash BrowserWindow with inline HTML (dependency-free, same webPreferences as main)"
key-files:
  created:
    - apps/desktop/electron/main/ipc.ts
    - apps/desktop/electron/main/splash.ts
  modified:
    - apps/desktop/electron/main/index.ts
    - apps/desktop/electron/preload/index.ts
    - apps/desktop/src/DetectorSettingsView.tsx
    - apps/desktop/src/i18n.tsx
    - apps/desktop/src/vite-env.d.ts
decisions:
  - registerIpc is called ONCE in whenReady (not inside runStartup) — ipcMain.handle rejects duplicate channels, so re-registering on every Retry would crash. onRetry re-runs the gate without re-registering.
  - before-quit uses preventDefault → await killSidecar().finally(app.quit()) instead of registering killSidecar raw, so the async taskkill /T /F completes before the process exits (no orphan; criterion #2).
  - showSplashError toggles the error panel via webContents.executeJavaScript rather than adding an IPC listener the hardened preload doesn't expose.
metrics:
  completed: 2026-07-10
  tasks: 4  # 3 auto + 1 human-verify (all passed)
  files: 8
status: complete
---

# Phase 02 Plan 02: Startup gate + logs action Summary

Orchestrated the wave-1 modules (`sidecar.ts`, `logging.ts`) into the live Electron startup sequence and exposed the OBS-01 "open logs folder" action to the UI. In production the main process now shows a splash immediately, spawns `nyanko-api.exe` with an absolute `NYANKO_DATA_DIR`, waits for the port file + `GET /api/health` 200, and only then opens the main window — killing the old "Cargando biblioteca ~1min" at the root. In dev the sidecar is skipped. The sidecar is killed on every exit path, and a logs button in the "acerca" tab opens the real logs directory.

## What Was Built

- **`ipc.ts`** (new) — `registerIpc({ onRetry })`: the first `ipcMain.handle` in the repo (the analog Phase 3's `native.ts` will follow). Registers `openLogsFolder` (no renderer argument — always opens the fixed `app.getPath('logs')`, threat T-02-IPC), `startup:retry` (splash Retry → re-runs the gate), and `startup:quit` (splash Exit).
- **`splash.ts`** (new) — `createSplash()` returns a small (420×300) frameless `BrowserWindow` with the **exact** secure `webPreferences` as the main window (`contextIsolation`/`nodeIntegration:false`/`sandbox`/`webSecurity`) + the same hardened preload. Loads dependency-free inline HTML (data URL): a loading spinner plus a hidden error panel with Reintentar / Abrir logs / Salir wired to the `nyanko` bridge. `showSplashError(win)` reveals the error panel via `executeJavaScript`.
- **`index.ts`** (rewired) — DATA-01 lock kept first and unchanged. `setupLogging()` called early. `whenReady().then(createWindow)` replaced by `runStartup()`: opens the splash immediately, then (dev) skips the sidecar and opens the window, or (prod) `await startSidecar({ dataDir: userDataDir(app.getPath('appData')) })` then opens the window and closes the splash; on failure calls `showSplashError`. `createWindow()` now returns a Promise resolving on `ready-to-show`. `before-quit` kills the sidecar (awaited) on every exit path.
- **`preload/index.ts`** (extended) — `nyanko` namespace gains `openLogsFolder`/`retryStartup`/`quit` via `ipcRenderer.invoke`/`send`; `appVersion` preserved; no raw Node/ipcRenderer exposed.
- **`DetectorSettingsView.tsx`** — "open logs folder" button (new `<article>`) in the "acerca" tab, gated on `window.nyanko?.openLogsFolder`; error surfaced via the file's existing `setError` pattern. Existing Tauri calls untouched (Phase 3).
- **`i18n.tsx`** — `about.logs` / `about.logs.d` / `about.openLogs` in both es and en.
- **`vite-env.d.ts`** — `window.nyanko` global (optional) so the renderer typechecks.

## Verification (automated — PASSED)

- `npm run check` (tsc --noEmit) — clean, incl. the `window.nyanko` global.
- `npx electron-vite build` — main bundle now 9.30 kB, 6 modules (index/splash/ipc/sidecar/logging/compat-paths) transformed; preload + renderer clean.
- `npm run test:sidecar` — 6/6 pass. `npm run test:datadir` — 3/3 pass.

## Deviations from Plan

### Auto-fixed (Rule 1 — Bug)

1. **registerIpc once, not per runStartup call.** The plan listed `registerIpc` as step 2 inside `runStartup`; since Retry calls `runStartup` again, that would re-register `ipcMain.handle('openLogsFolder')` and throw "second handler". Moved the single `registerIpc({ onRetry: () => void runStartup() })` into the `whenReady` handler before the first `runStartup()`.
2. **before-quit awaits the kill.** The plan said `app.on("before-quit", killSidecar)`. Registering the async `killSidecar` raw lets the process exit before `taskkill /T /F` runs → orphan `nyanko-api.exe` (violates criterion #2). Implemented `preventDefault` + `void killSidecar().finally(() => app.quit())` with a `quitting` guard.

## Gap fixes found during human-verify (both committed)

Live testing surfaced two gaps the planner + checker missed; both fixed and re-verified:

1. **Renderer couldn't discover the sidecar's dynamic port in Electron** (`12a9310`). `api.ts` `readAppDataFile` was gated on `__TAURI_INTERNALS__`, so in Electron prod it fell back to the hardcoded `8765` while the sidecar bound a dynamic free port → "Failed to fetch". Fix: a **whitelisted** `nyanko.readAppDataFile(port|instance_token)` IPC (reads `userData`, rejects any other name) + an Electron branch in `api.ts`. This is the minimal slice of Phase 3's `native.ts` that criterion 1 requires. Files: `ipc.ts`, `preload/index.ts`, `api.ts`, `vite-env.d.ts`.
2. **`electron-vite preview` runs unpackaged → `app.isPackaged=false`** (`0dd4d99`), so the dev branch skipped the sidecar and `NYANKO_SIDECAR_EXE` did nothing under preview. Fix: treat `NYANKO_SIDECAR_EXE` as a force-prod signal so preview can exercise the real gate before packaging (Phase 5). Real `npm run dev` (no override) still short-circuits per D-10.

## Human-verify: PASSED (live UAT, 2026-07-10)

All 5 ROADMAP success criteria confirmed live by the user, once the clean-room contention (a stray `dev.py` + the old 0.1.15 app holding 8765 + a divergent `apps/backend/data` instance token) was cleared:
1. Prod cold-start (splash → `/api/health` gate → library loads cold, no "Cargando ~1min") — ✅ via `NYANKO_SIDECAR_EXE` + `electron-vite preview`.
2. No orphans — ✅ graceful close, `before-quit → killSidecar`, zero `nyanko-api.exe` after quit.
3. Logs button opens the real logs dir — ✅.
4. `main.log` (electron-log) + `sidecar.log` (piped uvicorn) under `app.getPath('logs')` — ✅ (verified on disk with content).
5. Dev omits the sidecar (manual backend) — ✅ no `nyanko-api.exe` spawned under `npm run dev`.

Note: window has no titlebar/close controls yet (frameless; controls are Phase 4 / NATIVE-04) — closed via right-click taskbar → Cerrar. Expected deferral, not a defect.

## Self-Check: PASSED

All 8 artifacts exist on disk; 5 commits (a33f0c8, b7590cf, d9a8bb9, 12a9310, 0dd4d99) exist in git. Automated gates (tsc, build, test:sidecar, test:datadir) and live human UAT of all 5 criteria pass.
