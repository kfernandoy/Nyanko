# Migración Tauri → Electron — Diseño

Fecha: 2026-07-09
Estado: aprobado (pendiente de plan de implementación)

## Contexto y motivación

`apps/desktop` es hoy una app Tauri 2 (frontend React/Vite + shell Rust en
`src-tauri`) que lanza el backend Python (`apps/backend`, empaquetado con
PyInstaller onedir) como sidecar. Versión actual: 0.1.15.

Se migra a **Electron** por madurez de ecosistema: plugins, adapters, comunidad
de apps de escritorio, y espacio para expandir el companion a futuro. No es un
problema puntual de Tauri; es una decisión long-term de plataforma.

`src-tauri/` ya fue borrado del árbol de trabajo (junto con los 18 GB de
`target`). Su contenido está íntegro en el backup
`nyanko-pre-electron-backup-20260709.tar.gz` (config, código Rust, iconos) y en
git, y se usa solo como **referencia** para replicar comportamiento.

Distribución: prácticamente un solo usuario (el autor). Por lo tanto **no** se
necesita puente de auto-update Tauri→Electron ni compatibilidad hacia atrás con
usuarios externos.

## Regla de alcance por versión (dura)

La 0.2 es un **engine swap**, no una plataforma nueva. Regla no negociable:

- **0.2.0** = misma app, mismo backend, mismo tracking, mismo data dir, mismo
  flujo de extensión. Solo cambia el shell (Tauri → Electron). Objetivo:
  Electron replica Tauri al ~95%. Aburrida y estable.
- **0.2.x** = fixes de migración.
- **0.3.0+** = features nuevas: adapters comunitarios (API versionada), rediseño
  de la pantalla de extensión, firma pública / página "Verify", navegador
  embebido, etc.

Nada de la columna 0.3 se implementa en 0.2, aunque el diseño lo tenga en el
horizonte.

## Alcance

**No cambia:**
- `apps/backend` (Python/FastAPI). Se sigue empaquetando igual: PyInstaller
  onedir → `nyanko-api.exe` + carpeta `_internal`.
- `apps/extension`.
- `apps/desktop/src` (renderer React), salvo la fina capa que hoy importa
  `@tauri-apps/*`.

**Cambia / se crea:**
- Se elimina la dependencia de `src-tauri` (Rust) y de todos los paquetes
  `@tauri-apps/*`.
- `apps/desktop` pasa a ser un proyecto **electron-vite** (main + preload +
  renderer).
- Empaquetado con **electron-builder** (target NSIS) y auto-update con
  **electron-updater** (provider GitHub, reutiliza el flujo de releases-en-
  GitHub existente).

## Enfoque elegido

**electron-vite, proyecto idiomático.** Es la vía estándar del ecosistema
(justo el driver de la migración): da HMR de main/preload/renderer, TypeScript,
e integración con electron-builder sin cablear el glue de dev/build a mano.

Descartados:
- Electron a mano sin electron-vite → más glue propio que mantener; va contra el
  objetivo de apalancar el ecosistema.
- Shim runtime que emule `@tauri-apps/*` → frágil y mágico.

## Arquitectura

### Frontera nativa aislada (renderer)

Hoy el renderer importa `@tauri-apps/*` directo en ~15 sitios. Se centraliza
todo en un único módulo `src/native.ts` que expone operaciones de alto nivel,
respaldadas por `window.nyanko` (inyectado por el preload vía `contextBridge`):

- `openExternal(url|path)` — reemplaza `plugin-opener` (×6)
- `readAppDataFile(name)` — lee `port` / `instance_token` del data dir
  (reemplaza `plugin-fs` + `BaseDirectory.AppData`)
- `notify(...)` — `plugin-notification` (la Web Notification API del renderer
  también sirve; se decide en implementación)
- `pickFolder()` — `plugin-dialog` (alta de carpetas de biblioteca)
- `checkUpdate()` / `downloadAndInstall()` / `relaunch()` — `plugin-updater` +
  `plugin-process`
- `setAutostart(enabled)` — `plugin-autostart`
- controles de ventana (minimizar/cerrar) — `api/window` (titlebar frameless)
- `on(event, cb)` — `api/event` (eventos `sidecar-error`, `detection-paused`)
- `discordSetActivity(...)` / `discordClearActivity()` — `invoke` custom
- `stopSidecar()` — `invoke` custom (antes de instalar update)
- `appVersion()` — `api/app`

Beneficio: toda la app habla con **una** superficie nativa, testeable y fácil de
extender. `api.ts` (que hoy usa `readTextFile` de `plugin-fs`) pasa a usar
`native.readAppDataFile`.

### Main process (`electron/main/`)

Un archivo por responsabilidad, espejando el Rust actual:

- `compat-paths.ts` — fuente única de verdad de rutas heredadas. Exporta
  `LEGACY_APP_ID = "app.nyanko.desktop"` y `USER_DATA_DIR = join(appData,
  LEGACY_APP_ID)`. Cualquier acceso a paths pasa por acá; ningún path hardcodeado
  suelto por el main.
- `index.ts` — bootstrap: fija `app.setPath('userData', USER_DATA_DIR)` **antes**
  de cualquier acceso a paths; luego, assert duro de arranque:
  `if (!app.getPath("userData").endsWith(LEGACY_APP_ID)) throw` (crash temprano,
  no "tener cuidado"). Después: `requestSingleInstanceLock`, ventana, sidecar,
  tray.
- `logging.ts` — `electron-log` con archivos en `app.getPath('logs')`
  (`main.log`, `sidecar.log` con el stdout/stderr del sidecar pipeado). Expone
  `openLogsFolder()` (`shell.openPath`) para el botón de Ajustes. Sin pantalla de
  diagnóstico elaborada en 0.2 — solo el botón.
- `sidecar.ts` — en producción spawnea `nyanko-api.exe` (desde `resources`) con
  `NYANKO_DATA_DIR = userData`; borra el `port` file previo; espera a que el
  sidecar lo escriba (timeout 30 s); lo mata en quit / antes de update. En dev
  se omite (backend Python manual, como hoy).
- `window.ts` — `BrowserWindow` con `frame:false` (titlebar custom),
  `width:1180 height:760 minWidth:760 minHeight:560`, arranca oculta; se muestra
  salvo `--minimized` (flag de autostart o preferencia). Maneja close-to-tray y
  minimize-to-tray.
- `tray.ts` — icono + menú (Mostrar / Ocultar / Pausar-Reanudar detección /
  Salir), doble-click izquierdo muestra la ventana; el toggle de detección hace
  POST a `/api/detection/{pause,resume}` resolviendo el puerto desde el `port`
  file; emite `detection-paused` al renderer.
- `prefs.ts` — `close_to_tray` / `minimize_to_tray` / `start_minimized`
  persistidos en `window_prefs.json` dentro del userData (mismo formato actual).
- `discord.ts` — Rich Presence con `@xhayper/discord-rpc`; mismo Client ID por
  defecto y override por `NYANKO_DISCORD_CLIENT_ID`; no-op silencioso si Discord
  no está.
- `updater.ts` — electron-updater (provider GitHub). Antes de instalar: detiene
  el sidecar. Sin code-signing por ahora (se agrega después).
- `autostart.ts` — `app.setLoginItemSettings({ openAtLogin, args:['--minimized'] })`.
- `ipc.ts` — registra los handlers que consume el preload.

### Preload (`electron/preload/`)

`contextBridge.exposeInMainWorld('nyanko', { ... })` con `contextIsolation`
activo. Expone solo lo que necesita `native.ts` (IPC invoke + on/emit), nada de
Node crudo al renderer.

### Seguridad (explícita desde el día 1)

Ventana principal, `webPreferences` fijas:

```
webPreferences: {
  preload,
  contextIsolation: true,
  nodeIntegration: false,
  sandbox: true,       // compatible: el preload solo usa contextBridge + ipcRenderer
  webSecurity: true
}
```

Principios para **ventanas futuras** (tipo navegador / adapters, 0.3+ — no se
construyen en 0.2, solo se documenta la regla): nunca `nodeIntegration`, nunca
preload con APIs sensibles, `partition` separada, sin cookies compartidas con la
app principal.

### Data dir (⚠️ compatibilidad)

`userData` se fija a `%APPDATA%\app.nyanko.desktop` (el mismo que usaba Tauri
`app_data_dir()` con identifier `app.nyanko.desktop`) para que la biblioteca de
producción existente siga funcionando sin migrar. El sidecar escribe ahí `port`,
`instance_token`, `window_prefs.json`; el renderer los lee vía
`native.readAppDataFile`.

### CSP

Se replica la CSP actual (self + `127.0.0.1:*` + hosts de imágenes AniList/MAL/
Kitsu + ws local) vía `session.defaultSession.webRequest` o meta tag, según
convenga en implementación.

## Empaquetado

- **electron-builder**, target **NSIS** (español + inglés, EULA).
- `extraResources`:
  - sidecar PyInstaller: `nyanko-api.exe` + `_internal/`
  - `extension/chromium` y `extension/firefox` (bundles de la extensión)
- Auto-update: `electron-updater` publicando/consumiendo desde GitHub Releases.
  El hook NSIS que en Tauri mataba el sidecar antes de sobrescribirlo se cubre
  con `stopSidecar` + el flujo de electron-updater.

## Versionado / releases

Se mantiene semver estricto (updater lo exige) y notas de release + commits en
inglés (código en español), igual que el flujo actual. El canal de update pasa
de `latest.json` firmado (minisign) al mecanismo de electron-updater.

Integridad: electron-updater **ya verifica el SHA512** del artefacto declarado en
`latest.yml` antes de instalar, así que en el caso de un solo usuario no se
pierde garantía criptográfica al soltar minisign. La firma pública externa
(minisign/cosign) + página "Verify" es una capa de **confianza comunitaria** que
se agrega en 0.3, cuando la distribución deje de ser de un solo usuario.

## Explícitamente fuera de alcance de 0.2

Diferido a 0.3+ para mantener la 0.2 como migración pura:

- **Firma pública externa + página "Verify"** (hashes/minisign/cosign visibles).
  Integridad ya cubierta por el SHA512 de electron-updater mientras tanto.
- **Rediseño de la pantalla de extensión** (descargas por navegador, guía,
  estado de conexión visible). 0.2 preserva el flujo de extensión actual tal cual
  (bundles en `extraResources` + UI existente).
- **Adapters comunitarios** con API versionada.
- **Navegador embebido** / ventanas tipo webview para sitios externos.
- **Code-signing** del instalador Windows.

## Verificación

- Self-check del boundary `native.ts` (assert-based) que falle si falta mapear
  alguna operación nativa.
- Test del path de datos: assert de que `USER_DATA_DIR` termina en
  `app.nyanko.desktop` y que el arranque crashea si `userData` cae en otro lado
  (p.ej. `%APPDATA%\Nyanko`). Convierte el riesgo de biblioteca huérfana en un
  crash temprano y testeable, no en "tener cuidado".
- Correr la app real antes de cerrar cada fase:
  - `electron-vite dev` con backend Python manual → la biblioteca carga, tray y
    controles de ventana responden.
  - Build NSIS → el instalador corre, la app arranca el sidecar en frío, espera
    el `port` file y carga la biblioteca; auto-update detecta versión.

## Riesgos

- **Data dir**: si `userData` no queda fijado antes del primer acceso a paths,
  Electron usaría `%APPDATA%\Nyanko` (por `productName`) y la biblioteca
  existente quedaría huérfana. Es el punto de mayor cuidado.
- **Sidecar en frío**: el gate de readiness (`waitForBackend` en el front + wait
  del `port` file en el main) debe conservarse para no reintroducir el
  "Cargando biblioteca ~1min".
- **electron-updater vs firma**: sin code-signing, Windows SmartScreen puede
  advertir; aceptable para uso propio, se firma más adelante.
