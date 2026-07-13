---
phase: 05-packaging-auto-update
plan: 01
subsystem: packaging
tags: [electron-builder, nsis, packaging, windows, sidecar, extension]
status: complete

requires:
  - "apps/backend/dist/nyanko-api/ (PyInstaller onedir, producido por build:sidecar)"
  - "apps/extension/dist/{chromium,firefox} (producido por build:extension)"
  - "resolveSidecarExe() en electron/main/sidecar.ts (Fase 3)"
provides:
  - "apps/desktop/electron-builder.yml — config de empaquetado NSIS"
  - "apps/desktop/release/Nyanko-Setup-0.2.0.exe — instalador NSIS asistido, per-user"
  - "apps/desktop/release/latest.yml — feed de auto-update (SHA512 + size por construcción)"
  - "resources/app-update.yml dentro del paquete — PRECONDICIÓN del updater del Plan 02"
  - "script npm `dist` en @nyanko/desktop (electron-vite build && electron-builder --publish never)"
affects:
  - "Plan 02 (updater): consume resources/app-update.yml y latest.yml"
  - "Plan 03 (gate de desinstalación): añadirá la rama D-02 a build/installer.nsh"
  - "Plan 04 (puente de release): consume el bloque publish: y el .exe"

tech-stack:
  added:
    - "electron-builder ^26.0.12 (devDependency)"
    - "electron-updater ^6.6.2 (dependency — RUNTIME, va dentro del asar)"
  patterns:
    - "El layout de recursos lo DICTA el código existente, no se elige"
    - "Config de empaquetado en YAML aparte, no inline en package.json"

key-files:
  created:
    - apps/desktop/electron-builder.yml
    - apps/desktop/build/installer.nsh
    - apps/desktop/build/EULA.txt (restaurado de a50659c^)
  modified:
    - apps/desktop/package.json
    - package.json
    - apps/backend/scripts/build_sidecar.py
    - .gitignore (en disco; el fichero no está trackeado)

decisions:
  - "electron pineado a 43.1.0 EXACTO: electron-builder no resuelve un rango bajo npm workspaces"
  - "taskkill en customCheckAppRunning, NO customInit (T-05-05)"
  - "build:icons ELIMINADO en vez de reparado (estaba roto; icon.png ya está commiteado)"
  - "--publish never en el script dist: publicar es el Plan 04 (D-08)"

metrics:
  duration: ~55 min
  completed: 2026-07-12
  tasks_completed: 3
  files_created: 3
  files_modified: 4
---

# Phase 5 Plan 01: Empaquetado NSIS con electron-builder — Summary

`npm run build` produce ahora un instalador NSIS real (`Nyanko-Setup-0.2.0.exe`, 131 MB) con el
sidecar Python y los bundles de extensión colocados exactamente donde el código ya existente los
busca — sin invocar nada de Tauri.

## Qué se construyó

**Tarea 1 (checkpoint):** gate de legitimidad de paquetes T-05-SC. El humano verificó
`electron-builder` y `electron-updater` en npmjs.com y respondió `approved`. Sin ese gate no se
ejecutó ningún `npm install`.

**Tarea 2 — cadena de build Rust-free.** Versión a `0.2.0` (semver estricto). `electron-updater`
en `dependencies` (runtime: tiene que estar fuera de devDeps o el asar no lo lleva),
`electron-builder` en `devDependencies`. Nuevo script `dist`. El `build` de la raíz pasa a ser
`build:extension → build:sidecar → dist`: se eliminan el paso `build:icons` (roto) y las dos
llamadas al CLI de Tauri (`build` y `dev:desktop`). En `build_sidecar.py` se borra la cola Tauri
(`rust_target_triple()`, `binary_dir`, la copia a `src-tauri/binaries/` y el `--icon` muerto) —
ese `binary_dir.mkdir(parents=True)` **resucitaba el directorio `src-tauri/` borrado en cada build
del sidecar**. Verificado: tras `npm run build:sidecar`, `apps/desktop/src-tauri/` no reaparece.

**Tarea 3 — config de empaquetado.** `electron-builder.yml` con `appId: app.nyanko.desktop`
(load-bearing: mantiene `userData` en `%APPDATA%\app.nyanko.desktop`; cambiarlo dejaría huérfana
la biblioteca de todos los usuarios de 0.1.15), NSIS asistido y per-user, selector de idioma
ES/EN, EULA cableado, y `deleteAppDataOnUninstall: false` explícito (DATA-01). El EULA se restauró
**byte-idéntico** de `a50659c^` (74 líneas, bilingüe). El hook `installer.nsh` porta el `taskkill`
del sidecar.

## El layout de recursos no se elige — lo dicta el código

Es lo único de este plan que no es negociable:

| Recurso | Destino | Por qué ahí |
|---|---|---|
| sidecar | `resources/nyanko-api/nyanko-api.exe` | `resolveSidecarExe()` (sidecar.ts:35-39) lo exige |
| extensión | `resources/nyanko-api/extension/{chromium,firefox}` | `main.py:extension_bundle` resuelve `Path(sys.executable).parent / "extension"` |

Poner la extensión en el sitio "obvio" (`resources/extension/`, calcado de Tauri) haría que
`/api/extension/bundle` devolviera nulls y el botón "abrir carpeta de la extensión" muriera en
producción **sin ningún error visible**. El empaquetado se adapta al código; el sidecar Python no
se tocó (0.2 = engine-swap puro).

## Verificación (ejecutada, no asumida)

- **Tarea 2** — el bloque `<automated>` del plan: `OK`. Además: `src-tauri` ausente de
  `build_sidecar.py`; tras `npm run build:sidecar` el directorio `src-tauri/` NO se recrea y
  `apps/backend/dist/nyanko-api/nyanko-api.exe` existe; `require.resolve('electron-updater')`
  resuelve desde `apps/desktop`.
- **Tarea 3** — el bloque `<automated>` del plan: `LAYOUT OK` (instalador + `latest.yml` +
  `app-update.yml` + sidecar + `_internal/` + ambos `manifest.json` + `icon.png` + `app.asar`, y
  **NO** existe `resources/extension/`).
- `CONFIG OK`: `appId`, `deleteAppDataOnUninstall: false`, `oneClick: false`, `perMachine: false`.
- EULA byte-idéntico a `a50659c^` (`diff` sin salida).
- `installer.nsh` define **solo** `!macro customCheckAppRunning` (no hay `!macro customInit`).
- Artefactos reales: `Nyanko-Setup-0.2.0.exe` (131.192.874 B), `latest.yml` (con SHA512 y size),
  `.blockmap`, `win-unpacked/`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] electron pineado a versión exacta**
- **Found during:** Tarea 3 (primer `npm run build`)
- **Issue:** electron-builder aborta con *"Electron version `^43.1.0` is a range, not a fixed
  version"*. Bajo npm workspaces, electron está hoisteado a la raíz y electron-builder (cuyo
  `projectDir` es `apps/desktop`) no lo encuentra para resolver el rango.
- **Fix:** `"electron": "43.1.0"` (sin caret) en `apps/desktop/devDependencies` — es la primera
  remediación que sugiere el propio error. Se descartó duplicar la versión en `electronVersion:`
  dentro del `.yml`: sería una segunda fuente de verdad que se desincroniza al actualizar.
- **Files modified:** apps/desktop/package.json
- **Commit:** 361e771

**2. [Rule 3 - Blocking] Sesión de `npm run dev` viva bloqueaba el empaquetado**
- **Found during:** Tarea 3 (`npm run build`, EPERM reproducible)
- **Issue:** electron-builder extrae Electron en `release/win-unpacked.tmp` y lo renombra a
  `release/win-unpacked` (`electronGet.js:187`). El rename fallaba con `EPERM: operation not
  permitted` **de forma reproducible**, y el directorio seguía sin poder renombrarse ni siquiera
  a mano diez minutos después.
- **Diagnóstico** (el síntoma es contraintuitivo, así que se acotó por bisección):

  | prueba | subdirs | rename |
  |---|---|---|
  | dir vacío bajo `release/` | 0 | OK |
  | dir con 2 ejecutables sueltos | 0 | OK |
  | copia completa del dist de Electron | 3 | **DENEGADO** |
  | esa misma copia en `C:\` | 3 | OK |

  El dir se podía **borrar** pero no **renombrar** → no era permisos ni ACL ni un lock de CWD, y
  se reproducía **sin electron-builder de por medio** (un `cp -r` bastaba). La causa: había una
  sesión `npm run dev` viva (PID 25588 = `electron-vite dev` + 4 `electron.exe`). Su watcher
  recursivo (chokidar) abre un handle **por cada subdirectorio** que descubre bajo
  `apps/desktop/`, incluidos los recién creados en `release/`. En Windows, un directorio cuyos
  subdirectorios están abiertos por otro proceso **no se puede renombrar** (pero sí borrar, y sus
  ficheros sí se pueden manipular) — que es exactamente el patrón observado.
- **Fix:** matar el árbol de la sesión de dev y reconstruir. El build pasó a la primera.
- **Files modified:** ninguno (problema de entorno, no de config)
- **Commit:** n/a

**3. [Rule 1 - Bug] Comentario que rompía su propio criterio de aceptación**
- **Found during:** Tarea 2
- **Issue:** el criterio de aceptación es un check de subcadena literal
  (`'src-tauri' not in src`). El comentario que escribí para explicar *por qué* se borró la cola
  contenía la subcadena `src-tauri/binaries/`, y hacía fallar el check.
- **Fix:** reformulado a "el directorio de binarios del crate Rust borrado" — conserva el
  razonamiento (que es lo que impide que un lector futuro reintroduzca la cola) y satisface el
  check.
- **Files modified:** apps/backend/scripts/build_sidecar.py
- **Commit:** 4fdbaf1

## Notas operativas (importan para los Planes 02-06)

1. **Empaquetar exige que NO haya una sesión de dev corriendo.** El watcher de `electron-vite dev`
   bloquea el rename de `win-unpacked.tmp` y el fallo (`EPERM`) no dice nada de esto. Es la misma
   clase de problema que el proyecto ya documentó con los `dev.py` duplicados. Si un `npm run
   build` futuro da EPERM: cerrar el dev y reintentar. (La sesión que había se mató; se relanza
   con `npm run dev`.)
2. **`.gitignore` no está trackeado** (se ignora a sí mismo en su línea 1). La línea
   `apps/desktop/release/` está añadida en disco y funciona, pero **no se commiteó** — no se forzó
   con `git add -f` por respetar esa decisión preexistente del repo. Quien clone el repo no
   heredará esa línea.
3. El instalador **no está firmado** (T-05-03, aceptado): SmartScreen mostrará el aviso azul.
4. La página del EULA es **nueva** respecto a 0.1.15 (el NSIS de Tauri nunca tuvo `licenseFile`,
   pese a lo que dice CONTEXT.md). Refuerza la expectativa de UX de D-01 en el Plan 04.

## Known Stubs

Ninguno. Todo lo que este plan promete está construido y verificado contra artefactos reales.

## Self-Check: PASSED

Ficheros declarados: existen. Commits declarados: existen.
