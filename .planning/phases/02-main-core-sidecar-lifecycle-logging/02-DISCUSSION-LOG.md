# Phase 2: Main core — sidecar lifecycle + logging - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-10
**Phase:** 2-main-core-sidecar-lifecycle-logging
**Areas discussed:** Gate de arranque en frío, Fallo del sidecar, Kill y huérfanos, Dev/prod + acceso a logs

---

## Gate de arranque en frío

| Option | Description | Selected |
|--------|-------------|----------|
| Main espera port file, LUEGO muestra ventana | Main await del port file antes de crear/mostrar ventana; splash nativo mínimo | ✓ (refinado) |
| Ventana carga ya, renderer espera señal IPC 'sidecar-ready' | createWindow inmediato; renderer espera evento IPC antes de llamar la API | |
| Ventana carga ya + retry/polling en el cliente API | La ventana carga y el cliente reintenta hasta que el backend responde | |

**User's choice:** Variante refinada de la opción 1 — splash window inmediata → borrar port viejo → spawn → esperar nuevo port → `GET /api/health` (+ opcional `/api/library` warm-up) → crear/cargar ventana principal, `ready-to-show`, cerrar splash, mostrar. Si falla: splash pasa a error con botones Reintentar / Abrir logs / Salir.
**Notes:** El readiness es del main, no del renderer — el renderer nunca arranca contra un backend frío (causa raíz del viejo "Cargando biblioteca ~1min"). Endpoint concreto confirmado en scout: `GET /api/health` existe; `/api/library/status` y `/api/bootstrap` NO existen.

---

## Fallo del sidecar (timeout / crash)

| Option | Description | Selected |
|--------|-------------|----------|
| Dialog de error con 'Abrir logs' + salir | Dialog nativo + botón abrir logs + app.quit() | |
| Reintentar una vez (re-spawn), luego dialog + salir | Un reintento automático antes de rendirse | ✓ (refinado) |
| Dialog + seguir con ventana degradada | Muestra la ventana igual; renderer maneja backend caído | |

**User's choice:** Variante refinada de la opción 2 — fail-fast si el exe sale rápido (capturar exit code/stderr, no esperar 30s); si no aparece port file en 20–30s → kill del child + cleanup (borrar port, esperar 500–1000 ms) → un re-spawn → si falla, dialog de diagnóstico con copiar logs / reportar error.
**Notes:** Integrado con el estado de error de la splash (Reintentar / Abrir logs / Salir).

---

## Kill y huérfanos

| Option | Description | Selected |
|--------|-------------|----------|
| Graceful con timeout → force-kill del árbol | Cierre limpio, esperar ~3-5s, luego taskkill /PID /T /F; en before-quit y antes de quitAndInstall | ✓ |
| Force-kill directo del árbol (taskkill /T /F) | Sin intento graceful; arriesga corrupción de DB en escritura | |
| child.kill() estándar de Node | Riesgo de dejar el hijo huérfano en Windows | |

**User's choice:** Graceful con timeout → force-kill del árbol.
**Notes:** Scout confirmó que el backend NO tiene ruta `/api/shutdown` y 0.2 lo mantiene congelado → el "graceful" es a nivel de SO; el mecanismo exacto en Windows queda para research.

---

## Dev/prod + acceso a logs

| Option | Description | Selected |
|--------|-------------|----------|
| IPC mínimo ahora + botón en un SettingsView existente | openLogsFolder vía preload/IPC + botón en *SettingsView.tsx | ✓ (+ menú nativo) |
| Solo item en el menú nativo de Electron por ahora | Item de menú que llama openLogsFolder; botón UI en Fase 4 | |
| Adelantar el botón hasta Fase 3/4 | Solo openLogsFolder() en el main; exposición UI diferida | |

**User's choice:** Opción 1 + opcionalmente un menú nativo "Help/Diagnostics → Open logs folder".
**Notes:** Dev/prod detectado con `app.isPackaged` (default de Claude, sin objeción del usuario). Scout confirmó que ya existen varios `*SettingsView.tsx` donde colgar el botón.

## Claude's Discretion

- Mecanismo del splash (BrowserWindow + HTML inline vs archivo).
- Formato/rotación/nivel de electron-log.
- Mecanismo graceful de terminación en Windows.
- Cómo se pipea stdout/stderr del sidecar a sidecar.log.
- Qué SettingsView concreto hospeda el botón.

## Deferred Ideas

- Tray + su acceso a logs → Fase 4 (NATIVE-03).
- `native.ts` frontera nativa → Fase 3 (NATIVE-01/SHELL-02).
- Integración real del updater que consume el kill → Fase 5.
- Pantalla de diagnóstico elaborada → fuera de 0.2.
- Endpoint `/api/shutdown` en backend → fuera de scope (backend congelado).
