---
phase: 04-native-feature-parity
plan: 01
subsystem: desktop-shell
tags: [electron, native, window-controls, titlebar, icon, ipc]
requires:
  - "frame:false BrowserWindow (Phase 2)"
  - "native.ts boundary + NATIVE_OPS self-check (Phase 3)"
  - "ipc.ts registerIpc registry (Phase 2/3)"
provides:
  - "build/icon.png (256x256 brand icon) reused by tray Plan 02 + Phase 5 packaging"
  - "window:minimize / window:toggle-maximize / window:close IPC channels"
  - "nyanko bridge methods minimizeWindow/toggleMaximizeWindow/closeWindow"
  - "frameless titlebar rendered under Electron (isNative gate)"
affects:
  - apps/desktop/electron/main/index.ts
  - apps/desktop/electron/main/ipc.ts
  - apps/desktop/electron/preload/index.ts
  - apps/desktop/src/native.ts
  - apps/desktop/src/App.tsx
tech-stack:
  added: []
  patterns:
    - "renderer -> native.ts -> window.nyanko bridge -> ipcMain.handle (named typed channels only)"
    - "window-control handlers scoped to BrowserWindow.fromWebContents(event.sender)"
key-files:
  created:
    - apps/desktop/build/icon.png
  modified:
    - apps/desktop/electron/main/index.ts
    - apps/desktop/electron/main/ipc.ts
    - apps/desktop/electron/preload/index.ts
    - apps/desktop/src/native.ts
    - apps/desktop/src/vite-env.d.ts
    - apps/desktop/src/App.tsx
decisions:
  - "D-07: single brand icon sourced from apps/extension/src/icons/icon-128.png (git history holds no .ico, only .gitkeep) upscaled to 256x256 via sharp"
  - "D-04: titlebar reused verbatim; only the render gate flipped HAS_TAURI -> isNative and stub bodies filled — no visual redesign"
metrics:
  duration: ~20m
  completed: 2026-07-11
status: complete
---

# Phase 4 Plan 01: Frameless Window Controls + Brand Icon Summary

Made the existing 0.1.15 React titlebar render under Electron and wired its minimize/maximize/close buttons to sender-scoped IPC, plus sourced the single 256x256 brand app icon (D-07) reused by the Phase-2 tray and Phase-5 packaging.

## What Was Built

**Task 1 — Brand app icon (commit bf3a0cc)**
- Generated `apps/desktop/build/icon.png` (256x256 PNG) from the extension brand asset `apps/extension/src/icons/icon-128.png` using the already-hoisted `sharp` dependency (one-off `node` invocation, no build step added). Git history carries no `.ico` (only `.gitkeep`), so per D-07 the recovery falls back to the brand asset.
- Set `icon: join(__dirname, "../../build/icon.png")` on the main `BrowserWindow` in `electron/main/index.ts`. Did not touch `contextIsolation`/`nodeIntegration`/`sandbox`/`webSecurity`.

**Task 2 — Window controls IPC + titlebar gate (commit fac0ac7)**
- Added three handlers to `registerIpc` in `electron/main/ipc.ts`: `window:minimize`, `window:toggle-maximize`, `window:close`. Each operates only on `BrowserWindow.fromWebContents(event.sender)` and accepts no payload (T-04-01 mitigation).
- Exposed three named typed methods on the `nyanko` contextBridge in `electron/preload/index.ts` — never raw `ipcRenderer` (T-04-02 mitigation).
- Filled the three `native.ts` throw-stubs with the wired-op + web-fallback no-op pattern (`window.nyanko?.minimizeWindow() ?? Promise.resolve()`). `NATIVE_OPS` unchanged; `native.test.ts` stays 2/2.
- Flipped the `App.tsx` titlebar render gate from `HAS_TAURI` to `isNative` at both use sites (`{isNative && <Titlebar />}` and the `with-titlebar` class) and removed the stale "titlebar oculto hasta Fase 4" comment. Titlebar JSX/styles left verbatim (D-04).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Added window-control methods to the nyanko type declaration**
- **Found during:** Task 2
- **Issue:** `apps/desktop/src/vite-env.d.ts` declares the `window.nyanko` bridge type. Filling the native.ts stubs to call `window.nyanko?.minimizeWindow()` (etc.) would fail `tsc --noEmit` because those methods were absent from the interface.
- **Fix:** Added `minimizeWindow`/`toggleMaximizeWindow`/`closeWindow` (all `() => Promise<void>`) to the `Window.nyanko` interface — the typed surface that mirrors the preload bridge.
- **Files modified:** apps/desktop/src/vite-env.d.ts
- **Commit:** fac0ac7

The plan's `files_modified` list did not include `vite-env.d.ts`, but it is the canonical home of the bridge type and the change is required for `npm run check` to pass — part of the same typed-bridge wiring.

## Verification Results

- `npm run test:native` → 2 pass / 0 fail (NATIVE_OPS ↔ native symmetry intact).
- `npm run check` (tsc --noEmit) → exit 0.
- `npm run build` (electron-vite) → exit 0.
- Acceptance greps: `ipcMain.handle("window:` = 3; preload window methods = 3; `throw new Error` in native.ts = 1 (only `checkForUpdates`, Phase 5); `isNative` in App.tsx = 6; `HAS_TAURI` in App.tsx = 0.
- Icon: `build/icon.png` present, 256x256.

Manual verification (titlebar visible; minimize hides to taskbar; close exits) is carried to phase verify — requires a running dev session.

## Known Stubs

None introduced. `native.checkForUpdates` remains an intentional throw-stub (Phase 5, PKG-02) — out of scope for this plan.

## Self-Check: PASSED

- FOUND: apps/desktop/build/icon.png
- FOUND commit: bf3a0cc (Task 1)
- FOUND commit: fac0ac7 (Task 2)
