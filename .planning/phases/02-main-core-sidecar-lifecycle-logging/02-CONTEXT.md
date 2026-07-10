# Phase 2: Main core — sidecar lifecycle + logging - Context

**Gathered:** 2026-07-10
**Status:** Ready for planning

<domain>
## Phase Boundary

El proceso main de Electron gestiona el ciclo de vida completo del sidecar
Python (`nyanko-api.exe`) en producción — spawn con `NYANKO_DATA_DIR`, espera de
readiness, kill limpio al salir y antes de un update — y deja rastro diagnóstico
(`electron-log`: `main.log` + `sidecar.log`) desde la primera versión Electron,
con una acción "abrir carpeta de logs" accesible desde la UI.

**Scope anchor (0.2 = engine-swap puro):** No se toca el backend Python (código
congelado, sin nuevos endpoints). No hay tray todavía (Fase 4) ni `native.ts`
completo (Fase 3). Esta fase implementa `sidecar.ts` y `logging.ts` en el main y
el cableado IPC mínimo necesario para la acción de logs.

Requisitos: **NATIVE-02** (lifecycle del sidecar), **OBS-01** (logging + acción
abrir-logs).

</domain>

<decisions>
## Implementation Decisions

### Gate de arranque en frío (mata el "Cargando biblioteca ~1min")
- **D-01:** Secuencia de arranque orquestada por el main, con **splash window
  inmediata** para que nunca se vea la app congelada:
  1. Abrir una splash window mínima **de inmediato** (BrowserWindow pequeña con
     HTML local, sin backend).
  2. Borrar el `port` file viejo **antes** de spawnear (evita leer un puerto
     obsoleto — el wait solo acepta un port file escrito tras el spawn).
  3. Spawnear `nyanko-api.exe` con `NYANKO_DATA_DIR = userData`.
  4. Esperar a que el sidecar escriba el nuevo `port` file (timeout ≤30s).
  5. Probar readiness real: `GET http://127.0.0.1:<port>/api/health` → 200.
  6. Cuando OK: crear/cargar la BrowserWindow principal, esperar `ready-to-show`,
     cerrar la splash y mostrar la ventana principal.
  7. Si falla: la splash pasa a estado de error con botones **Reintentar /
     Abrir logs / Salir**.
- **D-02:** La readiness es del **main**, no del renderer: el renderer nunca
  arranca contra un backend frío. Esto reemplaza el readiness gate que faltaba en
  el frontend (causa raíz del viejo "Cargando biblioteca ~1min").
- **D-03:** El endpoint de readiness es `GET /api/health` (existe hoy,
  `main.py:1392`). NO existe `/api/library/status` ni `/api/bootstrap` — no se
  agregan (backend congelado). Warm-up adicional de la biblioteca (`GET
  /api/library`) queda a discreción, no es requisito de readiness.

### Fallo del sidecar (timeout / crash / puerto ocupado)
- **D-04:** Fail-fast: si el `.exe` sale rápido (exit temprano), **no** esperar
  los 30s — capturar exit code + stderr/log y cortar.
- **D-05:** Si no aparece el `port` file en 20–30s: matar el child propio,
  limpiar (borrar `port` file), esperar 500–1000 ms.
- **D-06:** **Un** re-spawn automático tras el cleanup. Si el segundo intento
  falla → dialog de diagnóstico (integrado con el estado de error de la splash:
  Reintentar / Abrir logs / Salir), con opción de **copiar logs / reportar
  error**.

### Kill y prevención de huérfanos (criterio de éxito #2)
- **D-07:** Estrategia **graceful con timeout → force-kill del árbol**: intento
  de cierre ordenado, esperar ~3–5s, luego `taskkill /PID <pid> /T /F` (mata el
  árbol completo — PyInstaller onedir puede lanzar un proceso hijo en Windows).
- **D-08:** Registrar el kill tanto en `before-quit` (salida de la app) como en
  el flujo del updater **antes** de `quitAndInstall`. Sin procesos huérfanos en
  ningún camino.
- **D-09:** Restricción de scope: como el backend está congelado y NO tiene ruta
  `/api/shutdown`, el "graceful" es **a nivel de SO** (terminar ordenadamente y
  luego forzar). No se agrega un endpoint de shutdown al backend en 0.2 — el
  mecanismo graceful exacto en Windows (CTRL_BREAK vs `taskkill` sin `/F` vs
  cierre de stdin) es decisión de research/planner.

### Dev vs prod + acceso a "abrir carpeta de logs"
- **D-10:** Señal dev/prod: **`app.isPackaged`**. En dev (`!app.isPackaged`) se
  **omite** el sidecar por completo; la app usa el backend Python arrancado a
  mano (como hoy). En prod se spawnea.
- **D-11:** OBS-01 en 0.2: **IPC mínimo ahora + botón en un `*SettingsView.tsx`
  existente**. Cablear `openLogsFolder()` (`shell.openPath(app.getPath('logs'))`)
  vía preload/IPC en esta fase y colgar el botón en una pantalla de ajustes ya
  existente. Cumple "accesible desde la UI" sin esperar al tray (Fase 4).
- **D-12:** Opcionalmente, además, un item de menú nativo de Electron tipo
  "Help/Diagnostics → Open logs folder" que llame al mismo `openLogsFolder()`.

### Claude's Discretion
- Mecanismo del splash (BrowserWindow vacía + HTML inline vs archivo).
- Formato/rotación/nivel de `electron-log` (defaults salvo necesidad).
- Mecanismo graceful de terminación en Windows (D-09) — a definir en research.
- Cómo se pipea stdout/stderr del sidecar a `sidecar.log` (stream vs electron-log
  transport).
- Qué `*SettingsView.tsx` concreto hospeda el botón de logs.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Diseño de la migración (fuente de verdad de responsabilidades del main)
- `docs/specs/2026-07-09-tauri-to-electron-migration-design.md` §"Main process
  (electron/main/)" — responsabilidades de `sidecar.ts`, `logging.ts`,
  `updater.ts`; §"Data dir" (compatibilidad `%APPDATA%\app.nyanko.desktop`).

### Backend (congelado — referencia de contrato, no se modifica)
- `apps/backend/nyanko_api/main.py:1392` — `GET /api/health` (endpoint de
  readiness).
- `apps/backend/nyanko_api/main.py:1343` — `write_port_file(...)` en el startup
  (la señal que el main espera).
- `apps/backend/nyanko_api/config.py` — propiedades `port_file` /
  `instance_token_file` ancladas a `NYANKO_DATA_DIR`.
- `apps/backend/nyanko_api/instance.py` — `read_port_file` / `write_port_file`
  (formato del `port` file: texto plano con el número de puerto).

### Fase 1 (base sobre la que se construye)
- `apps/desktop/electron/main/index.ts` — bootstrap actual (data-dir lock +
  ventana frameless); aquí se inserta el spawn del sidecar y el gate de arranque.
- `apps/desktop/electron/main/compat-paths.ts` — `userDataDir(...)` (valor de
  `NYANKO_DATA_DIR` para el sidecar).
- `.planning/PROJECT.md` — constraints de scope 0.2 y data-dir.
- `.planning/REQUIREMENTS.md` — NATIVE-02, OBS-01 (texto completo de los
  requisitos).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `compat-paths.userDataDir()` (Fase 1): ya calcula el userData legacy — es el
  valor exacto de `NYANKO_DATA_DIR` a pasar al sidecar.
- `apps/desktop/electron/main/index.ts`: bootstrap secuencial ya establecido
  (setPath → assert → whenReady → createWindow); el gate de arranque se inserta
  entre `whenReady` y la creación de la ventana principal.
- `*SettingsView.tsx` (varios en `apps/desktop/src/`): ya hay superficie de
  ajustes en el renderer React donde colgar el botón "abrir carpeta de logs".

### Established Patterns
- Preload CommonJS `.cjs` con `contextBridge` (sandbox:true) — el IPC de
  `openLogsFolder` debe seguir este patrón (nada de Node crudo al renderer).
- `webPreferences` seguras fijas (contextIsolation/sandbox/webSecurity) — la
  splash window debe respetar los mismos principios de seguridad.
- Self-checks con `node:test` bajo `tsx` sin framework (Fase 1) — patrón para
  testear lógica pura (p.ej. parsing del port file, decisión dev/prod).

### Integration Points
- El sidecar escribe `port` (e `instance_token`, `window_prefs.json`) en el
  userData; el main lo lee para el gate de readiness.
- `app.getPath('logs')` — destino de `main.log`/`sidecar.log` y target de
  `openLogsFolder()`.
- Updater (Fase 5): debe llamar al kill del sidecar antes de `quitAndInstall`;
  esta fase deja el kill expuesto de forma reutilizable.

</code_context>

<specifics>
## Specific Ideas

- Diálogo de error de la splash con acción de **copiar logs / reportar error**
  (más allá de solo "abrir logs").
- Item de menú nativo "Help/Diagnostics → Open logs folder" como acceso
  secundario a los logs.

</specifics>

<deferred>
## Deferred Ideas

- Tray con menú (Mostrar/Ocultar/Pausar detección/Salir) y su acceso a logs —
  **Fase 4 (NATIVE-03)**.
- `native.ts` como frontera nativa única que reemplaza `@tauri-apps/*` —
  **Fase 3 (NATIVE-01/SHELL-02)**.
- Integración real del updater (electron-updater) que consume el kill del
  sidecar — **Fase 5 (empaquetado/update)**.
- Pantalla de diagnóstico elaborada — fuera de 0.2 (solo botón + dialog).
- Endpoint `/api/shutdown` en el backend para graceful HTTP — fuera de scope
  (backend congelado en 0.2).

None adicional — la discusión se mantuvo dentro del scope de la fase.

</deferred>

---

*Phase: 2-main-core-sidecar-lifecycle-logging*
*Context gathered: 2026-07-10*
