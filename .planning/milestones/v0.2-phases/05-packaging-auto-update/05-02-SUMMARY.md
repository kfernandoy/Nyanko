---
phase: 05-packaging-auto-update
plan: 02
subsystem: auto-update
tags: [electron-updater, ipc, native-boundary, pkg-02]
status: complete
human_gate: passed 2026-07-12

requires:
  - "resources/app-update.yml dentro del paquete (Plan 01 — el feed NO se configura en código)"
  - "killSidecar() en electron/main/sidecar.ts:132 (Fase 3)"
  - "isDevMode() en electron/main/sidecar.ts:23 (Fase 3)"
  - "las 5 cadenas about.* de i18n.tsx y la máquina de estados de DetectorSettingsView (vivas pero sin usar desde la Fase 3)"
provides:
  - "apps/desktop/electron/main/updater.ts — checkForUpdate() + downloadAndInstallUpdate()"
  - "canales IPC updates:check y updates:install (cero payload)"
  - "window.nyanko.checkForUpdates / installUpdate"
  - "native.installUpdate — NATIVE_OPS pasa de 18 a 19 ops"
  - "native.checkForUpdates deja de ser un throw-stub"
affects:
  - "Plan 06: prueba el camino feliz (descargar → SHA512 → matar sidecar → instalar → relanzar) cuando existan dos releases"

tech-stack:
  added: []
  patterns:
    - "El feed vive en app-update.yml dentro del paquete; ni el renderer ni el main pueden repuntarlo (T-05-04)"
    - "Guarda de módulo: installUpdate rechaza si no hubo antes un check positivo (T-05-05)"

key-files:
  created:
    - apps/desktop/electron/main/updater.ts
  modified:
    - apps/desktop/electron/main/ipc.ts
    - apps/desktop/electron/preload/index.ts
    - apps/desktop/src/native.ts
    - apps/desktop/src/vite-env.d.ts
    - apps/desktop/src/DetectorSettingsView.tsx
    - apps/desktop/electron-builder.yml

decisions:
  - "electron-updater se importa por default import + destructuring: es CJS y el named export no sobrevive al interop ESM de electron-vite"
  - "isUpdateAvailable existe en electron-updater 6.8.9 — no hizo falta el fallback por eventos que el plan contemplaba"
  - "Cero UI nueva: se reconectó la máquina de estados y las cadenas i18n que ya estaban en el árbol"
  - "El bloque files: del asar usa exclusiones NEGATIVAS (!.claude, !.env*), no una whitelist: reescribir lo que SÍ entra es lo que rompe paquetes"

metrics:
  duration: ~35 min
  completed: 2026-07-12
  tasks_completed: 3
  files_created: 1
  files_modified: 6
---

# Phase 5 Plan 02: Auto-update con electron-updater — Summary

El botón «Buscar actualizaciones» vuelve a hacer lo que hacía en 0.1.15 — check → confirmar con el
número de versión → descargar → matar el sidecar → reinstalar en silencio y relanzar — pero ahora
contra electron-updater. Cierra el último stub de la frontera nativa que dejó la Fase 3.

## Qué se construyó

**Tarea 1 — `updater.ts` + dos canales IPC.** Un módulo de 66 líneas, todo wrapper fino (sin capa
pura inventada: no hay nada que testear bajo Node plano, mismo caso que `tray.ts`). Dos exports y
nada más: `checkForUpdate(): Promise<{version} | null>` y `downloadAndInstallUpdate(): Promise<void>`.
`autoDownload = false` (la confirmación del usuario va ANTES de bajar 131 MB) y
`autoInstallOnAppQuit = false`. El `autoUpdater.logger` apunta al mismo `electron-log` que configura
`logging.ts`, así que un fallo de update aterriza en `main.log` (OBS-01) en vez de ser invisible.
Los handlers `updates:check` / `updates:install` no aceptan payload alguno.

**Tarea 2 — la frontera nativa y el flujo de «Acerca de».** El preload expone dos métodos nombrados
sin argumentos; `vite-env.d.ts` los declara; `native.ts` sustituye el `throw new Error("Actualizaciones:
Fase 5")` por el enrutado normal por `window.nyanko` (fallback web: `null`, no un throw — en un
navegador no hay updates) y añade `installUpdate` a `NATIVE_OPS` (18 → 19 ops).
`DetectorSettingsView.checkForUpdates` se reconstruyó con la MISMA forma del fuente 0.1.15
(`43b399b^`), cambiando solo el motor.

## Lo que NO se escribió

Ni una línea de UI, ni una cadena de i18n. **`git diff --stat apps/desktop/src/i18n.tsx` no reporta
nada** — las cinco cadenas (`about.upToDate`, `about.updateFound`, `about.updateInstall`,
`about.checking`, `about.downloading`) y la máquina de estados
(`idle | checking | none | downloading | error`) llevaban en el árbol desde la Fase 3, vivas y sin
usar. Este plan las reconecta. El JSX de la tarjeta no se tocó: sus etiquetas ya estaban cableadas a
esos estados.

## Las tres cosas que no son negociables

| Qué | Dónde | Por qué |
|---|---|---|
| El feed **no** está en el código | `resources/app-update.yml` (Plan 01) | T-05-04: si el origen fuese configurable desde el main o el renderer, un renderer comprometido podría apuntar el updater a un exe arbitrario. Verificado en el paquete: `provider: github, owner: kfernandoy, repo: Nyanko`. |
| `killSidecar()` antes de `quitAndInstall` | `updater.ts` → `sidecar.ts:132` | D-05: el sidecar mantiene bloqueados `_internal\*` y su propio exe; si sobrevive, el copiado del instalador falla. Se **reusa** la función del `before-quit` (es idempotente, así que su segunda llamada es un no-op). |
| `installUpdate` rechaza sin check previo | flag de módulo `updateAvailable` | T-05-05: lo máximo que consigue un renderer comprometido es reinstalar un update legítimo ya verificado (DoS menor), nunca ejecutar código. |

## Verificación (ejecutada, no asumida)

- **Tarea 1**, bloque `<automated>` del plan: `UPDATER OK` (+ `npx tsc --noEmit` → 0).
- **Tarea 2**, bloque `<automated>` del plan: `RENDERER OK`. `npm run check` → 0.
  `npm run test:native` → 2/2 (la simetría `native` ↔ `NATIVE_OPS` aguanta con las 19 ops).
- `git diff --stat apps/desktop/src/i18n.tsx` → sin salida.
- **`npm run build` construyó el instalador de verdad** (`Nyanko-Setup-0.2.0.exe`, 131.194.884 B) y
  se inspeccionó el `app.asar` resultante — no basta con que compile, tiene que estar DENTRO del
  paquete:

  | comprobación en el paquete | resultado |
  |---|---|
  | `out/main/index.js` ← `updates:check`, `updates:install`, `quitAndInstall`, `autoDownload`, `killSidecar` | presentes |
  | `out/preload/index.cjs` ← `updates:check`, `updates:install` | presentes |
  | `out/renderer/…js` ← cadenas `about.upToDate` etc. | presentes |
  | `out/renderer/…js` ← el viejo `"Actualizaciones: Fase 5"` | **0 — el stub no está en el paquete** |
  | `resources/app-update.yml` | presente |

## Lo que este plan NO prueba

**PKG-02 no se cierra aquí.** El checkpoint solo puede ejercitar la mitad «detectar»: cuando corre,
todavía no existe ningún release 0.2.0 publicado (eso es el Plan 04). El camino feliz completo
—encontrar → descargar → verificar SHA512 → matar sidecar → reinstalar → relanzar— necesita DOS
releases publicados y lo prueba el **Plan 06**. Escrito y empaquetado, sí; ejecutado, no.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Higiene/seguridad del paquete] `files:` en `electron-builder.yml`**
- **Found during:** Tarea 3 (inspección del `app.asar` del instalador construido)
- **Issue:** sin bloque `files:`, el asar empaquetaba `.claude/settings.local.json`,
  `.env.development` y el árbol de fuentes entero, en un instalador destinado a publicarse.
- **Investigación primero:** se descartó fuga de secretos (el `.env` del backend, el que tiene el
  `CLIENT_SECRET`, nunca viajó — búsqueda literal en todo `win-unpacked`, negativa).
- **Fix:** exclusiones negativas (`!.claude${/*}`, `!.env*`, `!electron-builder.yml`) sobre `**/*`.
- **Files modified:** apps/desktop/electron-builder.yml
- **Commit:** d8584e2
- **Por qué se arregló y no se difirió:** entró antes de la verificación humana, para que el humano
  validara exactamente el paquete que las waves 5-6 van a publicar. Detalle completo abajo.

Los dos `<automated>` del plan pasaron a la primera y las Tareas 1-2 se ejecutaron tal como estaban
escritas. Dos detalles menores donde la realidad fue más simple de lo que el plan contemplaba:

1. El plan preveía un posible fallback por eventos (`update-available` / `update-not-available`) "si
   `isUpdateAvailable` no existiera en la versión instalada". Existe (electron-updater 6.8.9,
   `types.d.ts:27`), así que el fallback no se escribió. Menos código, mismo comportamiento.
2. `electron-updater` es CommonJS: `import { autoUpdater } from "electron-updater"` no sobrevive al
   interop ESM. Se importa por default + destructuring, con el porqué en un comentario.

## Higiene del paquete: config de desarrollo dentro del asar (resuelto, `d8584e2`)

Al inspeccionar el `app.asar` del instalador construido apareció que, **sin bloque `files:`**,
electron-builder mete en el paquete todo lo que hay bajo `apps/desktop` — incluidos
`.claude/settings.local.json` y `.env.development`, además del árbol de fuentes entero y un `dist/`
obsoleto de la era Tauri. Un `.asar` no está cifrado: se extrae con un comando. Y las waves 5-6
publican este instalador.

**Se investigó ANTES de tocar nada, y no había fuga.** El `.env` que sí contiene el
`NYANKO_ANILIST_CLIENT_SECRET` es el del **backend**, y nunca viajó: la búsqueda del secreto
literal por todo `release/win-unpacked` no lo encuentra en ningún sitio, ni en el asar ni dentro
del sidecar de PyInstaller. Era higiene, no un incidente.

**Arreglo** (`electron-builder.yml`): exclusiones **negativas** sobre `**/*` —
`!.claude${/*}`, `!.env*`, `!electron-builder.yml`. Deliberadamente NO se reescribió la lista de lo
que SÍ entra: restructurar eso es precisamente lo que rompe paquetes.

**Re-verificado tras reconstruir:** asar limpio (ni `.claude` ni `.env`), layout de recursos intacto
(sidecar, ambos bundles de extensión, icono, `app-update.yml`) y `out\main\index.js` se sigue
extrayendo del asar con el updater dentro (8 referencias a `autoUpdater`). El arreglo entró **antes**
de la verificación humana, así que el humano validó exactamente el paquete que se va a publicar.

## Known Stubs

Ninguno. Este plan *elimina* el último stub de la frontera nativa (Fase 3).

## Tarea 3 — verificación humana: PASÓ (2026-07-12)

El humano instaló el NSIS y confirmó las tres cosas:

- **Icono de bandeja**: el gatito de Nyanko, no el genérico de Electron. Cierra el riesgo diferido
  de la Fase 4 (cableado por el Plan 05).
- **Icono de ventana**: el mismo en barra de tareas y Alt+Tab.
- **Biblioteca**: carga (el sidecar arrancó desde `resources/nyanko-api/`).
- **«Buscar actualizaciones»**: llega a GitHub y **falla con el error esperado** — no hay ningún
  release 0.2.0 publicado todavía (eso es el Plan 04). **Ese error ES la condición de aprobado**: un
  updater bien cableado tiene que salir a la red y no encontrar nada. Un «estás al día» habría sido
  un falso positivo (nunca habría llegado a la red), y el viejo «Actualizaciones: Fase 5» habría
  significado que el stub seguía vivo. No pasó ninguna de las dos.

## Self-Check: PASSED

Ficheros declarados: existen (`updater.ts` creado, los 6 modificados en el diff).
Commits declarados: existen (`1b3531e`, `58aa1aa`, `d8584e2`).
