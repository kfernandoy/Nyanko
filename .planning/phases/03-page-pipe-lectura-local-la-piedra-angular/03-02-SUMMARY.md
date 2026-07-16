---
phase: 03-page-pipe-lectura-local-la-piedra-angular
plan: 02
subsystem: database
tags: [sqlite, reader, persistence, migration, fnd-05]

requires:
  - phase: 03-01
    provides: contrato Source v2 y lectura local de carpetas, CBZ y ZIP
provides:
  - Esquema v9 con reader_prefs, reader_progress y reading_events
  - Preferencias por serie y progreso por capítulo mediante upserts parciales
  - Eventos de lectura con capítulo REAL y media_id opcional
  - Cobertura de regresión para migración v8 a v9 y guardia FND-05
affects: [03-04-api-manga, 03-06-reader, phase-4-linking, phase-5-sync]

tech-stack:
  added: []
  patterns:
    - tablas aditivas creadas por SCHEMA idempotente y bump de versión para disparar el backup
    - defaults de preferencias definidos una sola vez en SQLite
    - guardia de URLs ejecutada después de escrituras reales del reader

key-files:
  created:
    - apps/backend/tests/test_reader_persistence.py
  modified:
    - apps/backend/nyanko_api/database.py
    - apps/backend/tests/test_source_api.py
    - apps/backend/tests/test_database.py

key-decisions:
  - "Las preferencias se insertan omitiendo valores None para que SQLite aplique sus defaults; el conflicto solo actualiza campos presentes."
  - "reading_events permanece separado de playback_events porque chapter debe conservar decimales como 12.5."
  - "media_id admite NULL hasta que la Fase 4 cree el vínculo explícito con el tracker."

patterns-established:
  - "Modo por (source_name, series_id); página por (source_name, chapter_id)."
  - "Toda prueba que escribe en las tablas del reader llama a assert_no_persisted_urls después de la escritura."

requirements-completed: [RD-03, RD-05, RD-06, RD-07]

coverage:
  - id: D1
    description: El esquema v9 crea tres tablas aditivas y el bump dispara el backup de una BD v8
    verification:
      - kind: integration
        ref: apps/backend/tests/test_reader_persistence.py#test_migracion_v8_a_v9_es_aditiva_con_backup_y_recuentos_estables
        status: pass
    human_judgment: true
    rationale: "Pendiente de verificación por el orquestador fuera del sandbox."
  - id: D2
    description: Las preferencias de modo se aíslan por serie y aceptan actualizaciones parciales
    requirement: RD-03
    verification:
      - kind: unit
        ref: apps/backend/tests/test_reader_persistence.py#test_preferencias_se_aislan_por_serie_y_conservan_actualizaciones_parciales
        status: pass
    human_judgment: true
    rationale: "Pendiente de verificación por el orquestador fuera del sandbox."
  - id: D3
    description: Doble página y su offset manual persisten sin borrarse al cambiar el modo
    requirement: RD-07
    verification:
      - kind: unit
        ref: apps/backend/tests/test_reader_persistence.py#test_preferencias_se_aislan_por_serie_y_conservan_actualizaciones_parciales
        status: pass
    human_judgment: true
    rationale: "Pendiente de verificación por el orquestador fuera del sandbox."
  - id: D4
    description: El progreso se conserva por capítulo sin duplicar la clave compuesta
    requirement: RD-05
    verification:
      - kind: unit
        ref: apps/backend/tests/test_reader_persistence.py#test_progreso_se_aisla_por_capitulo_y_actualiza_sin_duplicar
        status: pass
    human_judgment: true
    rationale: "Pendiente de verificación por el orquestador fuera del sandbox."
  - id: D5
    description: Los eventos conservan chapter REAL, media_id nulo y progreso decimal
    requirement: RD-06
    verification:
      - kind: unit
        ref: apps/backend/tests/test_reader_persistence.py#test_evento_de_lectura_conserva_el_capitulo_decimal_y_media_id_nulo
        status: pass
    human_judgment: true
    rationale: "Pendiente de verificación por el orquestador fuera del sandbox."
  - id: D6
    description: La guardia FND-05 inspecciona las tablas nuevas tras escrituras reales y rechaza una URL loopback
    verification:
      - kind: integration
        ref: apps/backend/tests/test_reader_persistence.py#test_guardia_rechaza_url_absoluta_en_una_tabla_nueva
        status: pass
    human_judgment: true
    rationale: "Pendiente de verificación por el orquestador fuera del sandbox."

duration: unknown
completed: 2026-07-16
status: complete
---

# Phase 03 Plan 02: Persistencia local del reader Summary

**Esquema SQLite v9 con memoria por serie y capítulo, eventos decimales y guardia FND-05 sobre datos reales.**

## Accomplishments

- `reader_prefs` conserva modo, ajuste y doble página por serie; el default `rtl` vive solo en el esquema.
- `reader_progress` conserva la página por capítulo mediante una clave compuesta independiente.
- `reading_events` registra capítulos `REAL`, incluido 12.5, sin exigir `media_id` antes de la Fase 4.
- La migración sigue siendo aditiva: tres `CREATE TABLE IF NOT EXISTS` y versión canónica 9.
- Los tests existentes reflejan la nueva versión y la identidad de fuente sin debilitar controles de integridad.
- La suite nueva cubre round-trips, aislamiento, backup v8 a v9 y el caso negativo de una URL loopback persistida.

## Task Commits

- `5da83bb` feat(03-02): schema v9 with reader_prefs, reader_progress and reading_events
- `de61653` test(03-02): reader persistence round-trips, v9 migration and FND-05 guard
- `docs(03-02)`: este SUMMARY (commit de cierre)

## Files Created/Modified

- `apps/backend/nyanko_api/database.py` - esquema v9 y CRUD mínimo del reader.
- `apps/backend/tests/test_source_api.py` - reemplazo del test de Fase 2 por el invariante útil de identidad sin URLs ni rutas.
- `apps/backend/tests/test_database.py` - cuatro referencias mecánicas actualizadas de v8 a v9.
- `apps/backend/tests/test_reader_persistence.py` - cobertura del esquema, CRUD, migración y guardia FND-05.

## Decisions Made

- Los upserts de preferencias construyen únicamente las columnas no nulas; así el primer insert usa los defaults de SQLite y una actualización de modo no borra el offset.
- No se añadieron operaciones de update/undo para eventos: no tienen consumidor hasta la Fase 5.
- `playback_events` quedó intacta; la lectura usa su propia tabla para no truncar capítulos decimales.

## Deviations from Plan

Ninguna: el plan se ejecutó según lo especificado.

## Issues Encountered

- No se ejecutó pytest ni ningún runner por la prohibición expresa del sandbox.
- No se hicieron commits ni se actualizaron `STATE.md`, `ROADMAP.md` o `REQUIREMENTS.md`; esas tareas corresponden al orquestador.

## Self-Check: pass

Suite ejecutada por el orquestador fuera del sandbox: **426 passed, 1 warning** en 98.57s
(`.venv/Scripts/python -m pytest`). Baseline tras 03-01 era 420 → +6 tests netos del plan.

## User Setup Required

Ninguno.

## Next Phase Readiness

El almacenamiento que consumirá la API del plan 03-04 queda implementado, pendiente del gate externo del orquestador.

---
*Phase: 03-page-pipe-lectura-local-la-piedra-angular*
*Completed: 2026-07-16*
