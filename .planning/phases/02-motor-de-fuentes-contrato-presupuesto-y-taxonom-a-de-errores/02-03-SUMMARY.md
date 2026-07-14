---
phase: 02-motor-de-fuentes-contrato-presupuesto-y-taxonom-a-de-errores
plan: 03
subsystem: backend
tags: [sources, api, packaging, fastapi]

requires:
  - phase: 02-01
    provides: contrato, errores tipados, registro con rechazo por version
  - phase: 02-02
    provides: SourceEngine dueño del presupuesto
provides:
  - Endpoint GET /api/sources con fuentes aceptadas Y rechazadas
  - SourceInfo / SourceCapabilitiesResponse en models.py
  - Guardia contra registro vacio en el sidecar empaquetado (PyInstaller onedir)
affects: [sources, api, renderer, packaging]

tech-stack:
  added: []
  patterns:
    - el rechazo de una fuente es dato visible via API, no un fallo silencioso

key-files:
  created:
    - apps/backend/tests/test_source_api.py
    - apps/backend/tests/test_packaged_sources.py
  modified:
    - apps/backend/nyanko_api/models.py
    - apps/backend/nyanko_api/main.py

key-decisions:
  - "SourceInfo.status es Literal['ok','rejected'] con rejection_reason opcional: una fuente rechazada por api_version sigue siendo visible para el renderer en vez de desaparecer."
  - "El motor no añade ninguna capa de persistencia nueva detras de la API; hay un test que lo guarda."

patterns-established:
  - "El test de empaquetado ejercita el sidecar YA empaquetado, no el arbol de desarrollo: es la unica forma de detectar que PyInstaller onedir (sin autodiscovery) deje el registro vacio en produccion."

requirements-completed: [SRC-04, SRC-06]

coverage:
  - id: D1
    description: GET /api/sources lista fuentes aceptadas y rechazadas, con rejection_reason
    requirement: SRC-04
    verification:
      - kind: unit
        ref: apps/backend/tests/test_source_api.py
        status: passed
    human_judgment: false
    rationale: "Verificado por el orquestador fuera del sandbox: suite completa 399 passed."
  - id: D2
    description: El sidecar empaquetado expone un registro de fuentes no vacio
    requirement: SRC-06
    verification:
      - kind: integration
        ref: apps/backend/tests/test_packaged_sources.py#test_packaged_sources_endpoint_is_not_empty
        status: passed
    human_judgment: false
    rationale: "Verificado por el orquestador fuera del sandbox."
  - id: D3
    description: El motor no introduce persistencia nueva
    requirement: SRC-06
    verification:
      - kind: unit
        ref: apps/backend/tests/test_source_api.py
        status: passed
    human_judgment: false
    rationale: "Verificado por el orquestador fuera del sandbox."

duration: unknown
completed: 2026-07-13
status: complete
---

# Phase 02 Plan 03: Motor de fuentes expuesto al renderer Summary

**`GET /api/sources` con fuentes aceptadas y rechazadas, y la trampa de empaquetado cerrada.**

## Accomplishments

- `models.py`: `SourceInfo` (con `status: "ok" | "rejected"` y `rejection_reason`) y `SourceCapabilitiesResponse`.
- `main.py`: endpoint `GET /api/sources`. Una fuente rechazada por `api_version` **sigue siendo visible**
  para el renderer con su motivo, en vez de desaparecer sin dejar rastro.
- `test_source_api.py`: cubre el listado (aceptadas + rechazadas) y guarda que el motor no mete persistencia nueva.
- `test_packaged_sources.py`: ejercita el sidecar **ya empaquetado**. PyInstaller onedir no hace autodiscovery,
  asi que un registro que funciona en desarrollo puede venir vacio en produccion; este test falla si eso pasa.

## Task Commits

Codex no puede escribir en `.git` desde su sandbox, asi que los commits los hizo el orquestador tras
verificar la suite fuera del sandbox (mapeo tarea→fichero reportado por Codex):

- `fbbbb90` feat(02-03): expose the source engine over /api/sources
- `3febdad` test(02-03): cover the sources endpoint and guard against new persistence
- `0d0040e` test(02-03): packaged sidecar must expose a non-empty source registry

## Deviations from Plan

- **El SUMMARY lo escribio el orquestador.** El brief de Codex restringia el alcance a los 4 ficheros de
  `files_modified`, lo que contradecia la peticion de crear el SUMMARY (un quinto fichero). Codex detecto la
  contradiccion, se nego a resolverla por su cuenta y la reporto. Fallo del brief, no de Codex.

## Issues Encountered

- Ninguno en el codigo. Los bloqueos fueron de entorno (sandbox de Codex), ya documentados en
  `.planning/CODEX-RULES.md`.

## Self-Check: PASSED

Suite completa ejecutada por el orquestador fuera del sandbox: **399 passed** (393 antes de este plan,
+6 de los dos ficheros de test nuevos). Sin regresiones.

## Next Phase Readiness

El motor de fuentes esta completo y expuesto: contrato versionado, presupuesto propio, errores tipados y
API visible al renderer, con el empaquetado guardado por un test. La Fase 3 puede construir encima.

---
*Phase: 02-motor-de-fuentes-contrato-presupuesto-y-taxonom-a-de-errores*
*Completed: 2026-07-13*
