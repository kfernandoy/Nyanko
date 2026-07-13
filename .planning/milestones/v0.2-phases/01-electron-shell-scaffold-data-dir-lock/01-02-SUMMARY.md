---
phase: 01-electron-shell-scaffold-data-dir-lock
plan: 02
subsystem: desktop-shell
tags: [electron, data-dir, testing, migration, security]
requires:
  - compat-paths-module
  - secure-frameless-window
  - userdata-lock
provides:
  - datadir-selfcheck
affects:
  - apps/desktop
tech-stack:
  added: []
  patterns:
    - node:test/node:assert self-check run under tsx (no test framework dep)
key-files:
  created:
    - apps/desktop/electron/main/compat-paths.test.ts
  modified:
    - apps/desktop/package.json
decisions:
  - Self-check imports the same compat-paths guard main/index.ts boots with — one source of truth, tested without an electron mock.
metrics:
  duration: ~10m
  completed: 2026-07-10
  tasks: 2
  files: 2
status: complete
---

# Phase 01 Plan 02: Data-Dir Guard Self-Check + Shell Proof Summary

Pinned the DATA-01 crash-guard with an assert-based `node:test` self-check and confirmed the full Electron shell runs end-to-end: the frameless window loads the existing production library unchanged against the manual Python backend.

## What Was Built

- **compat-paths.test.ts** (`electron/main/compat-paths.test.ts`): three `node:test`/`node:assert` cases importing the electron-free `compat-paths` guard — the same module `main/index.ts` uses at boot. Asserts `userDataDir(...)` ends in `app.nyanko.desktop`, `assertUserDataDir` accepts the legacy path, and it throws on `%APPDATA%\Nyanko` (the exact orphaned-library failure mode). Runs under plain Node via tsx — no electron mock, no app boot.
- **package.json**: added `"test:datadir": "node --import tsx --test electron/main/compat-paths.test.ts"`.

## Verification

- **Automated (Task 1):** `cd apps/desktop && npm run test:datadir` → 3 pass, 0 fail. Legacy path accepted, `%APPDATA%\Nyanko` rejected, `userDataDir` ends in `app.nyanko.desktop`. This is the runnable proof of DATA-01 Success Criterion 4.
- **Interactive (Task 2, human-approved):** User ran the full shell against a manually-started backend (uvicorn on `127.0.0.1:8765` via `apps/backend/scripts/dev.py`) and confirmed the frameless window opened and the existing library loaded UNCHANGED — notably faster than the old Tauri startup, implying `userData` resolved to the legacy `%APPDATA%\app.nyanko.desktop` and the existing production library was found without migration. The forced-wrong-path crash was not manually demoed; it is covered by the automated self-check above.

## Deviations from Plan

### Environment / setup gotcha (non-code, does NOT block)

**1. Electron binary not auto-downloaded under npm workspaces**
- **Found during:** Task 2 interactive run.
- **Issue:** Under npm workspaces, `electron` hoisted to `Nyanko/node_modules/electron` and its binary was not fetched by the executor's `npm install`; `npm run dev` failed with `Error: Electron uninstall` until the binary was fetched manually.
- **Workaround:** `node node_modules/electron/install.js` to download the binary.
- **Impact:** Setup-only, no code defect. Flag to harden in Phase 5 (packaging).

No code deviations — Task 1 executed exactly as written.

## Known Stubs

None.

## Self-Check: PASSED

Both artifacts exist on disk; Task 1 commit (0430119) exists in git; `npm run test:datadir` passes.
