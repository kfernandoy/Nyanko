---
phase: 03-native-boundary-tauri-removal
plan: 01
subsystem: desktop-native-boundary
tags: [electron, ipc, contextBridge, native-boundary, security]
requires:
  - "Phase 2 window.nyanko namespace (preload) + registerIpc registry (ipc.ts)"
provides:
  - "apps/desktop/src/native.ts — single native boundary (native, isNative, NATIVE_OPS)"
  - "window.nyanko wired ops: openExternal, openPath, revealItemInDir, openFolderDialog, appVersion, notify, onDetectionPaused"
  - "WindowPrefs + DiscordActivity types (new home; windowPrefs.ts/discord.ts reduce to re-exports in 03-02)"
  - "test:native self-check script"
affects:
  - "03-02 renderer migration (imports native.ts instead of @tauri-apps/*)"
  - "Phase 4 (autostart, window prefs, Discord RPC, window controls) — fills stubs"
  - "Phase 5 (updater) — fills checkForUpdates stub"
tech_stack:
  added: []
  patterns:
    - "Specific typed IPC methods on contextBridge (never raw ipcRenderer/invoke)"
    - "Input validation at the renderer->main trust boundary (scheme/path checks)"
    - "Phase-tagged ponytail stubs kept on the boundary + manifest so self-check stays honest"
key_files:
  created:
    - apps/desktop/src/native.ts
    - apps/desktop/src/native.test.ts
  modified:
    - apps/desktop/electron/preload/index.ts
    - apps/desktop/electron/main/ipc.ts
    - apps/desktop/src/vite-env.d.ts
    - apps/desktop/package.json
decisions:
  - "Wired ops keep web/dev fallbacks (window.open, no-op, null) so native.ts imports cleanly without the bridge"
  - "Window-control + updater stubs THROW (dead button must surface); autostart/prefs/discord stubs are safe no-ops"
metrics:
  duration: 8 min
  completed: 2026-07-11
  tasks: 3
  files: 6
status: complete
---

# Phase 3 Plan 01: Native Boundary Foundation Summary

Single `native.ts` boundary now backs every former `@tauri-apps` op via `window.nyanko` under `contextIsolation:true` — 8 wired ops with input validation, 10 phase-tagged stubs, and an assert-based symmetry self-check.

## What Was Built

- **`apps/desktop/src/native.ts`** — the one module the renderer imports for native ops. Exports `native` (18 ops), `isNative`, `NATIVE_OPS` manifest, and `WindowPrefs`/`DiscordActivity` types. All `window` access is inside function bodies so the file imports cleanly under `node --import tsx` (no DOM) for the self-check.
- **Preload bridge** (`electron/preload/index.ts`) — extended `window.nyanko` with 7 new specific typed methods (`openExternal`, `openPath`, `revealItemInDir`, `openFolderDialog`, `appVersion`, `notify`, `onDetectionPaused`). `appVersion` moved from the `""` prod placeholder to an `appVersion()` invoke. `onDetectionPaused` returns an unsubscribe to avoid listener leaks.
- **IPC handlers** (`electron/main/ipc.ts`) — 6 new `ipcMain.handle` handlers wired to `shell`/`dialog`/`Notification`/`BrowserWindow`, each validating renderer-supplied args.
- **Type surface** (`vite-env.d.ts`) — extended `Window.nyanko` with the new signatures; `appVersion` is now `() => Promise<string>`.
- **Self-check** (`native.test.ts` + `test:native` script) — enforces two-way symmetry between `native` and `NATIVE_OPS`.

## Wired vs. Stub Surface

- **Wired now (8):** openExternal, openPath, revealItemInDir, openFolderDialog, appVersion, notify, onDetectionPaused, readAppDataFile (Phase 2).
- **Phase 4 no-op stubs:** getAutostart (false), setAutostart, getWindowPrefs (defaults), setWindowPrefs, setDiscordActivity, clearDiscordActivity.
- **Phase 4 throw stubs:** minimizeWindow, toggleMaximizeWindow, closeWindow (a dead window button is a bug we want surfaced).
- **Phase 5 throw stub:** checkForUpdates.

Each stub carries a `ponytail:` comment naming its owning phase/requirement.

## Security Mitigations Applied

| Threat | Mitigation |
|--------|-----------|
| T-03-01 (high) | `readAppDataFile` whitelist left exactly `{port, instance_token}` — not widened. |
| T-03-02 (high) | `openExternal` accepts only `^https?://`; `openPath`/`revealItemInDir` reject any string containing `://`. |
| T-03-03 (high) | Bridge exposes only specific typed methods — no raw `ipcRenderer`, no generic `invoke`. |
| T-03-04 (low, accepted) | `notify` title/body are the app's own i18n strings. |

## Verification

- `cd apps/desktop && npx tsc --noEmit` → exit 0
- `cd apps/desktop && npm run test:native` → 2 pass / 0 fail
- Sanity: removing one op from `NATIVE_OPS` makes `test:native` exit 1 (proves success criterion 3), then restored.
- `grep -c ipcMain.handle` → 10 (>= 8 required)
- Bridge exposes 7 new + 4 existing methods; no raw `ipcRenderer`/`invoke`.

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

Intentional, tracked, and phase-owned (from `<boundary_strategy>` — required so no `@tauri-apps` import survives):

| Op | File | Owning phase |
|----|------|--------------|
| getAutostart / setAutostart | native.ts | Phase 4 (NATIVE-06) |
| getWindowPrefs / setWindowPrefs | native.ts | Phase 4 (NATIVE-04) |
| setDiscordActivity / clearDiscordActivity | native.ts | Phase 4 (NATIVE-05) |
| minimizeWindow / toggleMaximizeWindow / closeWindow | native.ts | Phase 4 (NATIVE-04) |
| checkForUpdates | native.ts | Phase 5 (PKG-02) |

These are on the boundary + `NATIVE_OPS` manifest deliberately (per plan `<notes>`); they do not block plan 03-01's goal (the boundary surface exists and compiles). Filled by Phases 4/5.

## Self-Check: PASSED
