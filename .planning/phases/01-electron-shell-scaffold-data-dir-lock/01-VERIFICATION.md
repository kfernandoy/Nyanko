---
phase: 01-electron-shell-scaffold-data-dir-lock
verified: 2026-07-10T00:00:00Z
status: passed
score: 4/4 must-haves verified
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: null
---

# Phase 1: Electron shell scaffold + data-dir lock — Verification Report

**Phase Goal:** `apps/desktop` corre como app electron-vite en desarrollo, cargando el renderer React actual sin cambios de UI, contra un data dir compatible con producción. (SHELL-01, DATA-01)
**Verified:** 2026-07-10
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria)

| # | Truth | Status | Evidence |
| --- | --- | --- | --- |
| 1 (SHELL-01 / SC1) | `electron-vite dev` launches the existing React renderer unchanged; library loads against the manual :8765 backend | ✓ VERIFIED | `electron.vite.config.ts` renderer root `.` reuses existing `index.html`+`src/`; `npx electron-vite build` compiles all three bundles (main 1.56kB, preload .cjs, renderer 63 modules); `git diff HEAD~6 HEAD -- apps/desktop/src/` is empty (renderer untouched); port 1420 pinned `strictPort` and present in backend `config.py` `desktop_url`/`allowed_origins`; human ran the shell and confirmed library loaded (01-02-SUMMARY, approved) |
| 2 (SC2) | Frameless window opens with contextIsolation:true, nodeIntegration:false, sandbox:true, webSecurity:true | ✓ VERIFIED | `electron/main/index.ts:20-28` — `frame:false` + webPreferences with all four flags verbatim |
| 3 (SC3 / DATA-01) | `app.getPath('userData')` resolves to `%APPDATA%\app.nyanko.desktop`; prod library loads without migration | ✓ VERIFIED | `index.ts:11` `app.setPath("userData", userDataDir(app.getPath("appData")))` runs at module top-level BEFORE `createWindow` (only called via `whenReady` at :43); `userDataDir` joins `LEGACY_APP_ID = "app.nyanko.desktop"`; human confirmed library loaded unchanged and faster than Tauri (approved) |
| 4 (SC4 / DATA-01) | Boot crashes if userData resolves elsewhere; provable by self-check | ✓ VERIFIED | `index.ts:12` `assertUserDataDir(app.getPath("userData"))` runs immediately after setPath, before window; `compat-paths.ts` guard throws unless path ends in legacy id; `npm run test:datadir` → **3 pass / 0 fail** (accepts legacy, rejects `%APPDATA%\Nyanko`) |

**Score:** 4/4 truths verified (0 present, behavior-unverified)

### Scope Discipline (must-NOT)

| Check | Status | Evidence |
| --- | --- | --- |
| `@tauri-apps/*` deps retained (removal is Phase 3) | ✓ VERIFIED | `package.json` still lists 9 `@tauri-apps/*` deps + `@tauri-apps/cli` |
| No sidecar/tray/native.ts/packaging leaked in | ✓ VERIFIED | `electron/main/` contains only `index.ts`, `compat-paths.ts`, `compat-paths.test.ts` — no `native.ts`/`tray.ts`/`sidecar.ts`; no electron-builder/updater added |
| compat-paths.ts is electron-free | ✓ VERIFIED | Imports only `node:path`; no electron import — self-check runs under plain Node via tsx |

### Required Artifacts

| Artifact | Expected | Status | Details |
| --- | --- | --- | --- |
| `electron.vite.config.ts` | 3-section config, renderer :1420 | ✓ VERIFIED | main/preload/renderer wired; preload forced CJS `.cjs`; port 1420 strictPort |
| `electron/main/index.ts` | userData lock + assert + secure frameless window | ✓ VERIFIED | setPath→assert→whenReady ordering; secure webPreferences; dual-path renderer load |
| `electron/main/compat-paths.ts` | LEGACY_APP_ID + userDataDir + assertUserDataDir, electron-free | ✓ VERIFIED | all three symbols exported; node:path only |
| `electron/main/compat-paths.test.ts` | node:test self-check, 3 cases | ✓ VERIFIED | imports same guard main uses; 3/3 pass |
| `electron/preload/index.ts` | minimal secure preload, no __TAURI_INTERNALS__ | ✓ VERIFIED | only `contextBridge` + `window.nyanko` placeholder; no Tauri internals |
| `package.json` | electron-vite scripts + main field + test:datadir | ✓ VERIFIED | dev/build/preview → electron-vite; `main: out/main/index.js`; test:datadir added |

### Key Link Verification

| From | To | Via | Status |
| --- | --- | --- | --- |
| renderer dev server | backend CORS | port 1420 = `config.py` desktop_url | ✓ WIRED — both pinned to 1420, desktop_url in allowed_origins |
| index.ts | userData legacy path | setPath BEFORE any getPath/window | ✓ WIRED — line 11 top-level, before whenReady:43 |
| index.ts | crash-early guard | assertUserDataDir(getPath('userData')) | ✓ WIRED — line 12, before window |
| compat-paths.test.ts | boot guard | imports same compat-paths module | ✓ WIRED — one source of truth |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| --- | --- | --- | --- |
| Data-dir crash-guard | `npm run test:datadir` | 3 pass / 0 fail | ✓ PASS |
| Sanctioned build (SHELL-01) | `npx electron-vite build` | main+preload+renderer built, no errors | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan | Status | Evidence |
| --- | --- | --- | --- |
| SHELL-01 | 01-01 | ✓ SATISFIED | electron-vite dev/build scaffold, renderer unchanged, port 1420 |
| DATA-01 | 01-01, 01-02 | ✓ SATISFIED | setPath+assert ordering in source + passing self-check |

### Anti-Patterns Found

None blocking. `window.nyanko.appVersion` placeholder and no functional titlebar are documented, intentional Phase 3/4 deferrals (key_findings #1/#4), not stubs against this phase's goal.

### Human Verification Required

None outstanding. The interactive shell run (library loads unchanged against manual backend, userData = legacy path) was performed and human-approved (01-02-SUMMARY). The live forced-wrong-path crash demo was not manually run, but SC4 requires only "verificable con un self-check" — the automated self-check passes, satisfying the criterion.

### Gaps Summary

No gaps. All four ROADMAP success criteria are verified in source and by re-run automated checks (build + self-check both pass live). Ordering for the DATA-01 mitigation (setPath → assert → window) is confirmed in the actual `index.ts`, not merely claimed. Scope discipline held: Tauri deps retained, no later-phase work leaked in.

---

_Verified: 2026-07-10_
_Verifier: Claude (gsd-verifier)_
