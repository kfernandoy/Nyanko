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

- [ ] **Phase 1: Electron shell scaffold + data-dir lock** - electron-vite arranca el renderer actual con `userData` fijado a `app.nyanko.desktop`
- [ ] **Phase 2: Main core — sidecar lifecycle + logging** - el main lanza/mata el sidecar Python con gate de readiness y escribe logs con electron-log
- [ ] **Phase 3: Native boundary + Tauri removal** - `src/native.ts` + preload contextBridge reemplazan todos los `@tauri-apps/*` y se borran las deps/`src-tauri`
- [ ] **Phase 4: Native feature parity** - tray, window prefs/titlebar, Discord RPC, single-instance, autostart, notif, dialog y opener replican Tauri
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
**Plans**: TBD

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
**Plans**: TBD

### Phase 3: Native boundary + Tauri removal
**Goal**: Toda operación nativa del renderer pasa por una única frontera (`src/native.ts` → `window.nyanko` → IPC), y el repo deja de depender de Rust/Tauri para buildear.
**Depends on**: Phase 2
**Requirements**: NATIVE-01, SHELL-02
**Success Criteria** (what must be TRUE):
  1. Un único `src/native.ts` respalda toda operación que antes usaba `@tauri-apps/*`, vía `window.nyanko` expuesto por el preload con `contextBridge`.
  2. No queda ningún import de `@tauri-apps/*` en el renderer y `api.ts` lee el data dir vía `native.readAppDataFile`.
  3. Un self-check assert-based del boundary falla si alguna operación nativa queda sin mapear.
  4. El repo buildea sin Rust: se eliminan las deps `@tauri-apps/*` de `package.json` y no queda `src-tauri` en el árbol.
**Plans**: TBD

### Phase 4: Native feature parity
**Goal**: Las features nativas que Tauri proveía funcionan con equivalentes de Electron, replicando el comportamiento de 0.1.15.
**Depends on**: Phase 3
**Requirements**: NATIVE-03, NATIVE-04, NATIVE-05, NATIVE-06
**Success Criteria** (what must be TRUE):
  1. La bandeja muestra el menú (Mostrar / Ocultar / Pausar-Reanudar detección / Salir), doble-click muestra la ventana, y el toggle de detección hace POST a `/api/detection/{pause,resume}`.
  2. Las preferencias de ventana (close-to-tray, minimize-to-tray, start-minimized) persisten en `window_prefs.json` y gobiernan el comportamiento; la titlebar frameless (minimizar/cerrar) responde.
  3. Discord Rich Presence set/clear activity funciona con el mismo Client ID y es no-op silencioso si Discord no está corriendo.
  4. Single-instance trae al frente la instancia viva; autostart arranca con `--minimized`; notificaciones, abrir externos (opener) y selector de carpetas (dialog) funcionan.
**Plans**: TBD

### Phase 5: Packaging + auto-update
**Goal**: La app se distribuye como instalador Windows firmable-a-futuro y se actualiza sola desde GitHub Releases, cerrando la paridad con el flujo de release Tauri.
**Depends on**: Phase 4
**Requirements**: PKG-01, PKG-02
**Success Criteria** (what must be TRUE):
  1. `electron-builder` produce un instalador NSIS (español/inglés, EULA) que corre e instala la app.
  2. El instalado incluye el sidecar (`nyanko-api.exe` + `_internal`) y los bundles de extensión (`chromium`/`firefox`) como `extraResources`, y la app arranca el sidecar en frío y carga la biblioteca.
  3. `electron-updater` detecta una versión nueva en GitHub Releases, la descarga verificando SHA512 y la instala tras detener el sidecar.
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Electron shell scaffold + data-dir lock | 0/TBD | Not started | - |
| 2. Main core — sidecar lifecycle + logging | 0/TBD | Not started | - |
| 3. Native boundary + Tauri removal | 0/TBD | Not started | - |
| 4. Native feature parity | 0/TBD | Not started | - |
| 5. Packaging + auto-update | 0/TBD | Not started | - |
