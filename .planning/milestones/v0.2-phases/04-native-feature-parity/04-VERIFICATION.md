---
phase: 04-native-feature-parity
verified: 2026-07-11T14:05:00Z
status: passed
score: 3/11 must-haves verified
behavior_unverified: 8
overrides_applied: 0
deferred:

  - truth: "El icono de la bandeja/ventana existe en el build empaquetado (NSIS)"
    addressed_in: "Phase 5"
    evidence: "Phase 5 goal: 'electron-builder NSIS con sidecar+extensión como recursos'. build/icon.png es el buildResources dir de electron-builder, que por defecto NO se empaqueta dentro de la app — Phase 5 debe incluirlo en `files`/`extraResources` o el Tray quedará sin icono en producción."
behavior_unverified_items:

  - truth: "La bandeja muestra el menú (Mostrar / Ocultar / Pausar-Reanudar detección / Salir)"
    test: "Lanzar la app; click derecho en el icono de bandeja"
    expected: "Menú con exactamente: Mostrar, Ocultar, Pausar detección, separador, Salir"
    why_human: "El Tray solo existe en una sesión GUI viva; grep prueba las etiquetas, no que la bandeja se monte"

  - truth: "Doble-click en la bandeja muestra y enfoca la ventana"
    test: "Ocultar la ventana (Ocultar) y hacer doble click izquierdo en el icono"
    expected: "La ventana reaparece, se restaura si estaba minimizada y toma el foco"
    why_human: "Evento nativo del Tray; presencia del handler no prueba la transición show+restore+focus"

  - truth: "El toggle de detección hace POST a /api/detection/{pause,resume} y la etiqueta refleja el estado"
    test: "Con el backend arriba, pulsar 'Pausar detección'; luego reabrir el menú"
    expected: "El sidecar recibe POST /api/detection/pause, la etiqueta pasa a 'Reanudar detección' y el renderer recibe detection-paused"
    why_human: "Transición de estado (detectionPaused) + IO HTTP contra el sidecar vivo; en error HTTP el estado NO debe cambiar"

  - truth: "close_to_tray oculta en vez de salir; minimize_to_tray oculta al minimizar"
    test: "Ajustes → activar close-to-tray y minimize-to-tray; cerrar la ventana; luego minimizar"
    expected: "Cerrar oculta (proceso sigue vivo, icono en bandeja); minimizar oculta; 'Mostrar' la restaura; 'Salir' sí sale"
    why_human: "Invariante de cancelación: e.preventDefault() en 'close' + flag isQuitting; ningún test ejercita el evento de ventana"

  - truth: "start_minimized (o --minimized) arranca sin mostrar la ventana"
    test: "Activar start-minimized y relanzar; o lanzar con --minimized"
    expected: "La app arranca sin ventana visible (solo bandeja); 'Mostrar' la abre"
    why_human: "Orden de arranque (seed prefs → ready-to-show); solo observable en un lanzamiento real"

  - truth: "La titlebar frameless renderiza y minimizar/maximizar/cerrar responden"
    test: "Lanzar la app; usar los tres botones de la titlebar y arrastrar la barra"
    expected: "Titlebar visible; minimizar → taskbar; maximizar/restaurar; cerrar → cierra (u oculta si close-to-tray); arrastre mueve la ventana"
    why_human: "Transiciones de estado de la BrowserWindow y CSS -webkit-app-region; requieren GUI"

  - truth: "Discord Rich Presence set/clear funciona y es no-op silencioso sin Discord"
    test: "Con Discord abierto, reproducir un episodio; luego cerrar Discord con la app corriendo; luego parar la reproducción"
    expected: "Aparece la presencia (serie · Ep N / usuario · proveedor / tiempo transcurrido); al cerrar Discord la app NO crashea; al parar se limpia la presencia"
    why_human: "Requiere el cliente Discord vivo y su socket IPC local; la presencia visible no es observable por grep"

  - truth: "Single-instance trae al frente la instancia viva; autostart arranca con --minimized"
    test: "Con la app corriendo, lanzar un segundo ejecutable; luego activar autostart en ajustes y revisar el login item"
    expected: "El segundo proceso sale y la ventana viva se muestra/enfoca; el login item queda registrado con el argumento --minimized (y se elimina al desactivar)"
    why_human: "Requiere un segundo lanzamiento real y el registro de inicio de sesión de Windows"
human_verification:

  - test: "Bandeja: click derecho → menú (Mostrar / Ocultar / Pausar detección / Salir); doble-click muestra la ventana"
    expected: "Los cuatro ítems en español y el doble click restaura+enfoca"
    why_human: "El Tray solo existe en una sesión GUI viva"

  - test: "Bandeja: pulsar 'Pausar detección' con el backend arriba"
    expected: "POST /api/detection/pause llega al sidecar, la etiqueta pasa a 'Reanudar detección' y el renderer refleja la pausa"
    why_human: "Transición de estado + HTTP contra el sidecar vivo"

  - test: "Prefs de ventana: activar close-to-tray / minimize-to-tray y cerrar/minimizar"
    expected: "Ambas ocultan a bandeja; 'Mostrar' restaura; 'Salir' hace un quit limpio (sin nyanko-api.exe huérfano)"
    why_human: "Intercepción de eventos de ventana; no ejercitada por ningún test"

  - test: "Start-minimized: activar el ajuste (o lanzar con --minimized)"
    expected: "La app arranca sin ventana visible, solo icono de bandeja"
    why_human: "Solo observable en un lanzamiento real"

  - test: "Titlebar frameless: minimizar / maximizar / cerrar + arrastre"
    expected: "Los tres botones responden y la barra arrastra la ventana"
    why_human: "Transiciones de estado de la ventana; requieren GUI"

  - test: "Discord: reproducir con Discord abierto; cerrar Discord a mitad de sesión; parar la reproducción"
    expected: "Presencia visible con details/state/elapsed; sin crash al cerrar Discord; clear al parar"
    why_human: "Requiere el socket IPC local de Discord"

  - test: "Single-instance: lanzar un segundo ejecutable con la app corriendo"
    expected: "El segundo sale y la ventana viva se muestra + enfoca (incluso desde bandeja)"
    why_human: "Requiere un segundo lanzamiento real"

  - test: "Autostart: activar el toggle en ajustes y revisar el login item de Windows"
    expected: "Login item registrado con --minimized; al desactivar, eliminado"
    why_human: "Requiere inspeccionar el registro de inicio de sesión del SO"
---

# Phase 4: Native feature parity — Verification Report

**Phase Goal:** Las features nativas que Tauri proveía funcionan con equivalentes de Electron, replicando el comportamiento de 0.1.15.
**Verified:** 2026-07-11
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

Toda la superficie nativa de la Fase 4 existe, es sustantiva y está cableada de punta a punta
(renderer → `native.ts` → `window.nyanko` → `ipcMain.handle` → módulo main). No queda **ningún**
stub de Fase 4: `grep -c 'throw new Error' src/native.ts` = **1** (solo `checkForUpdates`, Fase 5).
La paridad con el Rust borrado se comprobó leyendo `a50659c^` (tray.rs, window_prefs.rs, discord.rs,
lib.rs) — las etiquetas, el contrato de error y el orden de arranque coinciden.

Lo que queda son 8 verdades **behavior-dependent**: transiciones de estado que solo una sesión GUI
viva (bandeja, ventana, Discord, segundo lanzamiento, login item) puede ejercitar. No son fallos —
el código está presente y cableado — pero no se certifican por presencia.

### Observable Truths

| # | Truth (SC del ROADMAP + must_haves de los planes) | Status | Evidence |
|---|---|---|---|
| 1 | La bandeja muestra el menú Mostrar / Ocultar / Pausar-Reanudar detección / Salir | ⚠️ PRESENT_BEHAVIOR_UNVERIFIED | `tray.ts:73-88` construye exactamente esos 4 ítems + separador (etiquetas idénticas a `tray.rs:9-13`); `setupTray(() => mainWindow)` se llama en `index.ts:121` tras `createWindow()`. El montaje del Tray solo es observable en GUI |
| 2 | Doble-click en la bandeja muestra la ventana | ⚠️ PRESENT_BEHAVIOR_UNVERIFIED | `tray.ts:92` `tray.on("double-click", …showWindow())`; `showWindow` hace restore+show+focus (`tray.ts:34-39`). Evento nativo → GUI |
| 3 | El toggle de detección hace POST a /api/detection/{pause,resume} | ⚠️ PRESENT_BEHAVIOR_UNVERIFIED | `tray.ts:44-63`: POST `${resolveApiUrl()}/api/detection/${paused?"pause":"resume"}`, timeout 5s, en error HTTP loguea y NO cambia estado (mirror `tray.rs:95-105`); en éxito reconstruye la etiqueta y emite `detection-paused` al renderer (suscrito en `App.tsx:355`). Transición de estado sin test |
| 4 | window_prefs.json persiste {close_to_tray, minimize_to_tray, start_minimized}, defaults false, sin migración | ✓ VERIFIED | `window-prefs.ts` (schema exacto, `coercePrefs` a 3 booleanos, fichero corrupto/ausente → defaults); ruta = `app.getPath("userData")` inyectada en `index.ts:119` (`seedWindowPrefs`) → `%APPDATA%\app.nyanko.desktop\window_prefs.json`. `npm run test:prefs` pasa (round-trip, descarte de claves extra/`__proto__`, defaults) |
| 5 | Las prefs gobiernan close→tray, minimize→tray, start-minimized | ⚠️ PRESENT_BEHAVIOR_UNVERIFIED | `index.ts:55-64` (`close` → preventDefault+hide si `close_to_tray && !isQuitting`; `minimize` → hide si `minimize_to_tray`) e `index.ts:70-72` (`start_minimized \|\| argv --minimized` → NO `show()`), paridad literal con `lib.rs:48-76`. Invariante de cancelación/orden no ejercitada por ningún test |
| 6 | La titlebar frameless (minimizar/cerrar) responde | ⚠️ PRESENT_BEHAVIOR_UNVERIFIED | `App.tsx:1039-1040` gate flipado a `isNative` (0 ocurrencias de `HAS_TAURI`); botones → `native.minimizeWindow/toggleMaximizeWindow/closeWindow` (`App.tsx:114-122`) → IPC `window:*` que opera SOLO sobre `BrowserWindow.fromWebContents(e.sender)` (`ipc.ts:73-82`); `frame:false` + `icon` en `index.ts:32-49`. Transición de ventana → GUI |
| 7 | Discord RP set/clear con el mismo Client ID; no-op silencioso sin Discord | ⚠️ PRESENT_BEHAVIOR_UNVERIFIED | `discord.ts:11-16` id `1521045260342525962` + override `NYANKO_DISCORD_CLIENT_ID` + centinela `REPLACE_WITH_…` (idéntico a `discord.rs`); conexión perezosa, try/catch que traga y suelta el cliente, listener `error` no-op (evita crash del main si Discord cierra a mitad). Presencia visible → requiere Discord vivo |
| 8 | Single-instance trae al frente la instancia viva | ⚠️ PRESENT_BEHAVIOR_UNVERIFIED | `index.ts:135-143`: `requestSingleInstanceLock()` → si falla `app.quit()`; el vivo hace show+restore+focus (paridad `lib.rs:11-16`). Requiere un segundo lanzamiento real |
| 9 | Autostart arranca con --minimized | ⚠️ PRESENT_BEHAVIOR_UNVERIFIED | `ipc.ts:101-104`: `autostart:get` → `getLoginItemSettings().openAtLogin`; `autostart:set` → `setLoginItemSettings({openAtLogin: Boolean(enabled), args:["--minimized"]})` (paridad `lib.rs:21-23`); consumido por `App.tsx:332/605`. El login item registrado solo se observa en el SO |
| 10 | Notificaciones, abrir externos (opener) y selector de carpetas (dialog) funcionan — cableado de Fase 3 intacto y sin debilitar | ✓ VERIFIED | `ipc.ts:41-67`: `openExternal` conserva `/^https?:\/\//i`, `openPath`/`revealItemInDir` conservan el rechazo de `://`, `openFolderDialog` → `dialog.showOpenDialog(openDirectory)`, `notify` → `Notification`. Spot-check de los guards: PASS. Consumidores vivos: `LibrarySettingsView.tsx:28` (dialog), `App.tsx:367` (notify), `native.openExternal` |
| 11 | No queda ningún stub de Fase 4 en la frontera nativa (solo el updater de Fase 5) | ✓ VERIFIED | `grep -c 'throw new Error' src/native.ts` = 1 (`checkForUpdates`); las 17 ops restantes enrutan por `window.nyanko?…`; `NATIVE_OPS` = 18 claves y `npm run test:native` pasa 2/2; `vite-env.d.ts` declara los 9 métodos nuevos del bridge |

**Score:** 3/11 truths verified (8 present, behavior-unverified)

### Deferred Items

| # | Item | Addressed In | Evidence |
|---|------|--------------|----------|
| 1 | El icono (ventana + bandeja) debe existir en el paquete NSIS | Phase 5 | `build/icon.png` es el `buildResources` dir de electron-builder, que **por defecto no se empaqueta dentro de la app**. `index.ts:40` y `tray.ts:69` lo resuelven como `join(__dirname, "../../build/icon.png")` — correcto en dev/preview, pero Phase 5 ("electron-builder NSIS con sidecar+extensión como recursos") debe incluirlo en `files`/`extraResources` o la bandeja quedará sin icono en producción |

### Required Artifacts

| Artifact | Expected | Status | Details |
|---|---|---|---|
| `apps/desktop/build/icon.png` | Icono de marca ≥256x256 (D-07) | ✓ VERIFIED | 256x256 PNG; referenciado por la BrowserWindow y por el Tray (mismo asset, sin icono monocromo — D-07) |
| `apps/desktop/electron/main/tray.ts` | Tray + menú + doble-click + POST detección | ✓ VERIFIED | 94 líneas, sustantivo; idempotente (`if (tray) return tray`) |
| `apps/desktop/electron/main/window-prefs.ts` | Carga/guarda/caché de las 3 prefs | ✓ VERIFIED | Núcleo electron-free (dir inyectado) → testeable; `coercePrefs` mitiga T-04-05 |
| `apps/desktop/electron/main/discord.ts` | Cliente RPC perezoso, no-op silencioso | ✓ VERIFIED | 87 líneas; `@xhayper/discord-rpc@^1.3.4` en `package.json` (gate T-04-SC aprobado por humano) |
| IPC `window:minimize` / `:toggle-maximize` / `:close` | 3 handlers | ✓ VERIFIED | `ipc.ts:73-82`, solo sobre la ventana del emisor |
| IPC `window-prefs:get` / `:set` | 2 handlers | ✓ VERIFIED | `ipc.ts:88-89` (set coacciona el payload) |
| IPC `discord:set-activity` / `:clear-activity` | 2 handlers | ✓ VERIFIED | `ipc.ts:94-95` |
| IPC `autostart:get` / `:set` | 2 handlers | ✓ VERIFIED | `ipc.ts:101-104` con `args:["--minimized"]` |
| Cuerpos reales en `native.ts` | 9 stubs de Fase 4 rellenados | ✓ VERIFIED | window controls, prefs, discord, autostart — todos por `window.nyanko?` con fallback web |
| `window-prefs.test.ts` | Self-check de round-trip/coerción | ✓ VERIFIED | 4 tests; `npm run test:prefs` en `package.json` |

### Key Link Verification

| From | To | Via | Status |
|---|---|---|---|
| `App.tsx` (titlebar) | `ipc.ts window:*` | `native.minimizeWindow` → preload `minimizeWindow` → `window:minimize` → `BrowserWindow.fromWebContents(sender)` | WIRED |
| `DetectorSettingsView.tsx:96/115` | `window-prefs.ts` | `getWindowPrefs`/`setWindowPrefs` → `window-prefs:get/set` → `currentWindowPrefs`/`updateWindowPrefs` (persiste a disco + refresca caché) | WIRED |
| `index.ts:119` | `window-prefs.ts` | `seedWindowPrefs(app.getPath("userData"))` ANTES de `createWindow()` → `ready-to-show` lee `start_minimized` | WIRED |
| `index.ts:121` | `tray.ts` | `setupTray(() => mainWindow)` tras `createWindow()` | WIRED |
| `tray.ts:62` | `App.tsx:355` | `webContents.send("detection-paused")` → preload `onDetectionPaused` → `setDetectionPaused` | WIRED |
| `tray.ts:49` | sidecar local | `http://127.0.0.1:{port desde userData/port, fallback 8765}/api/detection/{pause\|resume}` | WIRED |
| `App.tsx:493` | `discord.ts` (main) | `setDiscordActivity` → `discord:set-activity` → cliente `@xhayper` perezoso | WIRED |
| `App.tsx:332/605` | `ipc.ts autostart:*` | `getAutostart`/`setAutostart` → `setLoginItemSettings` | WIRED |
| `tray.ts:85` Salir | `index.ts:158` before-quit | `app.quit()` → `isQuitting=true` + `killSidecar()` (mismo camino, sin duplicar) | WIRED |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|---|---|---|---|---|
| `DetectorSettingsView.tsx` | `windowPrefs` | `getWindowPrefs()` → IPC → caché sembrada desde `window_prefs.json` | Sí (fichero real, no defaults hardcodeados) | ✓ FLOWING |
| `App.tsx` autostart toggle | `autostart` | `getAutostart()` → `app.getLoginItemSettings().openAtLogin` | Sí (estado real del SO) | ✓ FLOWING |
| `App.tsx` detection badge | `detectionPaused` | evento `detection-paused` emitido por el tray tras un POST OK | Sí (solo tras confirmación del sidecar) | ✓ FLOWING |
| `tray.ts` menú | `detectionPaused` | booleano en memoria (paridad `DetectionPaused` del Rust) | Sí (mismo contrato que 0.1.15) | ✓ FLOWING |
| `discord.ts` activity | `details/state/startTimestamp` | payload del renderer (serie/episodio/usuario reales de `App.tsx:490-496`) | Sí | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|---|---|---|---|
| El bundle de main contiene el código de Fase 4 (no solo los fuentes) | grep sobre `out/main/index.js` | `Pausar detecci`=1, `window_prefs.json`=1, `1521045260342525962`=1, `--minimized`=2, `api/detection/`=1, `build/icon.png`=3 | ✓ PASS |
| El bundle de preload expone los canales nuevos | grep sobre `out/preload/index.cjs` | `window-prefs:get`, `discord:set-activity`, `autostart:set`, `window:close` presentes | ✓ PASS |
| Guards de Fase 3 no debilitados | replay de los regex de `ipc.ts` en node | `https?://` OK; `file://`, `javascript:`, `ms-settings:` rechazados; `openPath` rechaza `://` | ✓ PASS |
| Icono ≥256x256 | `sharp('build/icon.png').metadata()` | 256x256 png | ✓ PASS |
| Tray/Discord/prefs en runtime | — | Requiere sesión GUI + Discord + segundo lanzamiento | ? SKIP → human_verification |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|---|---|---|---|---|
| NATIVE-03 | 04-02 | Bandeja: menú, doble-click, toggle de detección | ✓ SATISFIED (conducta → human) | `tray.ts` completo y cableado en `index.ts:121` |
| NATIVE-04 | 04-01, 04-02 | Prefs de ventana + titlebar frameless | ✓ SATISFIED (conducta → human) | `window-prefs.ts` + `test:prefs` verde; titlebar con gate `isNative`; close/minimize/start-minimized en `index.ts` |
| NATIVE-05 | 04-03 | Discord Rich Presence | ✓ SATISFIED (conducta → human) | `discord.ts` con el Client ID y el contrato de no-op silencioso |
| NATIVE-06 | 04-03 | Single-instance, autostart, notif, opener, dialog | ✓ SATISFIED (conducta → human) | `requestSingleInstanceLock` + `second-instance`; `setLoginItemSettings(--minimized)`; handlers de Fase 3 intactos |

**Orphaned requirements:** ninguno. `.planning/REQUIREMENTS.md` mapea exactamente NATIVE-03/04/05/06 a la Fase 4 y los tres planes los reclaman todos.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|---|---|---|---|---|
| `src/native.ts` | 3 | Comentario obsoleto: "Las ops de Fase 4/5 son stubs" (solo queda la de Fase 5) | ℹ️ Info | Documentación desfasada, cero impacto funcional |
| `src/autostart.ts` | 4 | "native.getAutostart/setAutostart son stubs de Fase 4" — ya no lo son | ℹ️ Info | Idem |
| `src/discord.ts` | 7 | "native.setDiscordActivity/clearDiscordActivity son stubs de Fase 4" — ya no lo son | ℹ️ Info | Idem |
| `src/windowPrefs.ts` | 8 | "native.getWindowPrefs/setWindowPrefs son stubs de Fase 4" — ya no lo son | ℹ️ Info | Idem |
| `electron/preload/index.ts` | 39 | "el emisor (tray/window) llega en Fase 4" — ya llegó | ℹ️ Info | Idem |

**Marcadores de deuda (TBD/FIXME/XXX):** ninguno. Los dos aciertos de `TODO` en el grep son la palabra española "TODO" ("TODO acceso a window…", "es TODO el contrato…"), no marcadores de deuda.

### Human Verification Required

8 ítems — todos requieren una sesión GUI viva (ver `human_verification` en el frontmatter):

1. **Bandeja — menú y doble-click.** Click derecho → Mostrar / Ocultar / Pausar detección / (sep) / Salir; doble click izquierdo restaura y enfoca.
2. **Bandeja — toggle de detección.** Con el backend arriba, "Pausar detección" → POST llega al sidecar, la etiqueta pasa a "Reanudar detección" y el renderer refleja la pausa.
3. **Prefs de ventana.** close-to-tray y minimize-to-tray ocultan a bandeja; "Mostrar" restaura; "Salir" hace quit limpio sin `nyanko-api.exe` huérfano.
4. **Start-minimized.** Con el ajuste activo (o lanzando con `--minimized`) la app arranca sin ventana visible.
5. **Titlebar frameless.** Minimizar / maximizar / cerrar responden; la barra arrastra la ventana.
6. **Discord.** Presencia visible con serie·episodio / usuario·proveedor / tiempo transcurrido; cerrar Discord a mitad de sesión NO crashea; parar la reproducción limpia la presencia.
7. **Single-instance.** Un segundo lanzamiento sale y trae al frente la ventana viva (incluso desde bandeja).
8. **Autostart.** El toggle registra el login item con `--minimized`; desactivarlo lo elimina.

### Gaps Summary

**Ninguna brecha bloqueante.** Los 9 stubs de Fase 4 de la frontera `native.ts` están rellenados con
implementaciones reales (solo `checkForUpdates` sigue lanzando — es Fase 5, PKG-02, correcto). Los
guards de seguridad de Fase 3 (allowlist `http(s)` en `openExternal`, rechazo de `://` en
`openPath`/`revealItemInDir`) siguen intactos y se verificaron por replay; `contextIsolation`,
`nodeIntegration:false`, `sandbox:true` y `webSecurity:true` no se tocaron. Las decisiones bloqueadas
del CONTEXT (D-01 `@xhayper/discord-rpc`, D-02 Client ID + env override, D-03 no-op silencioso, D-04
titlebar verbatim, D-05 esquema/ruta de `window_prefs.json`, D-06 etiquetas del menú, D-07 icono
único, D-08 paridad contra el Rust de `a50659c^`) se honran todas — comprobado leyendo el Rust
borrado, no las SUMMARY.

Lo único pendiente es conducta observable únicamente en una sesión GUI viva (8 ítems arriba), más un
riesgo de empaquetado **diferido a Fase 5**: `build/` es el `buildResources` dir de electron-builder
y no se empaqueta dentro de la app por defecto — Fase 5 debe incluir `build/icon.png` como app file
o la bandeja quedará sin icono en el NSIS.

---

_Verified: 2026-07-11_
_Verifier: Claude (gsd-verifier)_
