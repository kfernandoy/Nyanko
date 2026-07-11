---
phase: 04-native-feature-parity
plan: 02
subsystem: desktop-shell
tags: [electron, native, tray, window-prefs, ipc, detection]
requires:
  - "build/icon.png (brand icon from Plan 01) reused as the tray icon"
  - "native.ts boundary + NATIVE_OPS self-check (Phase 3)"
  - "ipc.ts registerIpc registry + preload nyanko bridge (Phase 2/3)"
  - "onDetectionPaused preload subscription (Phase 3) — receiver for tray toggle"
  - "before-quit killSidecar path (Phase 2) — reused by tray Salir"
provides:
  - "window_prefs.json persistence (3-boolean schema) in the app data dir"
  - "window-prefs:get / window-prefs:set IPC channels"
  - "nyanko bridge methods getWindowPrefs/setWindowPrefs"
  - "system tray: Spanish menu, double-click show, detection pause/resume POST"
  - "close/minimize-to-tray + start-minimized window behavior"
affects:
  - apps/desktop/electron/main/index.ts
  - apps/desktop/electron/main/ipc.ts
  - apps/desktop/electron/preload/index.ts
  - apps/desktop/src/native.ts
  - apps/desktop/src/vite-env.d.ts
tech-stack:
  added: []
  patterns:
    - "electron-free pure core (load/save take dir) + in-memory cache, mirroring compat-paths.ts — testable under node --import tsx without electron"
    - "renderer payload coerced to exactly three booleans before persisting (T-04-05); fs write hard-scoped to app.getPath(userData) (T-04-04)"
    - "tray detection POST fixed to http://127.0.0.1:{port} from userData/port, fallback 8765 (T-04-06)"
    - "before-quit sets isQuitting before window close events → tray Salir quits cleanly through existing killSidecar"
key-files:
  created:
    - apps/desktop/electron/main/window-prefs.ts
    - apps/desktop/electron/main/window-prefs.test.ts
    - apps/desktop/electron/main/tray.ts
  modified:
    - apps/desktop/electron/main/index.ts
    - apps/desktop/electron/main/ipc.ts
    - apps/desktop/electron/preload/index.ts
    - apps/desktop/src/native.ts
    - apps/desktop/src/vite-env.d.ts
    - apps/desktop/package.json
decisions:
  - "D-05: window_prefs.json at app.getPath(userData) = %APPDATA%\\app.nyanko.desktop; missing/malformed → defaults, no migration"
  - "D-06: tray labels kept accented 'detección' matching the authoritative Rust tray.rs (D-08 parity source), not the ASCII must_haves paraphrase"
  - "D-08 parity: start_minimized leaves the window hidden (in tray) exactly like lib.rs, rather than win.minimize()"
  - "window-prefs.ts core kept electron-free (dir as param) instead of a top-level electron import, so test:prefs runs under plain node — deviation from the plan's no-arg signature, same testability intent"
  - "tray Salir calls app.quit() only; before-quit (emitted before window close) sets isQuitting — no onQuit callback threaded into setupTray"
metrics:
  duration: ~15m
  completed: 2026-07-11
status: complete
---

# Phase 4 Plan 02: System Tray + Window Prefs Persistence/Behavior Summary

Delivered NATIVE-03 (system tray with Spanish menu, double-click show, and detection pause/resume POST to the local sidecar) and the persistence/behavior half of NATIVE-04 (window_prefs.json round-trip plus close/minimize-to-tray and start-minimized), mirroring the deleted Rust tray.rs / window_prefs.rs / lib.rs exactly.

## What Was Built

**Task 1 — window_prefs.json persistence + IPC + native bodies (commit dc26bfa)**
- `electron/main/window-prefs.ts`: electron-free pure core mirroring compat-paths.ts. `loadWindowPrefs(dir)` / `saveWindowPrefs(dir, input)` take the dir explicitly; `coercePrefs` forces exactly `{close_to_tray, minimize_to_tray, start_minimized}` booleans and drops unknown keys (T-04-05). An in-memory cache (`seedWindowPrefs`/`currentWindowPrefs`/`updateWindowPrefs`) replaces the Rust `WindowPrefsState`. Missing/malformed file → defaults, no migration (D-05).
- `window-prefs:get`/`window-prefs:set` handlers registered in `ipc.ts`; the write is hard-scoped to the seeded userData dir (T-04-04) — never a renderer path.
- Preload `getWindowPrefs`/`setWindowPrefs` named bridge methods (T-04-07); matching types added to `vite-env.d.ts`.
- Filled `native.ts` `getWindowPrefs`/`setWindowPrefs` bodies with the wired-op + web-fallback pattern. `NATIVE_OPS` unchanged.
- `window-prefs.test.ts` (node:test, tmp dir) asserts round-trip of `{close_to_tray:true}`, unknown-key drop (incl. `__proto__`/`hacker`), coercion, and missing-file defaults; `test:prefs` script added.

**Task 2 — tray.ts module (commit 4f9829c)**
- Electron `Tray` from `build/icon.png` (D-07 reuse). Menu, in Spanish (D-06): Mostrar (restore+show+focus), Ocultar (hide), a pause/resume item whose label reflects `detectionPaused`, separator, Salir.
- Double-click shows+focuses the window (menu stays on right-click, Windows convention).
- Detection toggle POSTs to `http://127.0.0.1:{port}/api/detection/{pause|resume}` — port from `userData/port`, fallback 8765, 5s `AbortSignal.timeout` (T-04-06). On HTTP/network error: logs and does NOT flip state (mirror tray.rs). On success: flips the boolean, rebuilds the menu label, emits `detection-paused` to the renderer.
- `setupTray(getMainWindow)` is idempotent (a splash Retry won't spawn a second tray).

**Task 3 — wire tray + prefs behavior into main (commit d5b9249)**
- Module-level `mainWindow` ref + `isQuitting` flag.
- `seedWindowPrefs(app.getPath("userData"))` before `createWindow()`; `setupTray(() => mainWindow)` after the window exists.
- `close` listener: `close_to_tray && !isQuitting` → `preventDefault()` + hide (paridad lib.rs CloseRequested). `minimize` listener: `minimize_to_tray` → hide (paridad Resized+is_minimized).
- `ready-to-show`: `start_minimized || --minimized` keeps the window hidden instead of showing.
- `before-quit` now sets `isQuitting` (emitted before window close, so tray Salir → `app.quit()` closes cleanly) and reuses the existing `killSidecar` path — no second sidecar-kill.

## Deviations from Plan

### Auto-fixed / discretionary adjustments

**1. [Discretion] window-prefs core kept electron-free with an explicit dir param**
- The plan sketched `loadWindowPrefs(): WindowPrefs` with an injectable dir defaulting to `app.getPath("userData")`. A default parameter requires a top-level `electron` import, which breaks `test:prefs` under plain node.
- Instead the pure functions take `dir` as a required arg (exactly the compat-paths.ts pattern the plan told me to mirror), and the userData dir is injected once via `seedWindowPrefs` from index.ts. Same testability intent, honored the "electron-free, mechanically verifiable T-04-05" requirement. IPC registration lives in `ipc.ts` (explicitly Claude's discretion).

**2. [Discretion] Tray Salir sets isQuitting via before-quit, not a threaded callback**
- The plan said "Salir must set the shared isQuitting flag then app.quit()". Electron emits `before-quit` before any window `close` event, so `app.quit()` alone suffices: `before-quit` sets `isQuitting` before the close listener runs. Avoided threading an `onQuit` callback through `setupTray`, keeping the plan's `setupTray(getMainWindow)` signature.

**3. [Parity, D-08] Kept accented "detección" in tray labels**
- The plan's ASCII `must_haves` paraphrase wrote "Pausar deteccion". The authoritative Rust `tray.rs` (D-08 parity source of truth) uses "Pausar detección"/"Reanudar detección" with the accent. Kept the accent for exact 0.1.15 parity. All four Spanish labels present.

No architectural changes; no auth gates.

## Verification Results

- `npm run test:prefs` → 4 pass / 0 fail (round-trip, unknown-key drop, coercion, missing-file defaults).
- `npm run test:native` → 2 pass / 0 fail (NATIVE_OPS ↔ native symmetry intact).
- `npm run check` (tsc --noEmit) → exit 0.
- `npm run build` (electron-vite) → exit 0.
- Acceptance greps: `window-prefs:` in ipc.ts = 2; `getWindowPrefs|setWindowPrefs` in preload = 2; tray labels grep = 8; `/api/detection/` = 2 (pause+resume present); index.ts prefs keys = 6, `isQuitting` = 4, `setupTray` = 2, `--minimized` = 1.
- No untracked files left behind.

Manual verification (tray menu items visible; double-click restores; toggling detection changes the label and the sidecar receives pause/resume; close-to-tray hides on close and Mostrar restores) is carried to phase verify — requires a running dev session with the sidecar.

## Known Stubs

None introduced. Remaining `native.ts` stubs (`getAutostart`/`setAutostart` NATIVE-06, `setDiscordActivity`/`clearDiscordActivity` NATIVE-05, `checkForUpdates` Phase 5) are out of scope for this plan and handled by Plan 03 / Phase 5.

## Self-Check: PASSED

- FOUND: apps/desktop/electron/main/window-prefs.ts
- FOUND: apps/desktop/electron/main/window-prefs.test.ts
- FOUND: apps/desktop/electron/main/tray.ts
- FOUND commit: dc26bfa (Task 1)
- FOUND commit: 4f9829c (Task 2)
- FOUND commit: d5b9249 (Task 3)
