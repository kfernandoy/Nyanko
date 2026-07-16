---
phase: 03-page-pipe-lectura-local-la-piedra-angular
plan: 04
subsystem: backend
tags: [fastapi, pydantic, manga, reader, sqlite, source-registry]

requires:
  - phase: 03-02
    provides: persistencia v9 para preferencias, progreso y eventos de lectura
  - phase: 03-03
    provides: URL relativa de pagina y mapeo HTTP de errores de fuente
provides:
  - API plana para navegar capitulos y obtener paginas de una fuente
  - Round-trip HTTP de preferencias por serie y progreso por capitulo
  - Creacion de eventos de lectura con chapter REAL
  - Registry de fuentes actualizado al anadir o borrar carpetas sin reiniciar
affects: [03-05-cliente-manga, 03-06-reader, phase-5-sync]

tech-stack:
  added: []
  patterns:
    - ids opacos enviados como query params y resueltos exclusivamente por SourceEngine
    - respuestas de pagina con URL relativa compuesta por _page_url
    - registry reconstruido solo en mutaciones de carpetas

key-files:
  created:
    - apps/backend/tests/test_manga_api.py
  modified:
    - apps/backend/nyanko_api/main.py
    - apps/backend/nyanko_api/models.py

key-decisions:
  - "source, series_id y chapter_id viajan como query params; los bodies contienen solo los valores que se persisten."
  - "source conserva local_archive como defecto en los siete endpoints."
  - "WR-06 se corrige en alta y baja de carpetas; ningun handler de lectura reconstruye el registry."

patterns-established:
  - "La API de manga traduce SourceError y KeyError mediante raise_source_http_error."
  - "Toda escritura HTTP del reader se verifica con assert_no_persisted_urls despues de escribir."

requirements-completed: [RD-03, RD-05, RD-06, RD-07]

coverage:
  - id: D1
    description: Un unico endpoint navega series y capitulos, conserva ComicInfo y entrega paginas ordenadas con URLs relativas
    verification:
      - kind: integration
        ref: apps/backend/tests/test_manga_api.py#test_un_endpoint_navega_series_y_capitulos_con_comicinfo y test_paginas_salen_en_orden_natural_con_urls_relativas_y_errores_tipados
        status: pass
    human_judgment: true
    rationale: "Pendiente de verificación por el orquestador fuera del sandbox."
  - id: D2
    description: Las preferencias se aislan por serie y conservan doble pagina y offset al cambiar el modo
    requirement: RD-03
    verification:
      - kind: integration
        ref: apps/backend/tests/test_manga_api.py#test_preferencias_progreso_y_evento_hacen_round_trip_sin_persistir_urls
        status: pass
    human_judgment: true
    rationale: "Pendiente de verificación por el orquestador fuera del sandbox."
  - id: D3
    description: El progreso se guarda y recupera por capitulo
    requirement: RD-05
    verification:
      - kind: integration
        ref: apps/backend/tests/test_manga_api.py#test_preferencias_progreso_y_evento_hacen_round_trip_sin_persistir_urls
        status: pass
    human_judgment: true
    rationale: "Pendiente de verificación por el orquestador fuera del sandbox."
  - id: D4
    description: El evento de lectura conserva un chapter decimal y devuelve su id
    requirement: RD-06
    verification:
      - kind: integration
        ref: apps/backend/tests/test_manga_api.py#test_preferencias_progreso_y_evento_hacen_round_trip_sin_persistir_urls
        status: pass
    human_judgment: true
    rationale: "Pendiente de verificación por el orquestador fuera del sandbox."
  - id: D5
    description: Anadir o borrar una carpeta actualiza LocalArchiveSource inmediatamente sin reconstruir al leer
    verification:
      - kind: integration
        ref: apps/backend/tests/test_manga_api.py#test_alta_y_baja_de_carpeta_refrescan_el_registry_sin_reiniciar
        status: pass
    human_judgment: true
    rationale: "Pendiente de verificación por el orquestador fuera del sandbox."
  - id: D6
    description: Los endpoints conservan 404, 415, 429, 502 y 503 y la guardia FND-05 revisa escrituras reales
    verification:
      - kind: integration
        ref: apps/backend/tests/test_manga_api.py#test_los_endpoints_de_fuente_no_convierten_errores_tipados_en_500 y test_preferencias_progreso_y_evento_hacen_round_trip_sin_persistir_urls
        status: pass
    human_judgment: true
    rationale: "Pendiente de verificación por el orquestador fuera del sandbox."

duration: unknown
completed: 2026-07-16
status: complete
---

# Phase 03 Plan 04: API local de manga y registry vivo Summary

**Siete endpoints `/api/manga/*` sobre SourceEngine y SQLite, con URLs relativas y carpetas visibles sin reiniciar.**

## Performance

- **Duration:** unknown
- **Started:** unknown
- **Completed:** 2026-07-16
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments

- La biblioteca se navega con `GET /api/manga/chapters`; `is_chapter` y `number` llegan como datos del contrato de fuente.
- Las paginas salen por `GET /api/manga/pages` en orden natural y con URLs `/assets/pages/...` relativas.
- Preferencias, progreso y eventos tienen round-trip HTTP sobre las tablas v9 y conservan su granularidad por serie o capitulo.
- Los errores de fuente se traducen a respuestas tipadas y las escrituras se cubren con la guardia FND-05.
- Alta y baja de carpetas reconstruyen el registry en el punto de mutacion, saldando WR-06 sin hacerlo por peticion de lectura.

## Contrato HTTP

| Metodo y ruta | Query | Body | Respuesta |
|---|---|---|---|
| `GET /api/manga/chapters` | `source=local_archive`, `series_id` | - | `MangaChapter[]` |
| `GET /api/manga/pages` | `source=local_archive`, `chapter_id` | - | `MangaPage[]` |
| `GET /api/manga/prefs` | `source=local_archive`, `series_id` | - | `ReaderPrefs \| null` |
| `PUT /api/manga/prefs` | `source=local_archive`, `series_id` | campos parciales de `ReaderPrefsUpdate` | `ReaderPrefs` persistido |
| `GET /api/manga/progress` | `source=local_archive`, `chapter_id` | - | `ReaderProgress \| null` |
| `PUT /api/manga/progress` | `source=local_archive`, `chapter_id` | `{ "page": int }` | `204` |
| `POST /api/manga/reading-events` | `source=local_archive`, `series_id`, `chapter_id` | `{ "chapter": float \| null }` | `{ "id": int }` |

`ReaderPrefsUpdate` admite `mode`, `fit`, `double_page` y `double_page_offset` como campos opcionales. Una actualizacion parcial no borra los valores anteriores.

## Task Commits

- `d3a8008` feat(03-04): manga reader API and static registry refresh (WR-06)
- `718204d` test(03-04): cover manga API navigation, persistence, typed errors and WR-06
- `docs(03-04)`: este SUMMARY (commit de cierre)

## Files Created/Modified

- `apps/backend/nyanko_api/models.py` - modelos Pydantic del contrato HTTP del reader.
- `apps/backend/nyanko_api/main.py` - siete rutas planas y refresco del registry en alta/baja de carpetas.
- `apps/backend/tests/test_manga_api.py` - navegacion, paginas, persistencia, errores, FND-05 y WR-06.
- `.planning/phases/03-page-pipe-lectura-local-la-piedra-angular/03-04-SUMMARY.md` - cierre del plan pendiente del gate externo.

## Decisions Made

- Los ids opacos quedan en query params; ninguna ruta acepta un path del sistema de ficheros.
- El body de preferencias es parcial y reutiliza el upsert del plan 02 para conservar campos ausentes.
- El body del evento solo declara `chapter`; la identidad queda en query params y nadie consume el evento hasta la Fase 5.

## Deviations from Plan

Ninguna: el plan se implemento dentro de los cuatro ficheros autorizados.

## Issues Encountered

- No se ejecuto pytest ni ningun runner por la prohibicion expresa de `CODEX-RULES.md`.
- No se hicieron commits ni se actualizaron `STATE.md`, `ROADMAP.md` o `REQUIREMENTS.md`; corresponden al orquestador.
- La secuencia RED/GREEN no puede verificarse dentro de este sandbox; los tests quedaron escritos para el gate externo.

## Self-Check: pass

Suite ejecutada por el orquestador fuera del sandbox: **447 passed, 1 warning** en 109.16s
(`.venv/Scripts/python -m pytest`). Baseline tras 03-03 era 440 → +7 tests netos del plan.

## User Setup Required

Ninguno.

## Next Phase Readiness

El contrato HTTP que consumira el cliente del plan 03-05 queda definido e implementado, pendiente de verificacion por el orquestador.

---
*Phase: 03-page-pipe-lectura-local-la-piedra-angular*
*Completed: 2026-07-16*
