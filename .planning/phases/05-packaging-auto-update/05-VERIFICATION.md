---
phase: 05-packaging-auto-update
verified: 2026-07-12T22:40:00Z
reverified: 2026-07-13T05:25:00Z
status: passed
score: 11/11 must-haves verified
behavior_unverified: 0
overrides_applied: 0
acknowledged_gaps: []
reverification:
  reason: |
    El audit del milestone (2026-07-12) encontró B-1: `customCheckAppRunning` NO es aditiva —
    es la rama !else del check del propio electron-builder. Definirla desactivaba
    _CHECK_APP_RUNNING, que avisa y mata Nyanko.exe antes de extraer. Esta verificación era
    ANTERIOR al arreglo, así que quedó stale por construcción: el installer.nsh que verificó
    ya no es el que hay en el árbol.
  changes_verified:
    - "installer.nsh: customCheckAppRunning reconstruida como aditiva (a2c645d)"
    - "native.ts: openLogsFolder entra en la frontera — 20 ops (W-1)"
    - "updater.ts: autoUpdater.once('error') → app.quit() antes de killSidecar (W-2)"
  human_gate:
    date: 2026-07-13
    test: "Nyanko 0.2.3 ABIERTA + doble click en Nyanko-Setup-0.2.4.exe (sin /S)"
    result: "PASA — las tres cosas confirmadas por el humano: (a) el instalador AVISA de que Nyanko está abierta y la cierra antes de extraer (B-1 arreglado: eso es _CHECK_APP_RUNNING, la macro que estaba desactivada); (b) selector de idioma ES/EN; (c) página del EULA"
    closes: ["B-1", "SC1b (selector ES/EN + EULA)"]
deferred:

  - truth: "El backend no debe persistir URLs de assets con el host:puerto dentro (D-I-02)"
    addressed_in: "0.3 — YA RESUELTO (quick 260712-q62)"
    evidence: "main.py:_asset_url() devuelve rutas relativas y database.py:_migrate_asset_urls_to_relative() reescribe las ya persistidas en initialize(). Verificado en el árbol. Bug PREEXISTENTE del backend, no regresión de la Fase 5; los datos se repararon en 05-06 (3.874 URLs) y el fallo de diseño se cerró después, fuera del alcance de 0.2 (engine-swap puro)"

  - truth: "El limitador de AniList debe reflejar el rate limit real (D-I-03)"
    addressed_in: "0.3"
    evidence: "anilist.py:482 sigue con `RateLimitedClient(requests_per_minute=90)` mientras AniList responde `X-RateLimit-Limit: 30`. No muerde hoy (backfill secuencial ≈1 req/2 s) pero cualquier ráfaga comería 429s. Backend = fuera del alcance de 0.2"

behavior_unverified_items: []

human_verification: []
---

# Phase 5: Packaging + auto-update — Verification Report

**Phase Goal:** La app se distribuye como instalador Windows firmable-a-futuro y se actualiza sola desde GitHub Releases, cerrando la paridad con el flujo de release Tauri.
**Verified:** 2026-07-12
**Status:** passed (el objetivo de la fase **está conseguido**; 1 ítem cosmético aceptado sin verificar en el gate humano del 2026-07-12 — ver `acknowledged_gaps`)
**Re-verification:** No — verificación inicial

## Goal Achievement

**El objetivo de la fase se cumple, y no por inspección de código: por ejecución.** Los dos hitos que
definen la fase se ejercitaron sobre instalaciones reales con gate humano, y ambos dejaron rastro
objetivo:

- **D-01 (el puente):** una instalación **0.1.15 real** arrancó sola, sondeó `latest.json`, verificó
  la firma minisign contra la pubkey horneada en su propio binario y **ejecutó el instalador 0.2.0
  por su cuenta**. Que el instalador llegue a arrancar *es* la prueba de la firma — Tauri se niega a
  ejecutar un binario que no verifica.
- **PKG-02 (el auto-update):** una **0.2.0 instalada** detectó la 0.2.1, la descargó
  **diferencialmente** (766 KB de 128 MB vía `.blockmap`), verificó su SHA512, ejecutó `killSidecar()`
  → `quitAndInstall(true, true)`, se reinstaló **sin asistente** y **se relanzó sola**. Biblioteca
  intacta, **cero** `nyanko-api.exe` huérfanos. Gate humano aprobado 2026-07-12.

Comprobado además **contra la red, en el momento de esta verificación** (no contra las SUMMARY):
`releases/latest/download/latest.yml` → `version: 0.2.3`, `size: 131.201.778` = tamaño exacto del
asset publicado; `latest.json` con URL **basada en el tag** (no `untagged-…`, la trampa del 05-04) y
firma cuyo **key id `d4f6287094b6caba` coincide** con el `EMBEDDED_PUBKEY_B64` del puente.

Lo único abierto es **una página de asistente que nadie ha mirado** (selector ES/EN + EULA). No es un
fallo: es config presente que ninguna de las tres instalaciones de la fase pudo observar (dos fueron
silenciosas/por-updater y el gate de la tercera preguntó por otras cosas).

**Y un hallazgo de la red que contradice a las SUMMARY: los releases v0.2.1 y v0.2.2 YA NO EXISTEN**
(404). Ver «Anti-Patterns / Hallazgos».

### Observable Truths

| # | Truth (SC del ROADMAP + must_haves de los planes) | Status | Evidence |
|---|---|---|---|
| 1 | `electron-builder` produce un instalador NSIS que **corre e instala la app** (SC1a) | ✓ VERIFIED | `electron-builder.yml`: `win.target: nsis`, `oneClick:false`, `perMachine:false`, `artifactName: Nyanko-Setup-${version}.${ext}`. Artefactos reales en `release/`: 0.2.0/0.2.1/0.2.2/0.2.3 (`Nyanko-Setup-0.2.3.exe` = 131.201.778 B, idéntico al publicado). **Ejecutado 3 veces sobre la máquina real:** `/S` sobre una 0.1.15 (05-03, exit 0), instalación manual con gate humano (05-02) y lanzado por el updater de Tauri (05-04). En las tres la app quedó instalada y arrancó |
| 2 | El asistente muestra **selector ES/EN + página del EULA** (SC1b) | ✓ VERIFIED (re-verificación 2026-07-13) | Config presente y cableada: `installerLanguages: [es_ES, en_US]`, `multiLanguageInstaller: true`, `displayLanguageSelector: true`, `license: build/EULA.txt` (74 líneas bilingües, byte-idéntico a `a50659c^`). **OBSERVADO POR EL HUMANO** el 2026-07-13 al ejecutar `Nyanko-Setup-0.2.4.exe` a doble click (sin `/S`): ambas páginas salen. Deja de ser el gap cosmético que la verificación original aceptó a ciegas — el payload comprimido en sólido no era greppable, así que la única vía era mirarlo, y se miró |
| 11 | **El instalador AVISA y cierra Nyanko antes de extraer** (B-1 — regresión de integración cruzada P2↔P5) | ✓ VERIFIED (re-verificación 2026-07-13) | Verdad que la verificación original **no podía contemplar**: la introdujo el audit del milestone. `customCheckAppRunning` es la rama `!else` del check de electron-builder (`allowOnlyOneInstallerInstance.nsh:36-42`), **no un hook aditivo** — definirla desactivaba `_CHECK_APP_RUNNING` en instalador Y desinstalador. Reconstruida como aditiva en `a2c645d` (`taskkill` del sidecar + `IS_POWERSHELL_AVAILABLE` + `_CHECK_APP_RUNNING`; el `!include getProcessInfo.nsh` + `Var pid` son obligatorios porque el include del framework va bajo `!ifmacrondef customCheckAppRunning`). **Probado en runtime el 2026-07-13**: con Nyanko 0.2.3 abierta, `Nyanko-Setup-0.2.4.exe` **avisa y la cierra** antes de extraer. Antes del arreglo: ni aviso ni kill |
| 3 | El instalado incluye el **sidecar** (`nyanko-api.exe` + `_internal`) y los **bundles de extensión** (`chromium`/`firefox`) como `extraResources`, y la app arranca el sidecar en frío y **carga la biblioteca** (SC2) | ✓ VERIFIED | Layout verificado **en el paquete en disco**: `release/win-unpacked/resources/nyanko-api/{nyanko-api.exe, _internal/, extension/chromium/manifest.json, extension/firefox/manifest.json}` + `resources/icon.png` + `resources/app-update.yml`. **NO** existe `resources/extension/` (el sitio "obvio" que habría devuelto nulls en `/api/extension/bundle`). Arranque en frío + biblioteca: gates humanos de 05-02 («la biblioteca carga») y 05-03 («la biblioteca renderiza con su contenido real») |
| 4 | `electron-updater` **detecta** una versión nueva en GitHub Releases, la **descarga verificando SHA512** y la **instala tras detener el sidecar** (SC3 / PKG-02) | ✓ VERIFIED | `updater.ts`: `autoDownload=false`; `checkForUpdate()` → `isUpdateAvailable`; `downloadAndInstallUpdate()` → `downloadUpdate()` → **`killSidecar()`** → `quitAndInstall(true,true)` (D-04/D-05), con guarda de módulo `updateAvailable` (T-05-05). Cableado end-to-end: `ipc.ts:111-112` (`updates:check`/`updates:install`) → preload `:42-43` → `native.ts:100-104`. **En el asar empaquetado**: `autoUpdater` ×7, `killSidecar` ×5, `quitAndInstall` ×1. **Ejecutado 0.2.0 → 0.2.1 sobre una instalación real** (gate humano 2026-07-12): `main.log` → `Full: 128,125.5 KB, To download: 766.47 KB (1%)`, SHA512 OK, instalación sin asistente, relanzado automático, cero sidecars huérfanos |
| 5 | El parque **0.1.15** llega a 0.2.x por el puente minisign/`latest.json` (D-01, PKG-01/02) | ✓ VERIFIED | `scripts/publish-bridge.mjs` (firma → **verifica antes de subir** → publica; exige exactamente UN release con el tag). `npm run test:publish` → **5/5**. **Contra la red hoy**: `latest.json` del release latest tiene `url` basada en el **tag** (`…/download/v0.2.3/Nyanko-Setup-0.2.3.exe`, no `untagged-…`) y su firma decodifica a key id **`d4f6287094b6caba`**, el mismo que el `EMBEDDED_PUBKEY_B64` del puente. **E2E real (05-04):** una 0.1.15 instalada se auto-migró a 0.2.0 sola |
| 6 | La migración desde Tauri **no toca la biblioteca** (D-02 / DATA-01) | ✓ VERIFIED | `build/installer.nsh` → `!macro customInit`: rama A completa — `ReadRegStr` de `HKCU\…\Uninstall\Nyanko` (clave literal medida, no un GUID), `NyankoUnquote` (las comillas van DENTRO del dato), guarda `StrCmp ""` (usuario nuevo), `ExecWait '"$0" /S _?=$1'` (síncrono de verdad) + remate `Delete`/`RMDir /r`. `deleteAppDataOnUninstall: false` en el `.yml`. **Medido sobre la instalación real:** `nyanko.sqlite3` 30.990.336 B / md5 idéntico antes y después; tras la migración D-01, `integrity_check: ok` con **2.761** `library_entries` y **25.727** `episodes` — idéntico tabla a tabla al backup |
| 7 | **El icono existe en el build empaquetado (NSIS)** — diferido de la Fase 4 | ✓ VERIFIED — **DIFERIDO CERRADO** | `compat-paths.ts:22` `iconPath(isPackaged, resourcesPath, mainDir)`; los dos call sites lo usan (`index.ts:40` BrowserWindow, `tray.ts:73` Tray) y **ya no queda ninguna ruta literal `build/icon.png` en `electron/`** (el único acierto del grep es el *nombre* de un test). `extraResources: build/icon.png → icon.png`. En disco: `resources/icon.png` = `build/icon.png` = **33.841 B**. `npm run test:datadir` → **5/5** (incluye rama empaquetada y rama dev). **Confirmación visual humana** sobre el NSIS instalado (gates 05-02 y 05-03): el gatito sale en bandeja y en ventana |
| 8 | La cadena de build es **Rust-free** y no queda **ningún stub** en la frontera nativa | ✓ VERIFIED | `npm run build` = `build:extension → build:sidecar → dist` (cero llamadas al CLI de Tauri); `apps/desktop/src-tauri` **no existe**; cero `@tauri-apps/*` en los `package.json` (el puente lo invoca por `npx` con versión pineada). `grep -c 'throw new Error' src/native.ts` = **0** (era 1 al cerrar la Fase 4: `checkForUpdates`). `NATIVE_OPS` = 19 ops, `npm run test:native` → **2/2**. `npm run check` (tsc) → **0**. El asar **no** contiene el viejo `"Actualizaciones: Fase 5"` |
| 9 | **Higiene del paquete**: el asar no lleva config de desarrollo (D-I-01) | ✓ VERIFIED | `asar.listPackage()` → 1.763 entradas, **0** coincidencias con `.claude` / `.env`. Bloque `files:` con exclusiones **negativas** (`!.claude${/*}`, `!.env*`, `!electron-builder.yml`). El `.env` del backend (el que tiene el `CLIENT_SECRET`) nunca viajó |
| 10 | **Ambos feeds** publicados y resolubles por un cliente anónimo | ✓ VERIFIED | `curl` sin token: `releases/latest/download/latest.yml` → `version: 0.2.3`, `sha512`, `size: 131201778` = **tamaño exacto del asset publicado** (API); `releases/latest/download/latest.json` → 200, firma + url por tag. El release **v0.2.3** trae los **cinco** artefactos (`.exe`, `.blockmap`, `.sig`, `latest.yml`, `latest.json`), no es borrador ni prerelease. `resources/app-update.yml` dentro del paquete: `provider: github, owner: kfernandoy, repo: Nyanko` (T-05-04: el feed **no** es configurable desde el código) |

**Score:** 11/11 truths verified (re-verificación 2026-07-13: el ítem 2 se observó y el ítem 11 se añadió y se probó)

### Re-verificación 2026-07-13 — por qué existía

Esta verificación quedó **stale por construcción**: el audit del milestone encontró B-1 *después* de
escribirla, y el arreglo cambió el `installer.nsh` que ella había verificado. El fallo vivía en la
**costura** entre la Fase 2 (matar el sidecar, que bloquea ficheros) y la Fase 5 (empaquetar): el
arreglo de la 5 al problema de la 2 **desactivó en silencio la protección de bloqueo de ficheros del
propio framework**, y ningún gate por fase podía verlo porque ambas fases son, por separado,
correctas. En máquina rápida el auto-update gana la carrera, que es exactamente por qué pasó.

El gate humano del 2026-07-13 cerró **tres** ítems de una sola ejecución (Nyanko abierta + instalador
sin `/S`): el aviso de app-en-ejecución (B-1), el selector de idioma y el EULA.

### Deferred Items

| # | Item | Addressed In | Evidence |
|---|------|--------------|----------|
| 1 | **D-I-02** — el backend persiste URLs de assets con el `host:puerto` dentro; si el sidecar cambia de puerto, la biblioteca se queda sin portadas de forma permanente y silenciosa | 0.3 — **ya resuelto** (quick 260712-q62) | Bug **preexistente** del backend que el reinicio del sidecar (inherente a todo update) se limitó a **revelar** — no es regresión de la Fase 5. En 05-06 se repararon los **datos** (3.874 URLs) y se dejó `check_stale_asset_ports.py`. El **diseño** se arregló después: `main.py:_asset_url()` devuelve rutas relativas y `database.py:_migrate_asset_urls_to_relative()` reescribe las persistidas en `initialize()` — **verificado en el árbol**. STATE.md aún lo lista como *Deferred* (drift documental) |
| 2 | **D-I-03** — `RateLimitedClient(requests_per_minute=90)` pero AniList responde hoy `X-RateLimit-Limit: 30` | 0.3 | **Sigue abierto**: `anilist.py:482` mantiene el `90`. No muerde hoy (backfill secuencial ≈1 req/2 s) pero una ráfaga comería 429s. Backend = fuera del alcance de 0.2 (engine-swap puro) |

### Required Artifacts

| Artifact | Expected | Status | Details |
|---|---|---|---|
| `apps/desktop/electron-builder.yml` | Config NSIS: appId, extraResources, publish, EULA, hook | ✓ VERIFIED | 79 líneas. `appId: app.nyanko.desktop` (load-bearing: fija `userData`), `deleteAppDataOnUninstall: false`, `publish: github/kfernandoy/Nyanko`, `include: build/installer.nsh` (no `script`: `script` reemplazaría el instalador entero) |
| `apps/desktop/build/installer.nsh` | `customCheckAppRunning` (taskkill) + `customInit` (rama A D-02) | ✓ VERIFIED | 83 líneas, dos macros. El `taskkill` está en `customCheckAppRunning` **y no en `customInit`** (T-05-05: `customInit` corre antes del asistente → 30-60 s de ventana para que el usuario respawnee el sidecar) |
| `apps/desktop/build/EULA.txt` | Licencia bilingüe ES/EN | ✓ VERIFIED | Restaurado byte-idéntico de `a50659c^`; cableado en `nsis.license` |
| `apps/desktop/electron/main/updater.ts` | `checkForUpdate()` + `downloadAndInstallUpdate()` | ✓ VERIFIED | 64 líneas, sustantivo. `autoDownload=false`, `autoInstallOnAppQuit=false`, `logger = electron-log` (OBS-01), `assertPackaged()` reusa `isDevMode()` del sidecar, guarda `updateAvailable` |
| `apps/desktop/scripts/publish-bridge.mjs` | Firma minisign + verifica + publica `latest.json` | ✓ VERIFIED | Ancla de confianza LITERAL en el script (`EMBEDDED_PUBKEY_B64`), URL compuesta del **tag**, exige exactamente UN release con ese tag. Test hermano: **5/5** |
| `iconPath()` en `compat-paths.ts` | Resolución única del icono (dev + empaquetado) | ✓ VERIFIED | Función pura de 3 líneas; `compat-paths.ts` sigue **Electron-free** (por eso su test corre bajo Node plano). `test:datadir` 5/5 |
| `resources/nyanko-api/` en el paquete | sidecar + `_internal` + `extension/{chromium,firefox}` | ✓ VERIFIED | Los cuatro presentes en `release/win-unpacked/`; ambos `manifest.json` existen |
| `resources/app-update.yml` en el paquete | Feed del updater (fuera del código) | ✓ VERIFIED | `provider: github, owner: kfernandoy, repo: Nyanko` |
| `apps/backend/scripts/check_stale_asset_ports.py` | Check ejecutable de D-I-02 | ✓ VERIFIED | 2.425 B, committeado (en 05-06 vivía en `scratchpad/`) |
| `docs/extra/RELEASING.md` | Runbook del flujo de release Electron | ⚠️ NO TRACKEADO | Existe **en disco**, pero `docs/extra/` está gitignorado y nunca ha estado trackeado. Ver «Anti-Patterns / Hallazgos» |

### Key Link Verification

| From | To | Via | Status |
|---|---|---|---|
| `DetectorSettingsView.tsx` (Acerca de) | `native.ts:100-104` | `checkForUpdates` / `installUpdate` → `window.nyanko` (fallback web: `null`, no throw) | WIRED |
| `preload/index.ts:42-43` | `ipc.ts:111-112` | `ipcRenderer.invoke("updates:check" \| "updates:install")` — **cero payload** | WIRED |
| `ipc.ts:111-112` | `updater.ts` | `checkForUpdate()` / `downloadAndInstallUpdate()` | WIRED |
| `updater.ts:60` | `sidecar.ts` `killSidecar()` | Se **reusa** la misma función del `before-quit` (idempotente) **antes** de `quitAndInstall(true,true)` — D-05 | WIRED |
| `updater.ts` | GitHub Releases | `resources/app-update.yml` (electron-builder lo mete desde `publish:`); el módulo **no** configura feed — T-05-04 | WIRED |
| `electron-builder.yml extraResources` | `resolveSidecarExe()` (sidecar.ts:35-39) | `resources/nyanko-api/nyanko-api.exe` — el layout lo **dicta el código**, no se elige | WIRED |
| `electron-builder.yml extraResources` | `main.py:extension_bundle` | `Path(sys.executable).parent / "extension"` → los bundles van **al lado del exe**, no en `resources/extension/` | WIRED |
| `index.ts:40` / `tray.ts:73` | `resources/icon.png` | `iconPath(app.isPackaged, process.resourcesPath, __dirname)` | WIRED |
| `installer.nsh customInit` | Uninstaller de Tauri 0.1.15 | `HKCU\…\Uninstall\Nyanko` → `ExecWait '"$0" /S _?=$1'` + `Delete`/`RMDir /r` | WIRED |
| `publish-bridge.mjs` | `latest.json` del release | Firma minisign verificada **antes** de subir; URL por tag | WIRED |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|---|---|---|---|---|
| Tarjeta «Acerca de» | `updateState` (`idle\|checking\|none\|downloading\|error`) | `native.checkForUpdates()` → IPC → `autoUpdater.checkForUpdates()` → **red** | Sí — la 0.2.0 migrada mostró «Nyanko está al día» contra el release real, y la 0.2.0 mostró la 0.2.1 disponible | ✓ FLOWING |
| `updater.ts` | `updateAvailable` | Solo lo pone un `checkForUpdate()` positivo; `installUpdate` **rechaza** sin él | Sí (guarda T-05-05: un renderer comprometido, como mucho, reinstala un update legítimo ya verificado) | ✓ FLOWING |
| `latest.yml` (feed) | `sha512` / `size` | Generado **por construcción** por electron-builder | Sí — `size` = 131.201.778 = tamaño del asset publicado (comprobado contra la API) | ✓ FLOWING |
| `latest.json` (puente) | `signature` / `url` | `publish-bridge.mjs` (minisign + tag) | Sí — key id `d4f6287094b6caba` = el horneado en 0.1.15; url por tag, resuelve 200 | ✓ FLOWING |
| Icono (ventana + bandeja) | ruta del PNG | `iconPath()` → `resources/icon.png` (33.841 B) | Sí — mismo fichero que `build/icon.png`; confirmado visualmente en el NSIS instalado | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|---|---|---|---|
| El helper del icono resuelve ambas ramas | `npm run test:datadir` | 5/5 pass | ✓ PASS |
| La frontera nativa sigue simétrica con 19 ops | `npm run test:native` | 2/2 pass | ✓ PASS |
| El puente firma/verifica/rechaza | `npm run test:publish` | 5/5 pass (acepta la firma buena; rechaza payload alterado en 1 byte; rechaza firma de otra clave) | ✓ PASS |
| Typecheck del workspace | `npm run check` | exit 0 | ✓ PASS |
| El updater está DENTRO del asar empaquetado | `asar.extractFile(app.asar, out/main/index.js)` | `autoUpdater` ×7, `killSidecar` ×5, `quitAndInstall` ×1, `updates:check`/`updates:install` ×1; **`"Actualizaciones: Fase 5"` ausente** | ✓ PASS |
| El preload expone los canales del updater | `asar.extractFile(app.asar, out/preload/index.cjs)` | `updates:check` ×1, `updates:install` ×1 | ✓ PASS |
| El asar no lleva dotfiles de desarrollo | `asar.listPackage()` (1.763 entradas) | 0 coincidencias `.claude` / `.env` | ✓ PASS |
| Feed de electron-updater vivo (anónimo) | `curl -sL releases/latest/download/latest.yml` | `version: 0.2.3`, `size: 131201778` = tamaño del asset publicado | ✓ PASS |
| Feed del puente Tauri vivo (anónimo) | `curl -sL releases/latest/download/latest.json` | 200; url **por tag**; key id de la firma = `d4f6287094b6caba` = `EMBEDDED_PUBKEY_B64` | ✓ PASS |
| Layout de recursos en el paquete | `ls release/win-unpacked/resources/` | `nyanko-api/{nyanko-api.exe,_internal,extension/{chromium,firefox}}`, `icon.png`, `app-update.yml`, `app.asar` | ✓ PASS |
| **Releases 0.2.1 y 0.2.2 publicados** (claim del 05-06) | `GET /releases/tags/v0.2.1` y `/v0.2.2` | **404** — solo existen los **tags**; los releases **no** | ✗ FAIL (documental — ver hallazgos) |
| Asistente NSIS: selector ES/EN + EULA | búsqueda literal del EULA y de «Installer Language» en el `.exe` (ASCII + UTF-16) | 0 aciertos — **payload comprimido en sólido** | ? SKIP → human_verification |
| SHA512 del binario publicado, byte a byte | descarga de 131 MB | No re-descargado en esta verificación | ? SKIP — **ya ejercitado por el propio electron-updater** durante el update real (05-06) y por descarga anónima en 05-04/05-06 |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|---|---|---|---|---|
| **PKG-01** | 05-01, 05-03, 05-04, 05-05 | NSIS (ES/EN, EULA) con sidecar + extensión como recursos | ✓ SATISFIED | `electron-builder.yml` + `installer.nsh` + layout verificado en el paquete + instalador ejecutado 3 veces. **Única mitad sin observar:** las páginas de idioma/EULA del asistente (ítem 2) |
| **PKG-02** | 05-02, 05-04, 05-06 | electron-updater detecta/descarga (SHA512)/instala parando el sidecar | ✓ SATISFIED | **Ejecutado sobre una instalación real** con gate humano: 0.2.0 → 0.2.1, descarga diferencial 766 KB/128 MB, SHA512 OK, `killSidecar()` → `quitAndInstall(true,true)`, sin asistente, relanzado solo |
| DATA-01 (Fase 1, re-ejercitado aquí) | 05-03, 05-04, 05-06 | La biblioteca sobrevive a la migración y al auto-update | ✓ SATISFIED | md5/tamaño idénticos tras la desinstalación de Tauri; `integrity_check: ok` + conteos por tabla idénticos al backup tras D-01; biblioteca intacta tras el auto-update |
| SHELL-02 (Fase 3, regresión) | 05-01, 05-04 | El repo no depende de Rust/Tauri para buildear | ✓ SATISFIED | `src-tauri` ausente; cero `@tauri-apps/*` en los `package.json` (el puente usa `npx` con versión pineada); `build_sidecar.py` ya no resucita `src-tauri/` |

**Orphaned requirements:** ninguno. `REQUIREMENTS.md` mapea exactamente PKG-01 y PKG-02 a la Fase 5, y los planes los reclaman todos.

### Anti-Patterns / Hallazgos

| File / Ítem | Pattern | Severity | Impact |
|---|---|---|---|
| **GitHub Releases** | **v0.2.1 y v0.2.2 ya NO existen** (`/releases/tags/v0.2.1` → **404**, `/v0.2.2` → **404**; sus assets → 404). Solo quedan los **tags** de git. El 05-06-SUMMARY y STATE.md afirman «Releases publicados: v0.2.0, v0.2.1, v0.2.2, v0.2.3» | ⚠️ Warning | **No rompe nada funcionalmente**: el canal vivo es `releases/latest` → **v0.2.3**, con sus cinco artefactos y ambos feeds verificados contra la red; una 0.2.0 instalada hoy encuentra la 0.2.3 y se actualiza igual (los fixes de 0.2.2/0.2.3 van dentro). Pero **la afirmación documental es falsa hoy** y la evidencia del salto 0.2.0 → 0.2.1 **no es re-reproducible** desde el conjunto de releases actual (los `.exe`/`.sig`/`.blockmap` de 0.2.1 y 0.2.2 sí siguen en `apps/desktop/release/` en disco). Si los releases se borraron a propósito por limpieza, **anótalo**; si no, se perdieron sin dejar rastro |
| `docs/extra/RELEASING.md` | Existe en disco pero **no está trackeado** (`docs/extra/` gitignorado, nunca trackeado) | ⚠️ Warning | El runbook de release —que documenta la trampa de los **dos borradores paralelos** y la forma `--password=`— vive **solo en el disco del autor**. Quien clone el repo no lo hereda. Es una decisión preexistente del repo (misma que con `.gitignore`), pero el coste ahora es mayor: la fase descubrió hechos operativos caros que solo están ahí |
| `.gitignore` línea `apps/desktop/release/` | Añadida en disco, **no commiteada** (el `.gitignore` se ignora a sí mismo) | ℹ️ Info | Quien clone el repo no hereda la exclusión → un `npm run build` le deja 131 MB × N sin ignorar |
| STATE.md → Deferred Items | Lista **D-I-02** como *Deferred*, pero `deferred-items.md` lo da por **resuelto** en 0.3 (quick 260712-q62) y el código lo confirma | ℹ️ Info | Drift documental; cero impacto funcional |
| Marcadores de deuda (`TBD`/`FIXME`/`XXX`/`HACK`) | Búsqueda sobre los 10 ficheros tocados por la fase | — | **Ninguno.** Cero marcadores sin referencia a trabajo formal |
| Stubs en la frontera nativa | `grep -c 'throw new Error' src/native.ts` | — | **0.** La fase *elimina* el último stub que dejó la Fase 3 |

### Human Verification Required

**1 ítem — cosmético, NO bloqueante.**

1. **Asistente NSIS: selector de idioma + EULA.** Ejecutar `Nyanko-Setup-0.2.3.exe` a doble click
   (**sin** `/S`) en una máquina limpia y mirar las dos primeras páginas.
   - **Esperado:** diálogo «Installer Language» (Español / English) y a continuación la página de
     licencia con el texto bilingüe de `build/EULA.txt`.
   - **Por qué humano:** el NSIS comprime su payload en sólido — ni el EULA ni la tabla de idiomas
     son greppables en el `.exe` (0 aciertos en ASCII y UTF-16 sobre 131 MB). La config está presente
     y el instalador compila, pero **las tres instalaciones de la fase no pudieron observar esas
     páginas**: 05-03 fue `/S`, 05-04 la lanzó el updater de Tauri (el ejecutor observó que saltaba
     directo a la página final) y el gate de 05-02 preguntó por icono/biblioteca/updater, no por el
     asistente.
   - **Por qué NO bloquea:** que el instalador **corre e instala** está probado tres veces sobre la
     máquina real, y el EULA es una página **nueva** respecto a 0.1.15 (el NSIS de Tauri nunca tuvo
     `licenseFile`) → ni siquiera es un requisito de paridad.

### Gaps Summary

**Ninguna brecha bloqueante. El objetivo de la fase está conseguido y ejecutado, no solo escrito.**

Los tres criterios de éxito del ROADMAP se cumplen: el instalador NSIS existe, corre e instala (3
ejecuciones reales); el paquete lleva el sidecar y ambos bundles de extensión **exactamente donde el
código ya existente los busca** (`resources/nyanko-api/…`, no en el sitio "obvio" que habría matado
`/api/extension/bundle` en silencio); y el auto-update se ejercitó de punta a punta sobre una
instalación real —detectar, descargar diferencialmente, verificar SHA512, matar el sidecar,
reinstalar sin asistente y relanzarse— con gate humano. El puente D-01 también: una 0.1.15 real
aterrizó sola en 0.2.0 verificando la firma minisign.

**El diferido que la Fase 4 pasó a la Fase 5 queda CERRADO:** `iconPath()` resuelve por
`process.resourcesPath`, el `extraResources` pone el PNG en `resources/icon.png` (33.841 B, mismo
fichero) y el humano vio el gatito en la bandeja del NSIS instalado. Ya no hay ninguna ruta literal
`build/icon.png` en `electron/`.

**Lo único abierto** es una página de asistente que nadie ha mirado (selector ES/EN + EULA). No es
código ausente: es config presente que ninguna de las tres instalaciones pudo observar, y que el
NSIS comprime de forma que no se puede verificar por grep. Se registra como ítem humano en vez de
darlo por bueno.

**Un hallazgo que las SUMMARY no reflejan:** contra la red, **los releases v0.2.1 y v0.2.2 devuelven
404** — solo quedan sus tags. El canal de update sigue intacto (`releases/latest` → v0.2.3 con los
cinco artefactos y ambos feeds verificados) y los fixes de 0.2.2/0.2.3 viven en la 0.2.3, así que
ningún usuario se queda varado. Pero el claim «los cuatro publicados» de 05-06-SUMMARY y STATE.md
**es falso hoy**, y conviene corregirlo antes de archivar el milestone.

Los dos bugs que el auto-update reveló (portadas sin puerto vivo, backfill colgado) **no son
regresiones de esta fase**: son bugs preexistentes del backend que el reinicio del sidecar —inherente
a cualquier update— se limitó a destapar. Ambos tratados: el backfill se arregló y salió como 0.2.2 +
0.2.3 (que es, además, la demostración del propio ciclo de patch que esta fase acaba de validar), y
D-I-02 se reparó en datos aquí y en diseño ya en 0.3.

---

_Verified: 2026-07-12_
_Verifier: Claude (gsd-verifier)_
