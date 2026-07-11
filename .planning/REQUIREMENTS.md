# Requirements — Nyanko 0.2 (Tauri → Electron)

Milestone: engine-swap del shell de escritorio. Diseño:
`docs/specs/2026-07-09-tauri-to-electron-migration-design.md`.

Principio rector: **paridad, no features**. Cada requisito es "Electron hace lo
que Tauri hacía", verificable contra el comportamiento 0.1.15.

## v1 Requirements (0.2.0)

### Shell (proyecto Electron)

- [ ] **SHELL-01**: `apps/desktop` corre en desarrollo con `electron-vite dev`,
      levantando el renderer React actual sin cambios de UI.

- [x] **SHELL-02**: El repo no depende de Rust/Tauri para buildear: se eliminan
      las deps `@tauri-apps/*` y no queda `src-tauri`.

### Frontera nativa (native.ts + preload)

- [x] **NATIVE-01**: Un único `src/native.ts` respalda toda operación que antes
      usaba `@tauri-apps/*`, vía `window.nyanko` expuesto por el preload con
      `contextBridge` (contextIsolation activo).

- [ ] **NATIVE-02**: El sidecar Python (`nyanko-api.exe`) se lanza en producción
      con `NYANKO_DATA_DIR`, espera el `port` file (timeout 30s) y se mata al
      salir y antes de instalar un update. En dev se omite (backend manual).

- [x] **NATIVE-03**: La bandeja replica el menú actual (Mostrar / Ocultar /
      Pausar-Reanudar detección / Salir), doble-click muestra la ventana, y el
      toggle de detección hace POST a `/api/detection/{pause,resume}`.

- [x] **NATIVE-04**: Las preferencias de ventana (close-to-tray, minimize-to-tray,
      start-minimized) persisten en `window_prefs.json` y gobiernan el
      comportamiento; la titlebar frameless custom (minimizar/cerrar) funciona.

- [ ] **NATIVE-05**: Discord Rich Presence set/clear activity funciona mediante
      una librería RPC de Node, con el mismo Client ID y no-op silencioso si
      Discord no está.

- [ ] **NATIVE-06**: Single-instance (traer al frente la instancia viva),
      autostart con `--minimized`, notificaciones, abrir externos (opener) y
      selector de carpetas (dialog) funcionan por equivalentes de Electron.

### Datos (compatibilidad)

- [ ] **DATA-01**: `userData` queda fijado a `%APPDATA%\app.nyanko.desktop`; el
      arranque hace assert y crashea si resuelve a otra ruta. La biblioteca de
      producción existente carga sin migración.

### Empaquetado y updates

- [ ] **PKG-01**: `electron-builder` produce un instalador Windows NSIS
      (español/inglés, EULA) que incluye el sidecar (`nyanko-api.exe` +
      `_internal`) y los bundles de extensión (`chromium`/`firefox`) como
      recursos.

- [ ] **PKG-02**: `electron-updater` detecta, descarga e instala updates desde
      GitHub Releases (verificando SHA512), deteniendo el sidecar antes de
      instalar.

### Observabilidad

- [ ] **OBS-01**: Los logs de main y del sidecar se escriben con `electron-log`
      en el directorio de logs de la app, y hay una acción "abrir carpeta de
      logs" accesible desde la UI.

## v2 / Deferred (0.3+)

- Firma pública externa + página "Verify" (minisign/cosign).
- Rediseño de la pantalla de extensión (descargas por navegador, guía, estado).
- Adapters comunitarios con API versionada.
- Navegador embebido / webviews para sitios externos.
- Code-signing del instalador Windows.

## Out of Scope

- Migrar el backend Python a Node — el sidecar existe y funciona; solo cambia el
  shell.

- Cambios de UI del renderer — 0.2 preserva la interfaz actual; solo se swapea la
  capa nativa que consume.

- Soporte multiplataforma nuevo (macOS/Linux) — Windows sigue siendo el target;
  no se amplía en 0.2.

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| SHELL-01 | Phase 1 | Pending |
| DATA-01 | Phase 1 | Pending |
| NATIVE-02 | Phase 2 | Pending |
| OBS-01 | Phase 2 | Pending |
| NATIVE-01 | Phase 3 | Complete |
| SHELL-02 | Phase 3 | Complete |
| NATIVE-03 | Phase 4 | Complete |
| NATIVE-04 | Phase 4 | Complete |
| NATIVE-05 | Phase 4 | Pending |
| NATIVE-06 | Phase 4 | Pending |
| PKG-01 | Phase 5 | Pending |
| PKG-02 | Phase 5 | Pending |
