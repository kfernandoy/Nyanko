---
phase: 05-packaging-auto-update
plan: 03
subsystem: packaging
tags: [nsis, installer, migration, tauri, data-safety]
status: complete
requires:
  - 05-01 (installer.nsh + electron-builder.yml con deleteAppDataOnUninstall:false)
  - 05-05 (icono en paquete)
provides:
  - "Macro NSIS customInit: desinstalación silenciosa de Tauri 0.1.15 antes de instalar 0.2.0"
  - "Máquina de pruebas en estado M2 (0.2.0 instalada, biblioteca intacta) — precondición de los Planes 02, 04 y 06"
  - "Resultado empírico del gate D-02 (ver abajo) — hecho sobre el parque instalado, no re-derivable sin re-hacer el experimento"
affects:
  - 05-02 (updater: parte de M2)
  - 05-04 (desinstala la 0.2.0 desde M2)
  - 05-06 (release 0.2.1: sus usuarios recorren exactamente este camino de migración)
tech-stack:
  added: []
  patterns:
    - "NSIS `_?=<dir>` para desinstalación SÍNCRONA de verdad (con remate manual Delete + RMDir /r)"
    - "Des-entrecomillado de valores de registro antes de usarlos como ruta"
key-files:
  created: []
  modified:
    - apps/desktop/build/installer.nsh
decisions:
  - "D-02 resuelto por EXPERIMENTO: se cablea la RAMA A (desinstalar Tauri en silencio). La rama B (instalar encima, nsis.guid compartido) NO existe en el árbol."
  - "electron-builder.yml NO se toca en este plan: sin nsis.guid, electron-builder deriva su propio GUID del appId — no queremos compartir clave con Tauri, queremos que Tauri desaparezca."
metrics:
  duration: ~35 min (continuación; el experimento del gate corrió antes)
  tasks: 2
  files: 1
  completed: 2026-07-12
---

# Phase 05 Plan 03: Migración del instalador Tauri → Electron (gate D-02) Summary

Cableada la **rama A** de D-02 — `customInit` desinstala Nyanko 0.1.15 (Tauri) en silencio antes
de instalar 0.2.0 — y verificada end-to-end sobre una instalación 0.1.15 real: la biblioteca del
usuario sobrevive byte a byte y no queda ni un binario de Tauri en la máquina.

---

## EL RESULTADO DEL GATE D-02 (medido, no razonado)

Experimento ejecutado el **2026-07-12** contra la instalación Nyanko 0.1.15 real de `kfern`
(desinstalación silenciosa de verdad, no simulada). **Esto es un hecho sobre el parque instalado:
si se pierde, hay que re-hacer el experimento en la máquina de un usuario.**

| # | Pregunta del gate | Respuesta LITERAL |
|---|---|---|
| 1 | Clave + colmena | Clave **`Nyanko`** — **NO es un GUID entre llaves**. Ruta: `HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\Nyanko` |
| 2 | `UninstallString` | `"C:\Users\kfern\AppData\Local\Nyanko\uninstall.exe"` — **las comillas están DENTRO del valor del registro** |
| 3 | `InstallLocation` | `"C:\Users\kfern\AppData\Local\Nyanko"` — **también entrecomillado**. NO vacío. |
| 4 | **¿SOBREVIVIÓ `%APPDATA%\app.nyanko.desktop`?** | ## **SÍ** |

`QuietUninstallString` **no existe**. El uninstaller se llama `uninstall.exe`.

**Evidencia dura de la respuesta 4** — antes y después de `uninstall.exe /S`:
`nyanko.sqlite3` = **30.990.336 B**, md5 **`51cb246bf0207c3f3efb79abf3dfc084`**, **7.812** ficheros
en el directorio. Idéntico. El desinstalador silencioso de Tauri **no toca `%APPDATA%`**.

### → SE CABLEA LA RAMA A. LA RAMA B NO SE ESCRIBE.

Toda la rama B queda muerta y **no está en el árbol**: nada de `nsis.guid`, nada de `preInit`,
nada de `customInstall`, nada de la purga T-05-24, nada del borrado de los cinco restos T-05-25.
Existían para el mundo en el que el desinstalador era destructivo; ese mundo no es este. Escribirla
"comentada por si acaso" habría dejado una rama de borrado de datos latente en un `.nsh` — justo
lo que alguien descomenta sin contexto dentro de seis meses.

**`electron-builder.yml` NO se ha tocado.** Al no fijar `nsis.guid`, electron-builder deriva su
propio GUID del `appId` (`addaf0cf-bfbc-5cf6-8e26-a933ab4bb8bf`), que es lo correcto: no queremos
compartir clave de desinstalación con Tauri, queremos que la de Tauri desaparezca.

### Hechos empíricos adicionales del experimento (no re-descubrirlos)

- Ejecutado **sin** `_?=`, el uninstaller **barrió su directorio de instalación por completo** y se
  llevó también **su propia clave de registro**: ni exe, ni accesos directos, ni entrada en
  Agregar/quitar programas.
- El proceso original de `uninstall.exe /S` **retornó a los 2,5 s**; a los 5 s ya no quedaba ningún
  proceso vivo. El asincronismo `%TEMP%` / `Au_.exe` es real, pero corto.
- **Exe de Tauri: `nyanko-desktop.exe`. Exe de Electron: `Nyanko.exe`. Nombres DISTINTOS** — instalar
  encima no habría pisado nada (esto es lo que destruía el mecanismo central de la rama B).
- Directorio de instalación de Tauri: `nyanko-desktop.exe` (17,9 MB), `nyanko-api.exe` (11,2 MB),
  `uninstall.exe` (81 KB), `_internal\`, `extension\`.
- La base de datos se llama **`nyanko.sqlite3`**, NO `nyanko.db` (el plan original preguntaba por un
  fichero inexistente — habría producido un falso «SOBREVIVIÓ: NO» y elegido la rama B por un
  fichero que nunca estuvo ahí).

### Por qué el `_?=` sigue siendo obligatorio aunque el barrido saliera limpio

El motivo **no es el directorio: es el acceso directo.** Tauri y electron-builder crean ambos un
`$SMPROGRAMS\Nyanko.lnk` con el MISMO nombre. Sin `_?=`, el `ExecWait` retorna en ~2,5 s mientras el
`Au_.exe` sigue borrando en segundo plano — y el instalador de Electron crearía su `.lnk` justo a
tiempo de que el uninstaller rezagado se lo llevara por delante. Con `_?=` el uninstaller corre
**en sitio y de verdad síncrono**; el precio es que ya no se autoborra ni borra su directorio, así
que la rama A remata a mano con `Delete "$0"` + `RMDir /r "$1"`. Ambas cosas están cableadas.

---

## What Was Built

`apps/desktop/build/installer.nsh` — una macro nueva, **`customInit`** (commit `1c87d00`):

1. `ReadRegStr` de `UninstallString` e `InstallLocation` en `HKCU\...\Uninstall\Nyanko` — la clave
   **literal** que reportó el gate, no un GUID inventado.
2. **Des-entrecomillado** (`!macro NyankoUnquote`): Tauri guarda las comillas *dentro* del dato del
   registro; un `ExecWait` con el valor crudo produce una "ruta" con comillas literales, que no es
   una ruta.
3. **Guarda `StrCmp` contra vacío** (T-05-10): un usuario nuevo, sin Tauri instalado, no puede
   comerse un `ExecWait` de una ruta vacía. Se guarda contra ambos valores.
4. `ExecWait '"$0" /S _?=$1'` — desinstalación síncrona real. Se continúa pase lo que pase: un
   uninstaller que falle no puede abortar la instalación de la versión nueva.
5. Remate `Delete "$0"` + `RMDir /r "$1"` — obligatorio por el `_?=`.
6. Un comentario largo en español que cita **D-02**, el resultado del experimento con su fecha,
   **DATA-01**, y **por qué está el `_?=`**. Ese comentario es la única defensa contra que un lector
   futuro lo "simplifique" a un `ExecWait` pelado y reintroduzca la carrera del acceso directo.

El `taskkill` del sidecar del Plan 01 sigue **intacto** en `customCheckAppRunning` (D-05 / T-05-05):
no se ha "normalizado" a `customInit`. Las dos macros coexisten y el orden resultante es el correcto
— `customInit` se lleva la 0.1.15 al arrancar el instalador; `customCheckAppRunning` mata cualquier
sidecar respawneado justo antes de copiar.

## Verificación

### Check automático del plan
```
GATE D-02 CABLEADO: rama A (uninstall silencioso, _?= + remate)
```
(taskkill del Plan 01 presente · `deleteAppDataOnUninstall: false` presente · exactamente UNA rama
cableada · guarda `StrCmp` · parámetro `_?=` · remate `RMDir` · comentario que cita D-02)

### Build
`npm run build` desde la raíz → `apps/desktop/release/Nyanko-Setup-0.2.0.exe`. NSIS compiló
`customInit` sin errores de sintaxis. (Sin sesiones `npm run dev` vivas: el watcher de chokidar
mantiene handles abiertos que hacen fallar el rename de `win-unpacked.tmp` con un `EPERM` opaco.)

### E2E sobre instalación real (M1 → M2)

`Nyanko-Setup-0.2.0.exe /S` ejecutado sobre la 0.1.15 real. Exit code 0. Ningún proceso de
desinstalación vivo a los 8 s.

| Criterio | Resultado |
|---|---|
| **1. Biblioteca intacta (DATA-01)** | `nyanko.sqlite3` = **30.990.336 B**, md5 **`51CB246BF0207C3F3EFB79ABF3DFC084`**, **7.812** ficheros. **Idéntico** al pre-instalación. |
| **2. Sin restos de Tauri** | `C:\Users\kfern\AppData\Local\Nyanko` **ya no existe** (`RMDir /r` lo barrió). Los cinco restos comprobados uno a uno: `nyanko-desktop.exe`, `uninstall.exe`, `nyanko-api.exe`, `_internal\`, `extension\` — **todos ausentes**. Ningún ejecutable de Tauri lanzable en la máquina. |
| **3. Agregar/quitar programas** | **UNA sola entrada**: `Nyanko 0.2.0` (clave `addaf0cf-bfbc-5cf6-8e26-a933ab4bb8bf`, HKCU). La entrada `Nyanko` de Tauri desapareció con su propio uninstaller. Ninguna en HKLM. |
| **4. Accesos directos** | Menú Inicio y Escritorio → ambos apuntan a `C:\Users\kfern\AppData\Local\Programs\Nyanko\Nyanko.exe`, que existe y reporta **ProductVersion 0.2.0.0**. **Ninguno se perdió en la carrera** — que es exactamente lo que protege el `_?=`. |

### Verificación humana: **PASÓ** (2026-07-12)

Criterio e2e 2 del plan, el único no automatizable. El usuario abrió Nyanko 0.2.0 desde el acceso
directo y confirmó:

- **La biblioteca renderiza** con su contenido real. La DB no solo sobrevivió byte a byte: la 0.2.0
  la lee y la pinta. DATA-01 cerrado de extremo a extremo.
- **El icono sale en la bandeja del sistema.**

**El icono cierra además el hueco que el Plan 05-05 dejó abierto a propósito.** Aquel plan cableó
`iconPath()` para resolver vía `process.resourcesPath` cuando la app está empaquetada, pero su
propio SUMMARY dejó constancia de que esa rama **no era verificable desde el plan**: en dev
`app.isPackaged` es `false`, así que la rama empaquetada nunca se ejecutaba y solo tenía un
self-check unitario detrás. Aquí se ha ejecutado por primera vez en una instalación de verdad —
icono visible en bandeja = `resources/icon.png` existe en el sitio que `iconPath()` calcula. 05-05
queda validado en producción, no solo en test.

## Deviations from Plan

Ninguna. El gate seleccionó la rama A y se cableó la rama A, con las tres correcciones que los
hechos medidos ya habían forzado sobre el plan (clave `Nyanko` en vez de GUID, valores
entrecomillados, `nyanko.sqlite3` en vez de `nyanko.db`).

Detalle de implementación menor: el `Delete` del uninstaller usa `"$0"` (la ruta completa ya
des-entrecomillada que salió del `UninstallString`) en lugar de reconstruir
`"$1\uninstall.exe"`. Mismo efecto, sin hardcodear el nombre del fichero.

## Estado de la máquina

**M2** — Nyanko 0.2.0 instalada en `C:\Users\kfern\AppData\Local\Programs\Nyanko`, biblioteca
intacta, sin restos de Tauri. Es la precondición de la que parten los checkpoints de los Planes 02,
04 y 06. Backup de la biblioteca en `C:\Users\kfern\Desktop\nyanko-backup-05-03` (no se ha
necesitado).

## Self-Check: PASSED

- `apps/desktop/build/installer.nsh` — existe, contiene `customInit` con `_?=` y `RMDir`
- commit `1c87d00` — existe en el árbol
