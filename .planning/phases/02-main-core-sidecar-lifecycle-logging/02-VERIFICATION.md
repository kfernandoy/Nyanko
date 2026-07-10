---
phase: 02-main-core-sidecar-lifecycle-logging
status: passed
verified: 2026-07-10
method: live human UAT + automated gates
requirements: [NATIVE-02, OBS-01]
---

# Phase 2 Verification — Main core: sidecar lifecycle + logging

**Result: PASSED** (goal-backward, all 5 ROADMAP success criteria confirmed).

**Phase goal:** El main process gestiona el ciclo de vida del sidecar Python en producción y deja rastro diagnóstico desde la primera versión Electron.

## Success criteria (verified live, 2026-07-10)

| # | Criterion | Evidence | Status |
|---|-----------|----------|--------|
| 1 | Prod: main spawns `nyanko-api.exe` with `NYANKO_DATA_DIR`, waits port file (≤30s), library loads cold without "Cargando biblioteca ~1min" | Live `electron-vite preview` + `NYANKO_SIDECAR_EXE`: splash → `/api/health` gate → biblioteca cargada. User: "ahora funciona". | ✅ |
| 2 | Sidecar killed on app-quit and before update; no orphans | Graceful close → `before-quit → killSidecar` (graceful → `taskkill /T /F`); zero `nyanko-api.exe` after quit. `killSidecar` exported for the Phase-5 updater. | ✅ |
| 3 | Dev omits the sidecar; app uses the hand-started backend | `npm run dev` (no override) → `isDevMode(app.isPackaged) && !NYANKO_SIDECAR_EXE` → no `nyanko-api.exe` spawned; library loads via manual backend. | ✅ |
| 4 | `main.log` + `sidecar.log` (piped stdout/stderr) under `app.getPath('logs')` | Both files present with content: `main.log` (electron-log), `sidecar.log` (piped uvicorn). | ✅ |
| 5 | "Open logs folder" action reachable from the UI | Ajustes → "acerca" → "Abrir carpeta de registros" opens the real logs dir. | ✅ |

## Requirements coverage

- **NATIVE-02** (sidecar lifecycle: spawn + `NYANKO_DATA_DIR` + port-file wait + kill on quit/update; dev omits) — covered by 02-01 (`sidecar.ts`) + 02-02 (`index.ts` gate + `before-quit`). ✅
- **OBS-01** (main + sidecar logs via electron-log + UI action) — covered by 02-01 (`logging.ts`) + 02-02 (IPC + button). ✅

## Automated gates

- `npm run check` (tsc --noEmit) — clean.
- `npx electron-vite build` — clean (main 9.74 kB: index/splash/ipc/sidecar/logging/compat-paths).
- `npm run test:sidecar` 6/6, `npm run test:datadir` 3/3.

## Gap fixes applied during verification

1. Renderer sidecar-port discovery in Electron via whitelisted `nyanko.readAppDataFile` (`12a9310`) — minimal `native.ts` slice; full frontier remains Phase 3.
2. `NYANKO_SIDECAR_EXE` forces the sidecar under `electron-vite preview` (`app.isPackaged` is false there) so the prod gate is verifiable pre-packaging (`0dd4d99`).

## Scope notes / deferrals (expected, not defects)

- Frameless window has no titlebar/close controls — Phase 4 (NATIVE-04).
- Full packaged-build verification of the prod gate — Phase 5.
- Real updater integration consuming `killSidecar` before `quitAndInstall` — Phase 5.
- Backend frozen: no `/api/shutdown` added; graceful kill is OS-level (D-09).
