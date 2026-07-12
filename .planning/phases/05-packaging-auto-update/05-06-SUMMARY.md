---
phase: 05-packaging-auto-update
plan: 06
subsystem: release
tags: [release, electron-updater, auto-update, sha512, differential-download, github-releases, pkg-02]
status: complete
human_gate: approved 2026-07-12

requires:
  - "05-02 (electron-updater cableado: downloadAndInstallUpdate → killSidecar → quitAndInstall)"
  - "05-04 (release v0.2.0 PUBLICADO + publish-bridge.mjs + máquina en estado M2)"
provides:
  - "Releases v0.2.1, v0.2.2 y v0.2.3 publicados, los cuatro artefactos cada uno"
  - "PKG-02 CERRADO: el camino feliz de electron-updater ejecutado sobre una instalación real"
  - "Prueba empírica de la cadena detectar → descargar (diferencial) → SHA512 → killSidecar() → quitAndInstall(true,true) → relanzar"
  - "Corrección del diagnóstico que dio el 05-04 sobre los borradores duplicados (era falso)"
  - "apps/backend/scripts/check_stale_asset_ports.py — check ejecutable de D-I-02"
affects:
  - "0.3: el backend (D-I-02 URLs con puerto persistido, D-I-03 rate limit desfasado)"

tech-stack:
  added: []
  patterns:
    - "El `.blockmap` no es adorno: electron-updater hace descarga DIFERENCIAL — 766 KB de 128 MB"
    - "Un release por bug arreglado (0.2.2, 0.2.3): el ciclo que el propio T-05-23 predijo como remedio"
    - "Timeout de cliente y coste de la query son UN solo invariante: si la query engorda, el timeout deja de caber y el fallo es SILENCIOSO"

key-files:
  created:
    - apps/backend/scripts/check_stale_asset_ports.py
  modified:
    - apps/desktop/package.json (0.2.0 → 0.2.1 → 0.2.2 → 0.2.3)
    - apps/backend/nyanko_api/anilist.py
    - apps/backend/nyanko_api/database.py
    - apps/backend/nyanko_api/main.py
    - docs/extra/RELEASING.md (en disco; gitignorado, nunca trackeado)

key-decisions:
  - "El bug de los DOS BORRADORES con el mismo tag NO es un publish fallido a medias (diagnóstico erróneo del 05-04): electron-builder lanza sus publishers en PARALELO, ambos comprueban «¿existe el release?» antes de que ninguno lo haya creado, y ambos lo crean. Reproducido 3 de 3 veces en publicaciones limpias a la primera."
  - "El auto-update de electron-updater es DIFERENCIAL por el .blockmap: 766 KB descargados de un instalador de 128 MB (1%)."
  - "Ni las portadas rotas ni el backfill colgado eran regresiones de la Fase 5: son bugs preexistentes del backend que el reinicio del sidecar (inherente al update) se limitó a REVELAR."
  - "El backfill no cambió: AniList se degradó ~6x (la misma query que su propio comentario mide en ~3,5 s tarda hoy 17-25 s) y bajó su rate limit de 90 a 30 req/min."

requirements-completed: [PKG-02]

metrics:
  duration: ~4 h (release + gate humano + dos bugs post-gate con sus dos releases)
  completed: 2026-07-12
  tasks_completed: 2
  files_created: 1
  files_modified: 5
---

# Phase 5 Plan 06: El auto-update de verdad — Summary

**Una Nyanko 0.2.0 instalada encontró la 0.2.1, se bajó 766 KB de un instalador de 128 MB, verificó
su SHA512, mató su propio sidecar, se reinstaló sin asistente y se relanzó sola. PKG-02 está cerrado
porque se ejecutó, no porque esté escrito.**

---

## PKG-02: la evidencia

El gate humano **pasó** (2026-07-12). El usuario lanzó la actualización desde su 0.2.0 instalada y la
aprobó. Ésta es la cadena que ningún plan anterior de la fase podía ejercitar — el 05-02 solo probó
el 404, el 05-04 probó el updater de *Tauri* (minisign) y la rama «estás al día» del de Electron:

| Eslabón | Evidencia |
|---|---|
| **Detecta** | La 0.2.0 instalada ve la 0.2.1 y pide confirmación |
| **Descarga** | **Diferencial.** `main.log`: `Full: 128,125.5 KB, To download: 766.47 KB (1%)` |
| **Verifica** | SHA512 contra el `latest.yml` del release. Sin errores de checksum |
| **Mata el sidecar** | `Install: isSilent: true, isForceRunAfter: true` → `killSidecar()` → `quitAndInstall(true, true)` |
| **Instala** | **Sin asistente.** Ni idioma, ni EULA, ni directorio (D-04) |
| **Relanza** | La app volvió sola como **0.2.1** (`isForceRunAfter`) |
| **DATA-01** | Biblioteca intacta |
| **D-05** | **Cero** `nyanko-api.exe` huérfanos |

La **descarga diferencial** es un hecho que nadie había medido: el `.blockmap` que el 05-04 anotó
como un asset más resulta ser el que convierte un update de 128 MB en uno de 766 KB. Sale gratis y
no estaba en el plan.

**Task 1** (release v0.2.1, commit `46acb55`) se verificó descargando los bytes publicados de forma
anónima, como un cliente cualquiera: `releases/latest/download/latest.yml` → `version: 0.2.1`; el
SHA512 coincide con los 131.200.512 bytes descargados; la firma minisign verifica contra la pubkey
horneada en la 0.1.15 (`d4f6287094b6caba`); y la url del `latest.json` del puente resuelve — basada
en el tag, no `untagged-…` (la trampa del 05-04, que su arreglo esquivó bien).

---

## CORRECCIÓN AL 05-04: el diagnóstico de los borradores duplicados era FALSO

El SUMMARY del 05-04 escribió, sobre los dos borradores compartiendo el tag `v0.2.0`:

> «El primer `--publish always` **falló a medias** (subió el `.blockmap` y nada más) y dejó un
> borrador huérfano; el reintento creó un segundo.»

**Eso no es lo que pasa.** Se reproduce en una publicación **limpia, a la primera, sin ningún fallo**:

**electron-builder lanza sus publishers en PARALELO.** Ambos preguntan «¿existe ya el release?»
*antes* de que ninguno lo haya creado, ambos reciben «no», y **ambos lo crean**. Su propio log lo
dice dos veces:

```
creating GitHub release  reason=release doesn't exist
creating GitHub release  reason=release doesn't exist
```

Ha vuelto a ocurrir en las publicaciones de **0.2.2** y **0.2.3**. Tres de tres. Es una carrera
determinista, no un accidente. `docs/extra/RELEASING.md` lo documenta como paso normal del flujo
(borrar el borrador sobrante antes de firmar), no como incidente.

La guarda del `publish-bridge.mjs` («exige exactamente UN release con este tag, o aborta») sigue
siendo el arreglo correcto —**es lo único que impide firmar el borrador equivocado a cara o cruz**—
pero se escribió creyendo que protegía de un caso raro. Protege del caso **normal**.

Se registra con este detalle porque **un SUMMARY con una causa raíz equivocada es peor que uno sin
ninguna**: el siguiente que lea «solo pasa si un publish falla» va a asumir que su publicación limpia
está a salvo, y no lo está.

---

## Lo que el usuario encontró DESPUÉS del gate (y lo que resultó ser)

Tras actualizar, el usuario reportó la biblioteca «media rota» (sin portadas) y un
«Actualizando biblioteca 0/1811» clavado. **Ninguno de los dos era una regresión de la Fase 5.** Los
dos eran bugs preexistentes del backend que el auto-update se limitó a **revelar**, porque reiniciar
el sidecar es precisamente lo que los dispara. Los dos están arreglados y publicados.

### 1. Sin portadas → D-I-02 (reparado en datos; el diseño, a 0.3)

El backend persiste las URLs de los assets **con el puerto del sidecar dentro**
(`http://127.0.0.1:{port}/assets/…`), y al releerlas las **prefiere** sobre la URL remota del CDN. Si
el sidecar arranca en otro puerto, las portadas cacheadas mueren todas de golpe, en silencio y para
siempre (`COALESCE` no las reescribe nunca).

Lo que lo disparó aquí: dos `scripts\dev.py` del usuario tenían ocupado el 8765, así que el sidecar
de producción llevaba sesiones cayendo a puertos efímeros. Había **3.874 URLs** apuntando a dos
puertos muertos.

- **Hecho:** matados los `dev.py`, el sidecar recupera el 8765, reescritas las 3.874 URLs,
  `integrity_check: ok`, backup previo de la BD.
- **Check ejecutable committeado:** `apps/backend/scripts/check_stale_asset_ports.py` (falla con
  3.874 antes, pasa con 0 después).
- **Arreglo real (no persistir host:puerto) → 0.3.** El backend está fuera del alcance de un
  engine-swap puro. Detalle completo en `deferred-items.md`.

### 2. Backfill clavado en 0/1811 → ARREGLADO Y PUBLICADO (0.2.2 y 0.2.3)

Commits `b88c198` (0.2.2) y `6b20225` (0.2.3).

El backfill pedía a AniList **characters + staff + relations + recommendations** de los 1.811 títulos
— datos que la grid **no pinta**. Medido:

| Query | Tiempo (lote de 50 ids) | Payload |
|---|---|---|
| Con los cuatro bloques | **17-25 s** | 434 KB |
| Sin ellos | **1,3-2,6 s** | 91,6 KB |

El timeout del cliente son **15 s**. O sea: **todos** los lotes expiraban, `done` no incrementaba
jamás, y la barra se quedaba en 0/1811 para siempre **sin un solo error en pantalla**.

**Y la query no había cambiado: AniList se degradó ~6x.** Su propio comentario en el código anota
«probado ~3,5 s» para esa misma consulta. Hoy tarda 17-25 s. (De paso, bajó su rate limit de 90 a 30
req/min — ver D-I-03.)

El backfill ahora pide **solo lo que la grid pinta** (~1,2 min para la biblioteca entera, en vez de
~13); el detalle completo se trae una sola vez al abrir la ficha. Con **guardas + tests** para que un
payload ligero no pueda sobrescribir el cast/relations ya cacheados.

**La lección, que vale más que el arreglo:** *el timeout del cliente y el coste de la query son un
solo invariante*. Cuando el segundo crece —y puede crecer **sin que tú toques nada**, porque el que
engorda es el servidor de otro— el primero deja de caber, y el modo de fallo es el silencio.

---

## Releases vivos

| Versión | Qué lleva |
|---|---|
| **v0.2.0** | El engine-swap (05-04) |
| **v0.2.1** | La subida de versión que el canal de update necesitaba para poder probarse (este plan) |
| **v0.2.2** | Timeout del backfill que sí cabe en la query |
| **v0.2.3** | Query ligera: backfill de ~13 min → ~1,2 min |

Los cuatro publicados, con los cuatro artefactos cada uno, y **ambos feeds verificados contra la red**
(`latest.yml` de electron-updater + `latest.json` del puente Tauri).

Que 0.2.2 y 0.2.3 hayan salido en el día es, además, la demostración de lo que T-05-23 decía en el
threat model del propio plan: *«si 0.2.1 fuese defectuoso, el remedio es 0.2.2 — que es exactamente
el ciclo que este plan demuestra que funciona»*. Se demostró.

---

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] El backfill de AniList expiraba en todos los lotes y la barra no avanzaba nunca**
- **Found during:** Tarea 2, tras el gate (el usuario reportó «Actualizando biblioteca 0/1811» clavado)
- **Issue:** query 6x más lenta que el timeout de 15 s del cliente → todos los lotes expiraban, `done`
  no incrementaba, cero errores visibles
- **Fix:** timeout que cabe en la query (`b88c198`) + la query solo pide lo que la grid pinta
  (`6b20225`), con guardas para no sobrescribir cast/relations cacheados
- **Files modified:** `apps/backend/nyanko_api/{anilist,database,main}.py` + tests
- **Verification:** tests nuevos en `test_anilist.py` / `test_database.py`; medido en vivo (~1,2 min
  la biblioteca entera)
- **Committed in:** `b88c198`, `6b20225` — publicados como **0.2.2** y **0.2.3**

**2. [Rule 1 - Bug, reparación de datos] 3.874 URLs de portada apuntando a puertos muertos**
- **Found during:** Tarea 2, tras el gate («la biblioteca está media rota, no carga ningún portrait»)
- **Issue:** el backend persiste `http://127.0.0.1:{port}/assets/…`; dos `dev.py` ocupaban el 8765 y
  el sidecar de producción llevaba sesiones en puertos efímeros
- **Fix:** liberado el 8765, reescritas las URLs al puerto vivo, `integrity_check: ok`. El **fallo de
  diseño** (no persistir host:puerto) queda **deferido a 0.3** — 0.2 es engine-swap puro
- **Files modified:** `apps/backend/scripts/check_stale_asset_ports.py` (nuevo)
- **Committed in:** `48b8536` (registro de D-I-02)

**3. [Corrección de un SUMMARY anterior] La causa raíz de los dos borradores que dio el 05-04 era falsa**
- Ver la sección **CORRECCIÓN AL 05-04** arriba. No es código: es un hecho registrado mal que habría
  hecho perder el tiempo (o publicar mal) a quien lo leyera. Corregido aquí y en `RELEASING.md`.

**Total deviations:** 2 auto-fixed (2 bugs, ambos PREEXISTENTES y revelados por el update, ninguno
regresión de la fase) + 1 corrección documental.
**Impact on plan:** Cero scope creep en el shell de Electron. Los dos arreglos son de backend y
salieron como releases de patch (0.2.2 / 0.2.3) por el mismo canal que este plan acaba de validar.

## Lo que este plan cierra

- **PKG-02: Completo.** Detecta → descarga (diferencial) → verifica SHA512 → mata el sidecar →
  instala en silencio → se relanza. **Ejecutado sobre una instalación real, no solo escrito.**
- **Criterio de éxito #3 del ROADMAP:** verificado.
- **DATA-01:** sobrevive también al camino de auto-update, no solo al de instalación.

## Estado de la máquina

**M3** — Nyanko **0.2.3** instalada (llegó por auto-update encadenado desde la 0.2.0), biblioteca
intacta con sus portadas, backfill funcionando en ~1,2 min.

## Known Stubs

Ninguno.

## Self-Check: PASSED

- `apps/backend/scripts/check_stale_asset_ports.py` — existe
- commits `46acb55`, `48b8536`, `b88c198`, `8d35880`, `6b20225`, `45b8cec` — existen en el árbol
- `apps/desktop/package.json` → `0.2.3`
- releases v0.2.0 / v0.2.1 / v0.2.2 / v0.2.3 — publicados; ambos feeds verificados contra la red

---
*Phase: 05-packaging-auto-update*
*Completed: 2026-07-12*
