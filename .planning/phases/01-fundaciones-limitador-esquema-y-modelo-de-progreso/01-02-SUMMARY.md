---
phase: 01-fundaciones-limitador-esquema-y-modelo-de-progreso
plan: 02
subsystem: backend/progress-model
tags: [schema-migration, progress, tracker-sync, sqlite, tdd]
requires: []
provides:
  - "docs/specs/progress-model.md — el modelo de progreso decidido y escrito"
  - "schema v8: library_entries.chapter_progress REAL (aditivo)"
  - "nyanko_api/progress.py — módulo puro: to_provider, next_progress, is_reread, effective_chapter"
  - "Database.tracker_progress — el lector del espejo del tracker"
  - "Database.set_chapter_progress — el escritor de la pareja coherente"
  - "scripts/verify_real_db_migration.py — gate de migración contra la BD real"
affects:
  - "apps/backend/nyanko_api/database.py"
  - "apps/backend/nyanko_api/main.py"
tech-stack:
  added: []
  patterns:
    - "Migración aditiva (ALTER TABLE ADD COLUMN) + _add_column idempotente: el patrón de la casa"
    - "Reconciliación al leer, no invariante mantenido al escribir"
    - "Guarda que falla cerrado (None) ante valor de tracker desconocido"
key-files:
  created:
    - docs/specs/progress-model.md
    - apps/backend/nyanko_api/progress.py
    - apps/backend/tests/test_progress.py
    - apps/backend/scripts/verify_real_db_migration.py
  modified:
    - apps/backend/nyanko_api/database.py
    - apps/backend/nyanko_api/main.py
    - apps/backend/tests/test_database.py
decisions:
  - "Columna aditiva chapter_progress REAL en vez de rebuild de library_entries: SQLite no tiene ALTER COLUMN TYPE, y el rebuild sobre 2.774 filas vivas devolvería 10.0 donde la API hoy devuelve 10"
  - "progress (INTEGER) es siempre autoritativo; chapter_progress solo vale si floor(chapter_progress) == progress"
  - "La reconciliación se evalúa AL LEER (progress.effective_chapter), no se mantiene en los cuatro escritores de progress"
  - "La ventana transitoria (sync del tracker con valor viejo mientras la mutación está encolada) queda ACEPTADA y escrita, no es un bug pendiente"
  - "next_progress falla cerrado: sin valor del tracker devuelve None y no se escribe nada en la lista real"
  - "progress_before guarda el valor DEL TRACKER capturado antes de update_remote_library_entry — un 0 de relleno sería peor que el bug"
metrics:
  duration: ~50 min
  tasks_completed: 3
  commits: 4
  tests: 354 passed (18 nuevos en test_progress.py, 5 nuevos en test_database.py)
  completed: 2026-07-13
status: complete
---

# Phase 1 Plan 02: Modelo de progreso y migración a schema v8 — Summary

El capítulo 10.5 ya tiene dónde vivir: `chapter_progress REAL` en local, `floor()` al cruzar hacia
el proveedor, guarda monotónica contra el espejo del tracker (no contra el local), y `progress_before`
grabado en los tres endpoints que antes lo dejaban NULL. La migración v8 se ejercitó contra una copia
de la BD real de 31,9 MB: `integrity_check ok`, los 29 recuentos por tabla idénticos, backup creado.

## Qué se construyó

### Task 1 — La decisión escrita, y luego el schema que la implementa (`9eeee1e`)

`docs/specs/progress-model.md` primero, el código después: FND-04 exige que el modelo esté *escrito*,
y escribirlo después del código es escribir una justificación, no una decisión. El documento fija:

- **Dos números, no uno.** `progress` (INTEGER) es lo que el tracker tiene o tendrá; `chapter_progress`
  (REAL, `NULL` para anime) es lo que el usuario leyó de verdad. `floor()` va del segundo al primero y
  solo se aplica al cruzar hacia el proveedor.
- **Rebuild de tabla: considerado y rechazado.** Con su motivo (SQLite no tiene `ALTER COLUMN TYPE`; el
  rebuild sobre 2.774 filas vivas devolvería `10.0` donde la API hoy devuelve `10`) y con el único
  precedente del árbol nombrado (`_migrate_torrent_filters`, `database.py:507`).
- **Los cuatro escritores de `progress`** por `fichero:línea` (`database.py:1231`, `:1374`, `:2158`,
  `:2639`), y `:2666` nombrado explícitamente como **no** escritor de `progress` (escribe `status`).
- **La ventana transitoria, aceptada.** Sync del tracker con el valor viejo mientras la mutación está
  encolada → el reader cae a `progress` hasta que la cola drena. Transitoria, autocurativa, sin pérdida
  de datos. Escrita como consecuencia conocida, para que la Fase 5 no la tape con un parche.

Schema v8 (aditivo): `CANONICAL_SCHEMA_VERSION` 7 → 8, `chapter_progress REAL` en `SCHEMA` y su
`_add_column` en `initialize()`. Subir la constante es, por sí solo, lo que arma
`_backup_before_migration` — el único rollback que existe. Más `Database.tracker_progress()` (lee
`remote_library_entries.progress`) y `Database.set_chapter_progress()` (escribe la pareja coherente en
la misma transacción).

### Task 2 — `progress.py`, puro, con su tabla de casos (`df5742d` RED, `6e8522d` GREEN)

Módulo sin `sqlite3`, sin `httpx`, sin imports del proyecto (único import: `math`). Cuatro funciones:
`to_provider`, `next_progress`, `is_reread`, `effective_chapter`. Los casos se escribieron **antes**
que el código: el commit RED falló con `ModuleNotFoundError: No module named 'nyanko_api.progress'`.

`Database.tracker_progress` es lo que convierte «la guarda compara contra el tracker» de convención en
construcción: sin ese lector, `next_progress` recibiría su valor de referencia de dondequiera que el
llamador decidiera.

**Los tres huecos de `main.py`, cerrados.** `update_progress`, `edit_media_entry` y
`bulk_update_library_entry` grababan `progress_after` sin `progress_before`. En los tres, el valor del
tracker se captura **antes** de `update_remote_library_entry`, que sobrescribe el espejo con el valor
nuevo: leerlo después daría `progress_before == progress_after`, un deshacer que no deshace nada.

### Task 3 — La migración contra la BD real (`1a74fbb`)

`scripts/verify_real_db_migration.py`. La original se abre en `mode=ro` y se copia con la API de backup
de sqlite (un `shutil.copy()` del `.sqlite3` a secas se dejaría el `-wal` fuera y copiaría una BD a
medias). Toda escritura ocurre sobre la copia, en una ruta determinista que el plan 01-03 puede
consumir (última línea de la salida). Las tablas se enumeran desde `sqlite_master`, no de una lista a
mano. Sin BD de producción: imprime que omite y sale 0.

## Evidencia FND-06: salida real del script

```
BD real: C:\Users\kfern\AppData\Roaming\app.nyanko.desktop\nyanko.sqlite3  (31.9 MB)
copia:   C:\Users\kfern\AppData\Local\Temp\nyanko-v8-verify.sqlite3

tabla                             antes    despues
--------------------------------------------------
accounts                              1          1
cache                                 5          5
conflicts                             0          0
episodes                          25740      25740
extension_clients                     2          2
external_identities                5099       5099
library_entries                    2774       2774
library_folders                       1          1
local_files                         419        419
match_corrections                     2          2
media                              2786       2786
media_details_cache                2786       2786
media_genres                       7890       7890
media_mappings                        2          2
media_seasons                      2320       2320
media_tags                            0          0
media_titles                      16269      16269
pending_mutations                     0          0
playback_events                      11         11
providers                             2          2
remote_library_entries             2774       2774
schema_migrations                     1          2  (la bitacora gana la fila v8)
settings                             15         15
torrent_filter_anime                  0          0
torrent_filter_conditions             0          0
torrent_filters                       0          0
torrent_seen                        135        135
torrent_sources                       1          1
wont_watch                            0          0

integrity_check: ok -> ok
schema_migrations: 7 -> 8
library_entries.chapter_progress: REAL
backup pre-migracion: nyanko-v8-verify.backup-v8-20260713-133007.sqlite3
BD original intacta (tamano y mtime): si

OK: migracion v8 aditiva, integridad intacta, recuentos identicos, backup creado.
C:\Users\kfern\AppData\Local\Temp\nyanko-v8-verify.sqlite3
exit=0
```

Los 29 recuentos idénticos (`library_entries` 2.774, `episodes` 25.740 — los valores reales de hoy, no
los 2.761/25.727 del ROADMAP). El único cambio es `schema_migrations` 1 → 2 filas: la bitácora ganando
la fila v8, que es exactamente lo que la migración debe hacer.

**La BD original no se modificó.** Comprobado tras correr el script: `MAX(version)` sigue en **7**, no
tiene `chapter_progress`, y tamaño/`mtime` son los mismos (33.398.784 bytes). Se migrará sola, con su
backup, la próxima vez que la app real arranque.

## Verificación

| Check | Resultado |
|-------|-----------|
| `python -m pytest -q` (suite completa) | **354 passed** |
| `ruff check nyanko_api/ tests/ scripts/` | limpio |
| `progress.py` puro (sin `sqlite3`/`httpx`/`nyanko_api`) | OK — único import: `math` |
| `CANONICAL_SCHEMA_VERSION == 8` | OK |
| `PRAGMA table_info(library_entries)` → `chapter_progress` REAL | OK |
| BD v7 con filas → v8: filas intactas, `chapter_progress` NULL, backup creado | OK |
| `set_chapter_progress(1, 10.5)` → `chapter_progress=10.5`, `progress=10` | OK |
| `tracker_progress` devuelve 7 (tracker) y no 3 (local) | OK |
| `progress_before == 7` en **los tres** endpoints (tracker=7, local=3) | OK |
| `verify_real_db_migration.py` contra la BD real | exit 0, salida arriba |
| `verify_real_db_migration.py` sin BD | exit 0, «omitido» |

## Decisiones tomadas

1. **Columna aditiva, no rebuild.** `ALTER TABLE ADD COLUMN` no reescribe ni una fila existente y, por
   construcción, no puede alterar los recuentos por tabla que FND-06 exige comparar.
2. **La reconciliación se evalúa al leer, no se mantiene al escribir.** `progress` tiene cuatro
   escritores que no tocarán `chapter_progress`; un invariante que hay que mantener en cuatro sitios es
   un invariante que se rompe. `effective_chapter` es una función pura: no hay nada que sincronizar, y
   el quinto escritor que alguien añada en la Fase 5 no puede romperla por omisión.
3. **La ventana transitoria se acepta, y se escribe.** El precio de evitarla sería mantener el
   invariante en los cuatro escritores — el diseño que se rechazó.
4. **`next_progress` falla cerrado.** Sin valor del tracker devuelve `None`. Que la Fase 5 tenga que ir
   a buscarlo es el punto.
5. **`is_reread` como señal aparte.** La guarda monotónica ya devuelve `None` al releer una serie
   terminada; la señal existe para que la Fase 5 (SYN-04) no reimplemente la comprobación de
   `COMPLETED` dentro de un endpoint.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `test_initialize_creates_canonical_provider_schema` afirmaba `version == 7`**
- **Found during:** Task 1
- **Issue:** Un test existente horneaba la versión del schema. Subir `CANONICAL_SCHEMA_VERSION` a 8 lo
  rompía — es exactamente lo que ese test debe detectar, así que su aserción era la que había que
  actualizar, no el código.
- **Fix:** `assert version == 8`. Es el mismo hecho que afirma el test nuevo
  `test_canonical_schema_version_is_8`, desde el otro lado (la BD creada, no la constante).
- **Files modified:** `apps/backend/tests/test_database.py`
- **Commit:** `9eeee1e`

### Desviaciones deliberadas

**Las citas `fichero:línea` de `progress-model.md` son las POSTERIORES a la edición, no las del plan.**
El plan pedía citar `database.py:1226`, `:1369`, `:2153`, `:2604` (y `:2631` como no-escritor). Añadir
`chapter_progress` a `SCHEMA` y su `_add_column` desplaza esas líneas +5. Citar los números del plan
habría dejado el documento **mintiendo sobre el árbol que la Fase 5 va a leer**, que es justo lo que el
criterio de aceptación («cada `fichero:línea` citado se ha comprobado abriéndolo») existe para impedir.
Las líneas del documento son las verificadas post-edición: `:1231`, `:1374`, `:2158`, `:2639`, y
`:2666` como el no-escritor. Son los mismos cuatro escritores, en el mismo orden, con los mismos SQL.
Cada una comprobada por `grep` contra el árbol final.

**`is_reread` no estaba en la lista de artefactos del plan.** El plan pedía que `next_progress` con
`status="COMPLETED"` «devuelva `None` **y señale relectura**». `next_progress` devuelve `int | None`:
no puede señalar nada más. La señal es una función pura de tres líneas, testeada, y es el gancho que
impide que la Fase 5 reimplemente la comprobación de `COMPLETED` dentro de un endpoint — el fallo que
el módulo existe para prevenir.

## Known Stubs

Ninguno. Las cuatro funciones de `progress.py` están implementadas y testeadas. `set_chapter_progress`
y `tracker_progress` funcionan, pero **todavía no tienen llamador en el reader**: eso es la Fase 5
(el reader de manga aún no existe). `tracker_progress` sí tiene tres llamadores vivos hoy — los tres
endpoints de sync.

## Para la Fase 5

- **`progress.py` es la única definición.** No reimplementes `floor()` ni la guarda monotónica dentro
  de un endpoint.
- **El valor de referencia sale de `Database.tracker_progress`.** Si `next_progress` te devuelve `None`
  porque el tracker es desconocido, ve a buscarlo — no lo rellenes con el local ni con un 0.
- **La ventana transitoria de `effective_chapter` no es un bug.** Está en `progress-model.md`. No la
  parchees.
- **`is_reread` es tu gancho para SYN-04** (la UX de `REPEATING`).

## Self-Check: PASSED

Ficheros creados verificados en disco:
- `docs/specs/progress-model.md` — FOUND
- `apps/backend/nyanko_api/progress.py` — FOUND
- `apps/backend/tests/test_progress.py` — FOUND
- `apps/backend/scripts/verify_real_db_migration.py` — FOUND

Commits verificados en `git log`:
- `9eeee1e` — FOUND (Task 1: modelo escrito + schema v8)
- `df5742d` — FOUND (Task 2 RED: tabla de casos)
- `6e8522d` — FOUND (Task 2 GREEN: progress.py + los tres endpoints)
- `1a74fbb` — FOUND (Task 3: verify_real_db_migration.py)
