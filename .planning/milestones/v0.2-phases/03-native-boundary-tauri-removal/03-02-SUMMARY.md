---
phase: 03-native-boundary-tauri-removal
plan: 02
subsystem: desktop-renderer-native-migration
tags: [electron, tauri-removal, native-boundary, build, supply-chain]
requires:
  - "03-01 native.ts boundary (native, isNative, NATIVE_OPS) + wired window.nyanko ops"
provides:
  - "Renderer with zero @tauri-apps imports — every consumer routes through native.ts"
  - "api.ts data-dir read via native.readAppDataFile (single boundary, NATIVE-01)"
  - "package.json free of @tauri-apps deps and the tauri script; Rust-free green build"
affects:
  - "Phase 4 (autostart, window prefs, Discord RPC, window controls) — fills the throw/no-op stubs now reached from the renderer"
  - "Phase 5 (updater) — fills checkForUpdates stub reached from DetectorSettingsView"
tech_stack:
  added: []
  patterns:
    - "Renderer imports native.ts only for native ops; isNative gates the Electron path"
    - "Legacy helper modules (autostart/discord/windowPrefs) reduced to thin delegates over native"
    - "Dependency removal only — no new packages, supply-chain surface shrinks"
key_files:
  created: []
  modified:
    - apps/desktop/src/App.tsx
    - apps/desktop/src/DetectorSettingsView.tsx
    - apps/desktop/src/api.ts
    - apps/desktop/src/autostart.ts
    - apps/desktop/src/discord.ts
    - apps/desktop/src/windowPrefs.ts
    - apps/desktop/src/AccountSettingsView.tsx
    - apps/desktop/src/ExtensionSettingsView.tsx
    - apps/desktop/src/LibrarySettingsView.tsx
    - apps/desktop/src/LocalLibraryView.tsx
    - apps/desktop/src/TorrentsView.tsx
    - apps/desktop/src/native.ts
    - apps/desktop/package.json
    - package-lock.json
decisions:
  - "api.ts reads the data dir via native.readAppDataFile only — dropped the window.nyanko direct branch and the plugin-fs AppData fallback (both dead under Electron)"
  - "__TAURI_INTERNALS__ runtime guards swapped to native.isNative so the Electron path is taken; the HAS_TAURI titlebar render gate stays (still false under Electron until Phase 4)"
  - "isTauri kept as a variable name in LibrarySettingsView, now derived from isNative — cosmetic rename skipped for minimal diff"
metrics:
  duration: 12 min
  completed: 2026-07-11
  tasks: 3
  files: 14
status: complete
---

# Phase 3 Plan 02: Renderer Tauri Purge Summary

Every `@tauri-apps/*` import is gone from `apps/desktop/src` — all 11 renderer consumers now route native ops through the single `native.ts` boundary, the 9 Tauri deps + CLI devDep + `tauri` script are stripped from `package.json`, and `npm run build` is green with no Rust toolchain.

## What Was Built

- **Heavy consumers (Task 1):**
  - `api.ts` — `readAppDataFile` now resolves the data dir with `await native.readAppDataFile(name)` behind the `VITE_API_URL` guard; removed the `plugin-fs` import, the direct `window.nyanko` branch, and the `__TAURI_INTERNALS__`/`BaseDirectory.AppData` fallback (criterion 2 / NATIVE-01).
  - `App.tsx` — single `import { native, isNative } from "./native"` replaces the opener/event/window/notification imports. `openExternal`, `openPath`, `revealItemInDir`, `notify`, `onDetectionPaused`, and the Titlebar window controls route through `native`; the notification and detection-paused effects gate on `isNative`; `connectAccount`/`openExternal` collapse to `native.openExternal` (native owns the web fallback). Also rewired the pending-local `openPath` play button (line ~2804) not called out in the plan text (see Deviations).
  - `DetectorSettingsView.tsx` — `appVersion` via `native.appVersion()` under `isNative`; the whole Tauri updater orchestration (`check`/`confirm`/`invoke("stop_sidecar")`/`downloadAndInstall`/`relaunch`) collapses to `await native.checkForUpdates()` (Phase-5 throw-stub; existing `catch` surfaces the error); Patreon button uses `native.openExternal`.

- **Light consumers (Task 2):**
  - `autostart.ts`, `discord.ts`, `windowPrefs.ts` reduced to thin delegates over `native.*`; `DiscordActivity`/`WindowPrefs` types re-exported from `native.ts`. Call sites in App.tsx / DetectorSettingsView unchanged.
  - `AccountSettingsView`, `ExtensionSettingsView`, `TorrentsView`, `LocalLibraryView` — opener calls swapped to `native.openExternal` / `native.openPath` / `native.revealItemInDir`.
  - `LibrarySettingsView` — folder picker uses `native.openFolderDialog()` (returns `string | null`); `isTauri` now derives from `isNative`, keeping the `disabled` / `desktopOnly` gating (correctly enabled under Electron).

- **Build purge (Task 3):**
  - Removed 9 `@tauri-apps/*` dependencies, the `@tauri-apps/cli` devDependency, and the `"tauri": "tauri"` script from `apps/desktop/package.json`.
  - `npm install` pruned 11 packages from the lockfile.

## Verification

- `cd apps/desktop && npx tsc --noEmit` → exit 0 (after Task 1 and Task 2)
- `grep -rn "@tauri-apps" apps/desktop/src` → ZERO matches
- `grep -c "@tauri-apps" apps/desktop/package.json` → 0; `grep -c '"tauri"' apps/desktop/package.json` → 0
- `find apps/desktop -maxdepth 2 -name src-tauri -o -name tauri.conf.json` → nothing (already absent, confirmation only)
- `cd apps/desktop && npm run build` → exit 0 (electron-vite, no Rust)
- `cd apps/desktop && npm run test:native` → 2 pass / 0 fail (03-01 self-check intact)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Extra `openPath` call site in App.tsx not listed in the plan**
- **Found during:** Task 1
- **Issue:** The plan called out the `openPath`/`revealItemInDir` sites in `libraryItemMenu` (~lines 1027-1028) but not a second `openPath(item.next_path)` on the pending-local play button (~line 2804). Removing the `@tauri-apps/plugin-opener` import would have left this as a broken reference (tsc error), blocking Task 1.
- **Fix:** Rewired it to `native.openPath(item.next_path)` — same boundary as the other opener sites.
- **Files modified:** apps/desktop/src/App.tsx
- **Commit:** 43b399b

**2. [Rule 3 - Blocking] Literal `@tauri-apps` string in a native.ts comment tripped the acceptance grep**
- **Found during:** Task 3
- **Issue:** `native.ts` (a 03-01 artifact, not in this plan's `files_modified`) carried a prose comment mentioning `@tauri-apps/*`. It is not an import, but the acceptance criterion `grep -rc "@tauri-apps" apps/desktop/src` must return 0 literally.
- **Fix:** Reworded the comment ("ningún import de Tauri") — no code change. `native.ts` is listed in the plan's `must_haves.artifacts`, so touching it is in scope.
- **Files modified:** apps/desktop/src/native.ts
- **Commit:** 5c55370

## Known Stubs

No new stubs introduced by this plan. The Phase 4/5 stubs on `native.ts` (window controls, autostart, window prefs, Discord RPC, updater — documented in 03-01-SUMMARY) are now *reached* from the renderer: window-control and `checkForUpdates` are throw-stubs (a dead button surfaces as an error, by design); autostart/prefs/discord are safe no-ops. All are phase-tagged and filled by Phases 4/5.

## Threat Flags

None. This plan only redirects existing consumers through the 03-01 boundary and removes dependencies — no new IPC surface, endpoints, or capabilities (matches threat register T-03-05/T-03-06/T-03-SC).

## Self-Check: PASSED

- Modified files exist on disk (14 files, all present).
- Task commits present: 43b399b (Task 1), 4f35750 (Task 2), 5c55370 (Task 3).
- `grep -rn "@tauri-apps" apps/desktop/src` → 0; build + test:native green.
