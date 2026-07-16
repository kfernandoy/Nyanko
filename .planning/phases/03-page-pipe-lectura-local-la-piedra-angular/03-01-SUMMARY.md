---
phase: 03-page-pipe-lectura-local-la-piedra-angular
plan: 01
subsystem: backend
tags: [sources, contract, cbz, zip, comicinfo, streaming]

requires:
  - phase: 02-motor-de-fuentes-contrato-presupuesto-y-taxonom-a-de-errores
    provides: contrato Source versionado, registro explicito, SourceEngine y errores tipados
provides:
  - Contrato Source v2 con page_bytes y SourcePageContent
  - LocalArchiveSource para carpetas, CBZ y ZIP con orden natural
  - Metadatos ComicInfo.xml seguros y bytes de pagina como path o chunks
  - SourceEngine exportado por la superficie publica del paquete
affects: [page-pipe, reader, online-sources, downloads]

tech-stack:
  added: []
  patterns:
    - la forma fisica del contenido elige path o chunks sin ramas por fuente
    - los miembros ZIP se transmiten con un generador que posee y cierra sus recursos

key-files:
  created: []
  modified:
    - apps/backend/nyanko_api/sources/contract.py
    - apps/backend/nyanko_api/sources/local_archive.py
    - apps/backend/nyanko_api/sources/engine.py
    - apps/backend/nyanko_api/sources/__init__.py
    - apps/backend/tests/test_sources.py
    - apps/backend/tests/test_source_api.py
    - apps/backend/tests/test_source_budget.py
    - apps/backend/tests/test_source_engine.py

key-decisions:
  - "SourcePageContent documenta una unica forma de retorno con exactamente path o chunks; no hay cache ni extraccion a disco."
  - "ComicInfo.xml se descarta antes del parser si declara DTD/entidades o supera 1 MB dentro del ZIP."
  - "El id de un miembro conserva el id opaco del archivo y agrega ! seguido del nombre exacto del miembro."

patterns-established:
  - "El contenido de disco se expone como Path y el contenido comprimido como Iterator[bytes] de 64 KB."
  - "La contencion de rutas sigue centralizada en LocalArchiveSource._resolve_id."

requirements-completed: [RD-01, RD-08]

coverage:
  - id: D1
    description: El contrato Source v2 expone page_bytes y SourcePageContent; SourceEngine lo delega por _call_source
    requirement: RD-01
    verification:
      - kind: unit
        ref: apps/backend/tests/test_sources.py y apps/backend/tests/test_source_engine.py
        status: pass
    human_judgment: false
  - id: D2
    description: Carpetas, CBZ y ZIP producen paginas en orden natural y sirven bytes sin extraer a disco
    requirement: RD-01
    verification:
      - kind: unit
        ref: apps/backend/tests/test_sources.py
        status: pass
    human_judgment: false
  - id: D3
    description: ComicInfo.xml manda sobre el nombre y se degrada con seguridad ante XML roto, peligroso o desmedido
    requirement: RD-08
    verification:
      - kind: unit
        ref: apps/backend/tests/test_sources.py
        status: pass
    human_judgment: false
  - id: D4
    description: Los dobles de fuente de la Fase 2 cumplen el cuarto metodo del contrato v2
    verification:
      - kind: integration
        ref: apps/backend/tests/test_source_api.py, test_source_budget.py y test_source_engine.py
        status: pass
    human_judgment: false

duration: unknown
completed: 2026-07-16
status: complete
---

# Phase 03 Plan 01: Contrato v2 y lectura local Summary

**Contrato de paginas con bytes, lectura unificada de carpetas/CBZ/ZIP y ComicInfo.xml seguro.**

## Accomplishments

- `contract.py` sube la API a v2, agrega `page_bytes`, `SourcePageContent` y los datos
  `SourceChapter.number` / `is_chapter`.
- `local_archive.py` lista y lee carpetas, CBZ y ZIP en orden natural; detecta CBR/RAR sin abrirlos,
  aplica `ComicInfo.xml` sobre el nombre y bloquea DTD, entidades y sidecars mayores de 1 MB.
- Las paginas sueltas salen como `path`; los miembros ZIP salen como `chunks` de 64 KB cuyo generador
  abre y cierra tanto el ZIP como el miembro.
- `SourceEngine.page_bytes` conserva la taxonomia de errores por `_call_source`, y `SourceEngine` queda
  exportado desde `nyanko_api.sources`.
- Los cuatro dobles de fuente y los tests de contrato quedan actualizados para la API v2.

## Task Commits

- `5444151` feat(03-01): source contract v2 with page_bytes and local CBZ/ZIP reading
- `7a60642` test(03-01): adapt source suite to contract v2
- `docs(03-01)`: este SUMMARY (commit de cierre)

## Files Created/Modified

- `apps/backend/nyanko_api/sources/contract.py` - contrato v2 y tipos de contenido/capitulo.
- `apps/backend/nyanko_api/sources/engine.py` - delegacion tipada de `page_bytes`.
- `apps/backend/nyanko_api/sources/__init__.py` - exportaciones publicas del engine y del contenido.
- `apps/backend/nyanko_api/sources/local_archive.py` - CBZ/ZIP, ComicInfo.xml y lectura de bytes.
- `apps/backend/tests/test_sources.py` - contrato v2, archivos locales, seguridad y streaming.
- `apps/backend/tests/test_source_api.py` - doble de API compatible con v2.
- `apps/backend/tests/test_source_budget.py` - doble con fetcher compatible con v2.
- `apps/backend/tests/test_source_engine.py` - doble de cache y delegacion compatibles con v2.

## Decisions Made

- Se siguio el plan: stdlib (`zipfile`, `mimetypes`, `xml.etree`) y las funciones existentes
  `_natural_key` / `_resolve_id`; no se agregaron dependencias, cache ni extraccion temporal.
- La pertenencia exacta a `namelist()` valida miembros antes de abrirlos; no se normaliza ni extrae
  ninguna ruta interna del ZIP.

## Deviations from Plan

Ninguna: el plan se ejecuto segun lo especificado.

## Issues Encountered

- La ejecucion de la suite y los commits quedan pendientes del orquestador por las reglas obligatorias
  del sandbox. No se modifico infraestructura de tests ni el mecanismo de temporales.

## Self-Check: pass

Suite ejecutada por el orquestador fuera del sandbox: **420 passed, 1 warning** en 122.70s
(`.venv/Scripts/python -m pytest`). Baseline Fase 2 era 407 → +13 tests netos del plan.

## Next Phase Readiness

El contrato v2 y el adapter local quedan listos para que el plan 03-03 construya la ruta dinamica de
paginas sobre `SourceEngine.page_bytes`, sujeto a la verificacion externa del orquestador.

---
*Phase: 03-page-pipe-lectura-local-la-piedra-angular*
*Completed: 2026-07-16*
