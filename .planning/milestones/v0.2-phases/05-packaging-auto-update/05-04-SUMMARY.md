---
phase: 05-packaging-auto-update
plan: 04
subsystem: release
tags: [release, minisign, updater, github-releases, d-01, pkg-01, pkg-02]
status: complete
human_gate: approved 2026-07-12

requires:
  - "05-01 (electron-builder.yml + bloque publish: + latest.yml por construcción)"
  - "05-02 (electron-updater cableado, asar limpio)"
  - "05-03 (customInit rama A: desinstala Tauri 0.1.15 en silencio)"
  - "05-05 (icono empaquetado)"
provides:
  - "Release v0.2.0 PUBLICADO en kfernandoy/Nyanko con los CUATRO artefactos"
  - "apps/desktop/scripts/publish-bridge.mjs — firma minisign, VERIFICA y publica el puente D-01"
  - "scripts npm dist:publish (--publish always) y test:publish"
  - "docs/extra/RELEASING.md reescrito para el flujo Electron (fichero NO trackeado: docs/extra/ está gitignorado)"
  - "Prueba empírica de D-01: una instalación 0.1.15 real aterrizó en 0.2.0 sola"
  - "Máquina en estado M2 — precondición del Plan 06"
affects:
  - "05-06: publica el SEGUNDO release (0.2.1) y cierra el camino feliz de PKG-02"

tech-stack:
  added: []
  patterns:
    - "El ancla de confianza va LITERAL en el script (EMBEDDED_PUBKEY_B64), no se lee del disco"
    - "Verificar la firma recién creada ANTES de subir nada — una firma mala es indistinguible de una buena"
    - "@tauri-apps/cli se invoca por npx con versión PINEADA; NO vuelve a package.json (SHELL-02)"

key-files:
  created:
    - apps/desktop/scripts/publish-bridge.mjs
    - apps/desktop/scripts/publish-bridge.test.mjs
  modified:
    - apps/desktop/package.json
    - docs/extra/RELEASING.md (en disco; gitignorado, nunca ha estado trackeado)

decisions:
  - "La url de latest.json NO puede salir del browser_download_url de un BORRADOR: es provisional (untagged-<hash>) y muere en 404 al publicar. Se compone del tag + el nombre del asset firmado."
  - "El puente exige que exactamente UN release lleve el tag: GitHub permite varios borradores con el mismo tag_name."
  - "docs/extra/ está gitignorado y nunca ha estado trackeado (como el propio .gitignore). RELEASING.md se actualiza en disco y NO se fuerza a git — misma decisión que tomó el Plan 01."

metrics:
  duration: ~75 min
  completed: 2026-07-12
  tasks_completed: 3
  files_created: 2
  files_modified: 2
---

# Phase 5 Plan 04: Publicar 0.2.0 + el puente a los 0.1.15 — Summary

Nyanko 0.2.0 está **publicado** con los cuatro artefactos, y una instalación Tauri 0.1.15 real
aterrizó sola en Electron 0.2.0 con la biblioteca intacta. D-01 no es una teoría: se ejecutó.

Por el camino, el puente estuvo **a un paso de publicar un enlace muerto** que habría varado a
todo el parque instalado sin un solo error visible. Esa es la lección cara de esta fase y está
documentada abajo.

---

## El release

https://github.com/kfernandoy/Nyanko/releases/tag/v0.2.0 — **publicado, no borrador**.

| Asset | Tamaño | Lo lee |
|---|---|---|
| `Nyanko-Setup-0.2.0.exe` | 131.199.882 B | ambos |
| `latest.yml` | 341 B | electron-updater (0.2.0+) |
| `Nyanko-Setup-0.2.0.exe.sig` | 412 B | updater Tauri (0.1.15) |
| `latest.json` | 1.228 B | updater Tauri (0.1.15) |
| `.blockmap` | 137.107 B | electron-updater (deltas) |

**Verificado descargando el binario publicado** (no el local) desde la URL que el propio feed
anuncia, sin token, como un cliente cualquiera:

- la firma minisign publicada **verifica** contra la pubkey horneada en 0.1.15 (`d4f6287094b6caba`);
- el `sha512` de `latest.yml` **coincide** con el hash de esos mismos bytes, y el `size` también;
- ambos feeds resuelven por `releases/latest/download/…` → HTTP 200.

---

## LOS DOS BUGS SILENCIOSOS (la parte que importa)

### 1. `latest.json` apuntaba a la URL provisional del borrador — T-05-12

El plan decía, con razón, «la `url` sale del `browser_download_url` que devuelve la API, no se
compone a mano». Lo que nadie sabía es que **en un BORRADOR ese campo es provisional**:

```
https://github.com/kfernandoy/Nyanko/releases/download/untagged-b9323463998e19ba7b84/Nyanko-Setup-0.2.0.exe
```

El tag no existe de verdad hasta publicar. **En cuanto se publica el release, los assets pasan a
servirse bajo su tag y esa URL `untagged-…` muere con un 404.**

Habríamos publicado un puente **correctamente firmado apuntando a un enlace muerto**: la firma
válida, el `latest.json` bien formado, el release completo — y **ningún 0.1.15 se habría
actualizado jamás**, sin un solo error visible ni para el usuario ni para nosotros. Exactamente la
clase de fallo que T-05-12 describe y que la fase entera existe para evitar.

Se cazó porque el script **imprime la URL que va a publicar** y la URL tenía un aspecto raro.

**Arreglo:** si el release es borrador, la URL se compone del **tag** + el **nombre del asset que
la API devolvió para el fichero que acabamos de firmar** (el nombre no se inventa: sale del asset
real). Es la URL que el release servirá una vez publicado, y se verificó a posteriori
descargándola.

### 2. Dos borradores compartiendo el tag `v0.2.0`

GitHub **permite varios borradores con el mismo `tag_name`** (el tag no es real hasta publicar). El
primer `--publish always` falló a medias (subió el `.blockmap` y nada más) y dejó un borrador
huérfano; el reintento creó un segundo. El puente hacía `releases.find(...)` y se quedaba con **el
primero** — una tirada de dados sobre a cuál de los dos le sube la firma.

**Arreglo:** el script exige que haya **exactamente uno** y aborta enumerando los ids si hay más.
El borrador huérfano se borró antes de firmar.

### 3. (menor) El firmador se comía la ruta del `.exe`

`npx` es un `.cmd` y Node se niega a lanzarlo sin `shell: true` (CVE-2024-27980). Con shell, un
argumento **vacío** (`--password`, `""`) desaparece al reconstruir la línea de comandos, y el
firmador tomaba la ruta del `.exe` como contraseña → «required argument `<FILE>` not provided».
La forma `--password=` mantiene el token entero — **la misma que ya documentaba el RELEASING.md de
la era Tauri**, que estaba ahí desde el principio.

**Las guardas funcionaron:** cuando el firmador falló, el script **abortó sin subir nada**. No hubo
que limpiar un release a medio firmar.

---

## D-01: la prueba, y ocurrió sola

Para probarlo hacía falta una 0.1.15 de verdad, así que se bajó la máquina de **M2 → M1**:

1. Se cerró Nyanko 0.2.0 (estaba corriendo; `WM_CLOSE` no la mata — minimiza a bandeja — así que
   force-quit con la DB en reposo).
2. **Backup fresco** de la biblioteca viva en `C:\Users\kfern\Desktop\nyanko-backup-05-04`
   (7.935 ficheros, 924 MB). El del Plan 03 era anterior al uso del usuario.
3. Desinstalada la 0.2.0. **Su desinstalador ignoró `/S` y abrió el asistente** (hecho nuevo, ver
   abajo); se clicó «Siguiente». Barrió dir, registro y accesos directos.
   **La biblioteca sobrevivió byte a byte** (`deleteAppDataOnUninstall: false`, DATA-01).
4. Instalada Nyanko 0.1.15 (Tauri) en silencio (`/S`, exit 0). Una sola entrada en Agregar/quitar.

**Y entonces, sin que nadie tocara nada:** la 0.1.15 arrancó sola, sondeó `latest.json`, encontró
0.2.0, **lo descargó, verificó la firma minisign** y ejecutó el instalador como
`Nyanko-0.2.0-installer.exe` (el nombre que le pone el updater de Tauri). El `customInit` del Plan
03 desinstaló Tauri, Electron 0.2.0 se copió, y **la app se relanzó sola**.

**Que el instalador llegara a arrancar ES la prueba de la firma:** si no verificara contra la
pubkey horneada en su binario, Tauri se habría negado a ejecutarlo. No hay forma de fingir esto.

### Estado final medido tras la migración

| Criterio | Resultado |
|---|---|
| **Biblioteca (DATA-01)** | `integrity_check: ok`, **2.761** `library_entries`, **25.727** `episodes`, 2.774 `media`, 16.128 `media_titles` — **idéntica tabla por tabla al backup** |
| Restos de Tauri | `nyanko-desktop.exe` ausente; el dir quedó **vacío** (`RMDir /r`), solo el cascarón |
| Agregar/quitar | **UNA** entrada: «Nyanko 0.2.0» |
| Accesos directos | Menú Inicio → `…\Programs\Nyanko\Nyanko.exe` (ProductVersion **0.2.0.0**) |
| Sidecar huérfano (D-05) | Ninguno. El `nyanko-api.exe` vivo es el **de la 0.2.0** (`…\Programs\Nyanko\resources\nyanko-api\`), o sea la app ya arrancada |
| Updater nuevo (paso 7) | La 0.2.0 migrada dice **«Nyanko está al día»** — visible en pantalla |

Ese último punto es el que cerró el cabo suelto del Plan 02: allí «Buscar actualizaciones» solo
podía producir un error (no existía ningún release 0.2.0). Ahora existe, coincide con la versión
instalada, y el updater lo reconoce.

### El desenlace del asistente — OBSERVACIÓN DEL EJECUTOR, no confirmada por el usuario

El plan preveía dos desenlaces, ambos aprobables: **(i)** silencioso con relanzado automático, o
**(ii)** asistente NSIS completo (idioma + EULA + directorio) sin relanzado.

**Lo observado directamente por el ejecutor fue un híbrido:** apareció una ventana de instalación,
pero **saltó sola hasta la página final** («Finalizando el Asistente… Presione Terminar», con
*Ejecutar Nyanko* marcado) — sin selector de idioma, sin EULA, sin diálogo de directorio a la
vista. Y **la app se relanzó sola**.

**Salvedad honesta:** el usuario aprobó el gate con un «approved» escueto y **no respondió a las
tres preguntas** del checkpoint (qué asistente vio, si la biblioteca renderiza, si el icono sale en
bandeja). Lo anterior es lo que el ejecutor midió y capturó, **no** algo que el usuario haya
confirmado. Lo máximo que se puede afirmar es que **no lo contradijo**.

Es un hecho sobre lo que verá el parque instalado, y **el Plan 06 lo cita** — pero conviene
tratarlo como una observación de una sola ejecución, no como una garantía.

Biblioteca e icono no dependen de esa respuesta: la biblioteca está respaldada por evidencia
objetiva propia (integridad + conteos idénticos al backup) y el **icono de bandeja lo confirmó
visualmente el humano en el checkpoint del Plan 05-02**, sobre este mismo paquete.

---

## Hechos nuevos sobre el instalador (no re-descubrirlos)

- **El desinstalador de electron-builder ignora `/S`** y abre su asistente, incluso invocado con la
  `QuietUninstallString` que el propio registro publica (`"…\Uninstall Nyanko.exe" /currentuser /S`).
  Un `Un_A.exe` se queda vivo esperando un clic. No afecta a los usuarios (nadie desinstala en el
  camino de D-01), pero **cualquier automatización futura que cuente con un uninstall silencioso va
  a colgarse ahí**.
- El uninstaller NSIS deja el **directorio vacío** tras el `RMDir /r`. Residuo inocuo.
- La md5 de `nyanko.sqlite3` **cambia con el uso** (SQLite reescribe páginas in situ; el tamaño no
  se mueve). Como invariante de «no se ha perdido la biblioteca», la md5 **solo sirve entre pasos
  en los que la app no corre**. El invariante bueno son los **conteos por tabla**.

## Verificación (ejecutada, no asumida)

- `npm run test:publish` → **5/5**: round-trip de `verifyMinisign` (acepta la firma buena; rechaza
  el payload alterado en un byte; rechaza una firma de otra clave), forma de `buildLatestJson`, y
  `EMBEDDED_PUBKEY_B64` decodifica a un `.pub` minisign de 2 líneas con key id `d4f6287094b6caba`.
- Bloque `<automated>` del plan: **`BRIDGE OK`**.
- `@tauri-apps/cli` **no aparece** en ningún `package.json` del repo (SHELL-02 sigue Completo).
- Guardas del script: todas (líneas 174-222) preceden a la primera subida (línea 229). El script no
  imprime el token ni el contenido de la clave privada en **ninguna** rama.
- `RELEASING.md`: cero referencias a `tauri.conf.json`, `Cargo.toml` o `TAURI_SIGNING_*`.

## Gate de legitimidad T-05-SC-2 — cómo se resolvió

El humano autorizó explícitamente la publicación y **nombró el paquete y la versión pineada** en el
encargo. Además se corroboró objetivamente, que es **más fuerte** que el vistazo a npmjs.com que
pedía el plan:

- `@tauri-apps/cli@^2.8.4` está **en la historia de git de este repo** (`a50659c^:apps/desktop/package.json`):
  es literalmente el toolchain con el que se firmó 0.1.15 y todos los 0.1.x que hay en el campo.
  No es un proveedor nuevo ni un nombre inventado.
- Registry: `repository.url = git+https://github.com/tauri-apps/tauri.git`, scope y tarball oficiales.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `latest.json` apuntaba a la URL `untagged-…` del borrador**
- **Found during:** Tarea 3 (publicación), leyendo la URL que el script iba a publicar
- **Issue:** el `browser_download_url` de un asset en un release BORRADOR es provisional y devuelve
  404 en cuanto el release se publica → puente firmado apuntando a un enlace muerto; todo el parque
  0.1.15 varado, en silencio (T-05-12)
- **Fix:** si `release.draft`, la URL se compone del tag + el nombre del asset firmado
- **Files modified:** apps/desktop/scripts/publish-bridge.mjs
- **Commit:** `565fe08`

**2. [Rule 1 - Bug] Varios borradores pueden compartir el mismo tag**
- **Found during:** Tarea 3 (el primer publish falló a medias y dejó un borrador huérfano)
- **Issue:** `releases.find()` cogía «el primero» — azar sobre a cuál se le sube la firma
- **Fix:** se exige exactamente un release con ese tag; aborta enumerando los ids si hay más
- **Files modified:** apps/desktop/scripts/publish-bridge.mjs
- **Commit:** `565fe08`

**3. [Rule 3 - Blocking] El argumento vacío `""` desaparecía bajo el shell**
- **Found during:** Tarea 3 (primera invocación del firmador)
- **Issue:** `npx` es un `.cmd` → `shell: true` obligatorio (CVE-2024-27980) → el arg vacío se
  evapora y el firmador toma la ruta del `.exe` como contraseña
- **Fix:** `--password=` (la forma que el RELEASING.md de la era Tauri ya documentaba) + rutas
  entrecomilladas
- **Files modified:** apps/desktop/scripts/publish-bridge.mjs
- **Commit:** `565fe08`

### Desviación de proceso

**`docs/extra/RELEASING.md` no se ha commiteado.** `docs/extra/` está en `.gitignore` (línea 9) y
**nunca ha estado trackeado** (`git log --diff-filter=A -- 'docs/extra/*'` está vacío), igual que el
propio `.gitignore`. Se ha reescrito **en disco** y no se ha forzado con `git add -f`: es la misma
decisión que tomó el Plan 01 al encontrarse con esto («no se forzó por respetar esa decisión
preexistente del repo»). Los dos scripts sí se forzaron a git — `apps/desktop/scripts/` tiene
hermanos trackeados desde el commit baseline, así que ahí el precedente es el contrario.

## Lo que este plan NO cierra

**PKG-02 sigue abierto.** Aquí el que actualizó fue el updater de **Tauri** (minisign +
`latest.json`). Del de electron-updater solo se ha ejercitado la rama «estás al día». El camino
feliz completo —encontrar → descargar → **verificar SHA512** → matar el sidecar → instalar →
relanzar— necesita un **segundo** release y lo prueba el **Plan 06** con la 0.2.1.

## Estado de la máquina

**M2** — Nyanko 0.2.0 instalada en `%LOCALAPPDATA%\Programs\Nyanko`, biblioteca intacta, sin restos
de Tauri, corriendo. Es la precondición del Plan 06. Backups: `nyanko-backup-05-04` (fresco, 7.935
ficheros) y `nyanko-backup-05-03` (del plan anterior). Ninguno hizo falta.

## Known Stubs

Ninguno.

## Self-Check: PASSED

- `apps/desktop/scripts/publish-bridge.mjs` — existe
- `apps/desktop/scripts/publish-bridge.test.mjs` — existe, 5/5 pasan
- commits `0fa0407` y `565fe08` — existen en el árbol
- release v0.2.0 — publicado, cuatro artefactos, ambos feeds verificados contra los bytes publicados
