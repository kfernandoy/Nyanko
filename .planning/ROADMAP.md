# Roadmap: Nyanko 0.2 (Tauri → Electron)

## Overview

Engine-swap del shell de escritorio: se reemplaza `apps/desktop/src-tauri` (Rust)
por un proyecto electron-vite (main + preload + renderer), sin tocar el renderer
React, el backend Python sidecar ni la extensión. El roadmap avanza por capas
técnicas que ensamblan en una app Electron funcional: primero el cascarón que
arranca contra el data dir correcto, luego el núcleo del main (sidecar +
logging), después la frontera nativa que borra `@tauri-apps/*`, luego la paridad
de features nativas, y por último el empaquetado NSIS + auto-update. Regla dura:
paridad con 0.1.15, cero features nuevas.

## Phases

**Phase Numbering:**

- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Electron shell scaffold + data-dir lock** - electron-vite arranca el renderer actual con `userData` fijado a `app.nyanko.desktop` (completed 2026-07-10)
- [x] **Phase 2: Main core — sidecar lifecycle + logging** - el main lanza/mata el sidecar Python con gate de readiness y escribe logs con electron-log (2 plans) (completed 2026-07-10)
- [x] **Phase 3: Native boundary + Tauri removal** - `src/native.ts` + preload contextBridge reemplazan todos los `@tauri-apps/*` y se borran las deps/`src-tauri` (completed 2026-07-11)
- [x] **Phase 4: Native feature parity** - tray, window prefs/titlebar, Discord RPC, single-instance, autostart, notif, dialog y opener replican Tauri (completed 2026-07-11)
- [ ] **Phase 5: Packaging + auto-update** - electron-builder NSIS con sidecar+extensión como recursos y electron-updater desde GitHub Releases

## Phase Details

### Phase 1: Electron shell scaffold + data-dir lock

**Goal**: `apps/desktop` corre como app electron-vite en desarrollo, cargando el renderer React actual sin cambios de UI, contra un data dir compatible con producción.
**Depends on**: Nothing (first phase)
**Requirements**: SHELL-01, DATA-01
**Success Criteria** (what must be TRUE):

  1. `electron-vite dev` levanta la app y la biblioteca carga contra un backend Python arrancado a mano, sin cambios visibles de UI.
  2. La ventana frameless abre con `contextIsolation:true`, `nodeIntegration:false`, `sandbox:true`, `webSecurity:true`.
  3. `app.getPath('userData')` resuelve a `%APPDATA%\app.nyanko.desktop` y la biblioteca de producción existente carga sin migración.
  4. El arranque crashea de inmediato si `userData` cae en otra ruta (p.ej. `%APPDATA%\Nyanko`), verificable con un self-check.

**Plans**: 2/2 plans complete

- [x] 01-01-PLAN.md — electron-vite scaffold + secure frameless window + data-dir lock (SHELL-01, DATA-01)
- [x] 01-02-PLAN.md — data-dir crash-guard self-check + interactive shell verification (DATA-01)

### Phase 2: Main core — sidecar lifecycle + logging

**Goal**: El main process gestiona el ciclo de vida del sidecar Python en producción y deja rastro diagnóstico desde la primera versión Electron.
**Depends on**: Phase 1
**Requirements**: NATIVE-02, OBS-01
**Success Criteria** (what must be TRUE):

  1. En un run de producción el main spawnea `nyanko-api.exe` con `NYANKO_DATA_DIR`, espera el `port` file (timeout 30s) y la biblioteca carga en frío sin el "Cargando biblioteca ~1min".
  2. El sidecar se mata al salir de la app y antes de instalar un update; no quedan procesos huérfanos.
  3. En dev el sidecar se omite y la app usa el backend Python arrancado a mano.
  4. `main.log` y `sidecar.log` (stdout/stderr pipeado) se escriben en el directorio de logs de la app.
  5. Existe una acción "abrir carpeta de logs" accesible desde la UI que abre el directorio real.

**Plans**: 2/2 plans complete

- [x] 02-01-PLAN.md — sidecar lifecycle + logging foundation: sidecar.ts (spawn/readiness gate/kill) + logging.ts (electron-log main.log/sidecar.log + openLogsFolder) + pure-helper self-check (NATIVE-02, OBS-01)
- [x] 02-02-PLAN.md — startup gate orchestration + logs action UI: splash.ts, index.ts gate (dev short-circuit + before-quit kill), ipc.ts + preload bridge, "open logs folder" button (NATIVE-02, OBS-01)

### Phase 3: Native boundary + Tauri removal

**Goal**: Toda operación nativa del renderer pasa por una única frontera (`src/native.ts` → `window.nyanko` → IPC), y el repo deja de depender de Rust/Tauri para buildear.
**Depends on**: Phase 2
**Requirements**: NATIVE-01, SHELL-02
**Success Criteria** (what must be TRUE):

  1. Un único `src/native.ts` respalda toda operación que antes usaba `@tauri-apps/*`, vía `window.nyanko` expuesto por el preload con `contextBridge`.
  2. No queda ningún import de `@tauri-apps/*` en el renderer y `api.ts` lee el data dir vía `native.readAppDataFile`.
  3. Un self-check assert-based del boundary falla si alguna operación nativa queda sin mapear.
  4. El repo buildea sin Rust: se eliminan las deps `@tauri-apps/*` de `package.json` y no queda `src-tauri` en el árbol.

**Plans**: 1/2 plans executed
**Wave 1**

- [x] 03-01-PLAN.md — build the native.ts boundary + preload/IPC surface + assert-based self-check (NATIVE-01)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 03-02-PLAN.md — purge @tauri-apps: rewire all consumers to native.ts, drop deps + tauri script, green Rust-free build (SHELL-02, NATIVE-01)

### Phase 4: Native feature parity

**Goal**: Las features nativas que Tauri proveía funcionan con equivalentes de Electron, replicando el comportamiento de 0.1.15.
**Depends on**: Phase 3
**Requirements**: NATIVE-03, NATIVE-04, NATIVE-05, NATIVE-06
**Success Criteria** (what must be TRUE):

  1. La bandeja muestra el menú (Mostrar / Ocultar / Pausar-Reanudar detección / Salir), doble-click muestra la ventana, y el toggle de detección hace POST a `/api/detection/{pause,resume}`.
  2. Las preferencias de ventana (close-to-tray, minimize-to-tray, start-minimized) persisten en `window_prefs.json` y gobiernan el comportamiento; la titlebar frameless (minimizar/cerrar) responde.
  3. Discord Rich Presence set/clear activity funciona con el mismo Client ID y es no-op silencioso si Discord no está corriendo.
  4. Single-instance trae al frente la instancia viva; autostart arranca con `--minimized`; notificaciones, abrir externos (opener) y selector de carpetas (dialog) funcionan.

**Plans**: 3/3 plans complete
**Wave 1**

- [x] 04-01-PLAN.md — Frameless titlebar + window controls IPC + brand app icon (NATIVE-04)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 04-02-PLAN.md — System tray + window prefs persist + close/minimize-to-tray + start-minimized (NATIVE-03, NATIVE-04)

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 04-03-PLAN.md — Discord RPC + single-instance + autostart + notifications/opener/dialog verify (NATIVE-05, NATIVE-06)

### Phase 5: Packaging + auto-update

**Goal**: La app se distribuye como instalador Windows firmable-a-futuro y se actualiza sola desde GitHub Releases, cerrando la paridad con el flujo de release Tauri.
**Depends on**: Phase 4
**Requirements**: PKG-01, PKG-02
**Success Criteria** (what must be TRUE):

  1. `electron-builder` produce un instalador NSIS (español/inglés, EULA) que corre e instala la app.
  2. El instalado incluye el sidecar (`nyanko-api.exe` + `_internal`) y los bundles de extensión (`chromium`/`firefox`) como `extraResources`, y la app arranca el sidecar en frío y carga la biblioteca.
  3. `electron-updater` detecta una versión nueva en GitHub Releases, la descarga verificando SHA512 y la instala tras detener el sidecar.

**Plans**: 6 plans

- [ ] 05-01-PLAN.md — electron-builder.yml + EULA + hook NSIS + cadena de build sin Tauri (PKG-01) · wave 1
- [ ] 05-03-PLAN.md — gate empírico D-02: migración desde la instalación Tauri sin perder la biblioteca (PKG-01, DATA-01) · wave 2
- [ ] 05-05-PLAN.md — icono empaquetado: `iconPath()` por `process.resourcesPath` (PKG-01) · wave 2
- [ ] 05-02-PLAN.md — electron-updater en el main + flujo de Acerca de restaurado (PKG-02) · wave 3
- [ ] 05-04-PLAN.md — publicar v0.2.0 + puente minisign/latest.json para los usuarios 0.1.15 (PKG-01, PKG-02) · wave 4
- [ ] 05-06-PLAN.md — publicar v0.2.1 y probar el auto-update real 0.2.0 → 0.2.1 (PKG-02) · wave 5

*Las waves 2-5 son secuenciales a propósito: los checkpoints de 05-02/03/04/06 instalan y
desinstalan Nyanko en la MISMA máquina, y cada uno necesita un estado de partida concreto
(ver `<coreografia_del_estado_de_la_maquina>` en 05-03-PLAN.md). 05-05 es código puro y es el único
que puede correr en paralelo (wave 2, no toca la máquina).*

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Electron shell scaffold + data-dir lock | 2/2 | Complete   | 2026-07-10 |
| 2. Main core — sidecar lifecycle + logging | 2/2 | Complete   | 2026-07-10 |
| 3. Native boundary + Tauri removal | 2/2 | Complete    | 2026-07-11 |
| 4. Native feature parity | 3/3 | Complete    | 2026-07-11 |
| 5. Packaging + auto-update | 0/TBD | Not started | - |
