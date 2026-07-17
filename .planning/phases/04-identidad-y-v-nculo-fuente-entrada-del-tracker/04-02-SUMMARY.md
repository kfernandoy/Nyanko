---
phase: 04-identidad-y-v-nculo-fuente-entrada-del-tracker
plan: 02
subsystem: backend
tags: [sqlite, media-mappings, manga-linking, namespace-guard]

requires:
  - phase: 03-page-pipe-lectura-local-la-piedra-angular
    provides: series_id opaco de local_archive y la tabla media_mappings ya enviada para anime
provides:
  - schema v11 con media_mappings.chapter_offset aditivo
  - guarda único de namespace para escribir, borrar y leer vínculos de manga
  - SeriesLink y require_link como puerta cerrada ante series sin vínculo confirmado
affects: [04-03-manga-link-http, phase-05-sync-progreso, media-mappings]

tech-stack:
  added: []
  patterns:
    - una sola regla de namespace compartida por escritura, borrado y lectura
    - el camino de anime conserva get_media_mapping como tupla de dos elementos

key-files:
  created:
    - apps/backend/nyanko_api/linking.py
    - apps/backend/tests/test_linking.py
  modified:
    - apps/backend/nyanko_api/database.py
    - apps/backend/tests/test_database.py
    - apps/backend/tests/test_reader_persistence.py

key-decisions:
  - "media_mappings sigue siendo la única tabla del vínculo; chapter_offset entra por migración aditiva y no por SCHEMA."
  - "Una fila del namespace de manga significa confirmación explícita; assert_manga_namespace protege las tres operaciones que podrían romperlo."
  - "require_link no consulta matcher ni acepta scores: una propuesta nunca se convierte en consentimiento."

patterns-established:
  - "get_media_mapping permanece congelado para anime; get_media_mapping_full es la lectura aditiva del vínculo."
  - "El media_id de SeriesLink es canónico y solo se convierte al id externo al escribir en el proveedor."

requirements-completed: [LNK-01, LNK-04]

coverage:
  - id: D1
    description: schema v11 añade chapter_offset sin alterar SCHEMA y migra filas v10 con default cero y backup
    requirement: LNK-01
    verification:
      - kind: integration
        ref: apps/backend/tests/test_database.py#test_v10_media_mappings_migra_sin_perder_filas_y_con_backup
        status: passed
    human_judgment: false
    rationale: "Medido por el orquestador fuera del sandbox: suite completa 488 passed, 0 failed (baseline 476, +12). FND-06 contra copia de la BD real (scripts/verify_real_db_migration.py): schema_migrations 7 -> 11, integrity_check ok -> ok, recuentos identicos en las 16 tablas (2.774 library_entries, 16.269 media_titles), backup nyanko-v8-verify.backup-v11-20260717-090303.sqlite3 escrito, BD original intacta. Gate de fuente ejecutado en las dos direcciones: 0 lineas anadidas con CREATE TABLE en el diff de database.py, y el mismo gate da 1 al inyectarle la regresion — SCHEMA intacta."
  - id: D2
    description: assert_manga_namespace impide escribir o borrar mappings desde el namespace equivocado
    requirement: LNK-01
    verification:
      - kind: unit
        ref: apps/backend/tests/test_database.py#test_el_guarda_impide_reapuntar_un_vinculo_confirmado y test_el_borrado_respeta_el_namespace_y_es_idempotente
        status: passed
    human_judgment: false
    rationale: "Medido por el orquestador fuera del sandbox (488 passed). Gate de fuente de «una regla, un sitio» ejecutado contra el arbol: assert_manga_namespace se LLAMA desde exactamente tres sitios — database.py:2479 (set_media_mapping, escritura), database.py:2496 (delete_media_mapping, borrado) y linking.py:35 (resolve_link, lectura). Ninguna reimplementa el `if`. No-regresion del anime medida: test_main.py:300 (set_media_mapping('crunchyroll', ...) sin opt-in) sigue verde sin tocarlo — era el quinto llamador que el censo original del plan no vio."
  - id: D3
    description: require_link falla cerrado sin fila confirmada y resolve_link rechaza mappings de anime
    requirement: LNK-04
    verification:
      - kind: unit
        ref: apps/backend/tests/test_linking.py
        status: passed
    human_judgment: false
    rationale: "Medido por el orquestador fuera del sandbox (488 passed): test_una_propuesta_fuerte_no_es_un_vinculo_confirmado (UnlinkedSeriesError con match_correction 'berserk' + entrada de biblioteca puntuable en la misma BD, pending_mutations = 0) y test_un_mapping_de_anime_no_es_un_vinculo_de_manga (ValueError, no SeriesLink ni None; la fila de anime sigue en (777, 3)). Gate de fuente ejecutado en las dos direcciones: linking.py da 0 matches de matcher|find_best_match|rank_matches|score|INSERT|UPDATE|set_media_mapping, y el mismo grep da 1 sobre un import inyectado. resolve_link es el UNICO consumidor de get_media_mapping_full en produccion (linking.py:38); el resto son tests."

duration: ~16min
completed: 2026-07-17
status: complete
---

# Phase 04 Plan 02: Vínculo almacenado y puerta de sync Summary

**Schema v11 con offset de manga, namespace reservado por una sola guarda y una puerta de vínculo que falla cerrada sin consentimiento.**

## Performance

- **Duration:** ~16min
- **Started:** 2026-07-17T12:38:00Z
- **Completed:** 2026-07-17T12:54:00Z
- **Tasks:** 2
- **Files modified:** 4 del plan, más este SUMMARY

## Accomplishments

- `media_mappings` gana `chapter_offset` mediante `_add_column`; `CANONICAL_SCHEMA_VERSION` sube a
  11 y `SCHEMA` permanece byte a byte igual.
- `assert_manga_namespace` concentra la disjunción entre anime y manga y la usan
  `set_media_mapping`, `delete_media_mapping` y `resolve_link`.
- `SeriesLink`, `resolve_link` y `require_link` leen únicamente vínculos confirmados; no conocen el
  matcher, no escriben y distinguen una serie sin vincular de un namespace inválido.

## Task Commits

- **Task 1:** `9893989` — `feat(04-02): schema v11 chapter_offset + manga namespace guard`
  (`database.py`, `test_database.py`, `test_reader_persistence.py`)
- **Task 2:** `03ca9ba` — `feat(04-02): linking.py — the gate that knows how to say no`
  (`linking.py`, `test_linking.py`)

El executor no ejecutó `git add` ni `git commit`, conforme a `.planning/CODEX-RULES.md` (regla 4: su
sandbox deniega la escritura en `.git/`). Los commits los hizo el orquestador tras medir los gates.

## Files Created/Modified

- `apps/backend/nyanko_api/database.py` - schema v11 aditivo, guarda y CRUD ampliado del mapping.
- `apps/backend/tests/test_database.py` - aserciones v11, migración realista v10 y gates del guarda.
- `apps/backend/tests/test_reader_persistence.py` - la séptima aserción del bump, que el censo del plan
  no vio. Corregida por el orquestador (ver Deviations).
- `apps/backend/nyanko_api/linking.py` - modelo del vínculo y puerta que falla cerrada.
- `apps/backend/tests/test_linking.py` - round-trip, offsets, ausencia de auto-vínculo y guarda de lectura.

## Decisions Made

- Se siguió el plan literalmente: `get_media_mapping` no se modificó y `main.py` quedó intacto.
- El guarda vive en una función pública de módulo para que una fuente de manga futura se añada una
  vez a `MANGA_RESERVED_PROVIDERS` y alcance las tres operaciones.
- `UnlinkedSeriesError` es independiente de `SourceError`; ausencia de consentimiento y fallo de
  fuente son estados distintos.

## Deviations from Plan

**Una, del orquestador: el censo de aserciones del plan estaba incompleto.**

El plan declara poseer «las SEIS aserciones que el bump de versión pone rojas por construcción» y las
sitúa todas en `tests/test_database.py`. Son **siete**, y la séptima vive en otro fichero:
`tests/test_reader_persistence.py:180` (`MAX(version) == 10`) y `:183` (el glob
`nyanko.backup-v10-*.sqlite3`, que lleva la versión en el nombre porque
`_backup_before_migration` la escribe ahí). Con los cuatro `files_modified` de Codex, la suite daba
**1 failed, 487 passed**.

Codex hizo lo correcto NO tocándola: `test_reader_persistence.py` no está en `files_modified` y la
regla 6 de CODEX-RULES le prohíbe salirse. La corrigió el orquestador: dos líneas, `10 -> 11` y
`v10 -> v11`. La tercera aserción del mismo test (`== 8`, la versión DENTRO del backup degradado) es
correcta y no se tocó. El nombre del test (`test_migracion_v8_a_v9_...`) ya era obsoleto antes de
esta fase y se deja como está: renombrarlo es churn fuera de alcance.

Es el mismo error de clase que el censo de llamadores que este plan ya documenta («son CUATRO, no
dos»): un inventario escrito razonando, no midiendo. Fichero tocado fuera de `files_modified`:
`apps/backend/tests/test_reader_persistence.py`.

## Issues Encountered

- Otro proceso de Codex escribió los cuatro ficheros del plan mientras se realizaba la lectura
  obligatoria. Se esperó a que quedaran estables y se revisó el diff completo sin revertir ni pisar
  esos cambios compartidos.
- No se ejecutó pytest, ningún runner ni `scripts/verify_real_db_migration.py`; la verificación de
  comportamiento y de la copia real queda pendiente del orquestador.
- El primer gate de igualdad de `SCHEMA` dio un falso negativo por mezclar decodificación UTF-8 y la
  predeterminada de PowerShell. Se repitió con UTF-8 explícito y confirmó igualdad; no se aceptó el
  resultado por razonamiento.

## User Setup Required

Ninguno.

## Self-Check: PASSED

Cerrado por el orquestador con gates ejecutados fuera del sandbox. Los `unknown` del executor eran
correctos: no podía medir nada de esto (CODEX-RULES reglas 2 y 4).

| Gate | Estado |
|------|--------|
| Suite completa (`pytest -q`) | **488 passed, 0 failed** en 88.88s (baseline 476, +12) |
| Alcance (`git status --porcelain`) | solo los 4 `files_modified` + SUMMARY. `main.py` intacto (T-04-02-08 respetado) |
| `conftest.py` / `pyproject.toml` / `pytest.ini` | intactos (regla 3) |
| `ruff check` sobre los ficheros tocados | All checks passed |
| FND-06: migración contra copia de la BD real | 7 -> 11, `integrity_check` ok, 16 tablas con recuentos idénticos, backup `-v11-` escrito, original intacta |
| `SCHEMA` sin `CREATE TABLE` añadido | 0 líneas añadidas; el gate da 1 al inyectar la regresión (medido en las dos direcciones) |
| `get_media_mapping` sin tocar | no aparece en el diff; sigue devolviendo tupla de dos |
| `assert_manga_namespace`: una regla, tres llamadores | `database.py:2479` + `:2496` + `linking.py:35`. Cero copias del `if` |
| `resolve_link`, único consumidor de `get_media_mapping_full` | sí en producción (`linking.py:38`); el resto son tests |
| `linking.py` no sabe puntuar | 0 matches; el gate da 1 sobre un import inyectado |

**Nota sobre los gates de fuente:** se ejecutaron contra el árbol y comprobando las dos direcciones
(el número esperado, y que se pongan rojos al inyectar la regresión que existen para cazar), por el
anti-patrón `blocking` de esta fase. El primer intento del gate de `SCHEMA` dio un **falso positivo**:
`grep "CREATE TABLE"` sobre el diff matchea la etiqueta de contexto del hunk
(`@@ -312 +312,3 @@ CREATE TABLE IF NOT EXISTS reading_events (`), no una línea añadida. Se corrigió
filtrando `^\+[^+]`. El executor tropezó con un falso positivo distinto en el mismo gate (mezcla de
codificaciones en PowerShell). Cuatro de cuatro gates de esta fase fallaron al medirse; este es el quinto.

## Next Phase Readiness

El código y los tests de 04-02 quedan listos para que el orquestador ejecute los gates fuera del
sandbox, haga los commits atómicos y cierre los estados `unknown` antes de iniciar 04-03.

---
*Phase: 04-identidad-y-v-nculo-fuente-entrada-del-tracker*
*Completed: 2026-07-17*
