---
phase: 02-main-core-sidecar-lifecycle-logging
plan: 01
subsystem: infra
tags: [electron, electron-log, sidecar, pyinstaller, child_process, taskkill, node-test, tsx]

# Dependency graph
requires:
  - phase: 01-foundation
    provides: "compat-paths.userDataDir() (absolute NYANKO_DATA_DIR value) + node:test-under-tsx self-check discipline"
provides:
  - "sidecar.ts: pure helpers (parsePortFile/isDevMode/healthUrl/resolveSidecarExe) + thin wrappers startSidecar/killSidecar"
  - "startSidecar: stale-port delete → spawn (absolute exe, shell:false, absolute NYANKO_DATA_DIR) → port-file wait ≤30s → GET /api/health 200, fail-fast on early exit, one auto re-spawn"
  - "killSidecar: single reusable graceful→taskkill /T /F on tracked pid, no-op when idle (before-quit + updater share it)"
  - "logging.ts: setupLogging (main.log), openLogsFolder (zero-arg, fixed logs dir), pipeSidecarOutput (sidecar.log)"
  - "electron-log dependency + test:sidecar npm script"
affects: [02-02, splash, index-wiring, ipc, phase-3-native, phase-5-updater]

# Tech tracking
tech-stack:
  added: [electron-log@^5.4.4]
  patterns: ["pure Electron-free helpers + deferred electron import so node:test drives logic without booting Electron", "single reusable killSidecar for all exit paths"]

key-files:
  created:
    - apps/desktop/electron/main/logging.ts
    - apps/desktop/electron/main/sidecar.ts
    - apps/desktop/electron/main/sidecar.test.ts
  modified:
    - apps/desktop/package.json

key-decisions:
  - "Deferred (dynamic) import of ./logging inside startSidecar so sidecar.ts pure helpers load under plain Node — self-check needs no Electron"
  - "parsePortFile uses Number()+Number.isInteger to reject floats/garbage, matching Python int(text.strip()) exactly"
  - "sidecar.log via plain append WriteStream (Claude's Discretion) — simplest way to keep main.log/sidecar.log distinct"
  - "electron-log main.log path forced via transports.file.resolvePathFn = app.getPath('logs')/main.log; rotation/level left at defaults"

patterns-established:
  - "Pure module + deferred Electron import: keep testable logic top-level, push electron-touching imports into async wrappers via await import()"
  - "OS-level sidecar kill (backend frozen, no /api/shutdown): graceful proc.kill() then taskkill /PID /T /F on tracked pid"

requirements-completed: [NATIVE-02, OBS-01]

coverage:
  - id: D1
    description: "parsePortFile mirrors instance.py read_port_file (trim+int, null on NaN/empty/float)"
    requirement: NATIVE-02
    verification:
      - kind: unit
        ref: "electron/main/sidecar.test.ts#parsePortFile lee texto plano / null en inválido / null en vacía"
        status: pass
    human_judgment: false
  - id: D2
    description: "isDevMode(!isPackaged) dev/prod gate (D-10)"
    requirement: NATIVE-02
    verification:
      - kind: unit
        ref: "electron/main/sidecar.test.ts#isDevMode: dev cuando NO está empaquetado"
        status: pass
    human_judgment: false
  - id: D3
    description: "healthUrl builds 127.0.0.1:<port>/api/health readiness URL (D-03)"
    requirement: NATIVE-02
    verification:
      - kind: unit
        ref: "electron/main/sidecar.test.ts#healthUrl construye el endpoint de readiness"
        status: pass
    human_judgment: false
  - id: D4
    description: "resolveSidecarExe honors NYANKO_SIDECAR_EXE override else resources exe (T-02-INJ absolute path)"
    requirement: NATIVE-02
    verification:
      - kind: unit
        ref: "electron/main/sidecar.test.ts#resolveSidecarExe honra el override"
        status: pass
    human_judgment: false
  - id: D5
    description: "startSidecar lifecycle: stale-port delete → spawn absolute/shell:false/absolute NYANKO_DATA_DIR → port-file wait ≤30s → GET /api/health 200, fail-fast early-exit, one auto re-spawn"
    requirement: NATIVE-02
    verification: []
    human_judgment: true
    rationale: "Spawn/net/re-spawn path is the untested thin wrapper; requires a real packaged nyanko-api.exe run (prod), wired into boot in Plan 02 — cannot be exercised by a Node unit test."
  - id: D6
    description: "killSidecar: reusable graceful→taskkill /T /F on tracked pid, no-op when idle (D-07/D-08, T-02-ORPH)"
    requirement: NATIVE-02
    verification: []
    human_judgment: true
    rationale: "taskkill/process-tree termination needs a live PyInstaller child tree on Windows; verified end-to-end only once index.ts (Plan 02) wires before-quit."
  - id: D7
    description: "logging.ts: setupLogging (main.log under app.getPath('logs')), openLogsFolder (zero-arg fixed dir, D-11/T-02-IPC), pipeSidecarOutput (sidecar.log)"
    requirement: OBS-01
    verification:
      - kind: integration
        ref: "cd apps/desktop && npx electron-vite build (compiles) + tsc --noEmit on logging.ts/sidecar.ts (types resolve incl. electron-log)"
        status: pass
    human_judgment: true
    rationale: "main.log/sidecar.log files only materialize during a real Electron run; the observable 'logs appear + Open logs folder works' is human-verified once wired in Plan 02."

# Metrics
duration: ~15min
completed: 2026-07-10
status: complete
---

# Phase 2 Plan 01: Main core — sidecar lifecycle + logging Summary

**Wave-1 main-process modules: sidecar.ts (spawn + port-file/health readiness gate + reusable taskkill-tree killSidecar) and logging.ts (electron-log main.log + sidecar.log pipe + zero-arg openLogsFolder), with all pure decision logic covered by a node:test self-check under tsx.**

## Performance

- **Duration:** ~15 min
- **Completed:** 2026-07-10
- **Tasks:** 3
- **Files modified:** 4 (3 created, 1 modified) + package-lock.json

## Accomplishments
- `sidecar.ts` — Electron-free pure helpers (parsePortFile, isDevMode, healthUrl, resolveSidecarExe) plus thin wrappers startSidecar (readiness gate: stale-port delete → spawn → port-file wait ≤30s → GET /api/health 200, fail-fast on early exit, one auto re-spawn) and killSidecar (single reusable graceful→`taskkill /PID /T /F`, no-op when idle).
- `logging.ts` — setupLogging pins electron-log main.log under `app.getPath('logs')`; openLogsFolder is zero-arg targeting the fixed logs dir (D-11/T-02-IPC); pipeSidecarOutput streams sidecar stdout/stderr to a distinct sidecar.log.
- `sidecar.test.ts` — 6 passing node:test cases over the pure helpers only (no spawn/net/taskkill); `test:sidecar` npm script added.
- `electron-log@^5.4.4` added to dependencies (only new package; T-02-SC — legitimate, widely-used).

## Task Commits

Each task committed atomically:

1. **Task 1: logging.ts + electron-log dep** - `fa4a5f3` (feat)
2. **Task 2: sidecar.ts spawn/readiness/kill** - `aa2bd21` (feat)
3. **Task 3: sidecar.test.ts + defer logging import** - `81c4cce` (test)

## Files Created/Modified
- `apps/desktop/electron/main/logging.ts` - electron-log transports (main.log), openLogsFolder, pipeSidecarOutput (sidecar.log)
- `apps/desktop/electron/main/sidecar.ts` - sidecar lifecycle: pure helpers + startSidecar/killSidecar wrappers
- `apps/desktop/electron/main/sidecar.test.ts` - node:test self-check for the pure helpers
- `apps/desktop/package.json` - electron-log dependency + test:sidecar script (+ root package-lock.json)

## Decisions Made
- `parsePortFile` uses `Number()` + `Number.isInteger` rather than `parseInt` so `"87.5"` and `"8765abc"` return null, exactly mirroring Python `int(text.strip())`.
- `sidecar.log` written via a plain append `WriteStream` (both discretion-allowed options were equal; stream is the smaller diff and keeps the two log files cleanly separate).
- electron-log main.log path forced via `transports.file.resolvePathFn`; rotation/level/format left at electron-log defaults (Claude's Discretion, CONTEXT).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Deferred `./logging` import in sidecar.ts so pure helpers load without Electron**
- **Found during:** Task 3 (sidecar.test.ts)
- **Issue:** `sidecar.ts` imported `pipeSidecarOutput` from `./logging` at module top level; `logging.ts` imports `electron` + `electron-log/main`, which throw under plain Node. The self-check (`node --import tsx --test`) failed to even load the module (0 suites, 1 fail at line 1) — it could never reach the pure helpers the plan requires to be "unit-tested with no Electron boot".
- **Fix:** Removed the top-level import and moved it into `startSidecar`'s spawn path as `const { pipeSidecarOutput } = await import("./logging")`. Electron only loads during a real prod spawn; the pure helpers now import cleanly under Node.
- **Files modified:** apps/desktop/electron/main/sidecar.ts
- **Verification:** `npm run test:sidecar` → 6/6 pass; `npx electron-vite build` green; targeted `tsc --noEmit` on both modules clean.
- **Committed in:** `81c4cce` (Task 3 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking).
**Impact on plan:** Fix was required to satisfy the plan's own must-have ("pure decision logic covered by a node:test that runs under tsx with no Electron boot"). No scope creep — same public API, one import made lazy.

## Issues Encountered
- The repo's `tsconfig.json` `include` is `["src"]` only, so `npm run check` (tsc --noEmit) does NOT typecheck `electron/main` (pre-existing gap, out of scope). To genuinely verify types (including electron-log resolution and `process.resourcesPath`), ran a targeted `tsc --noEmit --moduleResolution bundler` over `logging.ts`+`sidecar.ts` — clean. Left the tsconfig untouched.
- `electron-vite build` only bundles files reachable from `index.ts`; since this is wave 1 (no index.ts wiring), the build passes but does not itself exercise logging.ts/sidecar.ts. The targeted tsc + tsx self-check are the real compile/behavior gates for this wave.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- `startSidecar`, `killSidecar`, `setupLogging`, `openLogsFolder`, `pipeSidecarOutput` are importable and ready for Plan 02 (wave 2) to wire into `index.ts` (startup gate + before-quit), the splash window, and the `openLogsFolder` IPC handler.
- The spawn/net/kill wrappers (D5/D6) and the log-file materialization (D7) are only observable in a real packaged Electron run — flagged human_judgment in coverage; Plan 02 boot wiring is where they get end-to-end verified.

---
*Phase: 02-main-core-sidecar-lifecycle-logging*
*Completed: 2026-07-10*
