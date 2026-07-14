---
phase: 02-motor-de-fuentes-contrato-presupuesto-y-taxonom-a-de-errores
plan: 02
subsystem: backend
tags: [sources, rate-limit, cache, httpx]

requires:
  - phase: 02-01
    provides: contrato de fuentes, errores tipados, registro base y LocalArchiveSource
provides:
  - SourceEngine con fetcher generico, cache buena en memoria y traduccion de errores
  - DefaultSourceFetcher que aplica headers declarados por fuente
  - RateLimitedClient con admision por prioridad para lectura antes que descarga
  - Tests de presupuesto compartido, prioridad, headers y cache buena
affects: [sources, reader, downloads]

tech-stack:
  added: []
  patterns:
    - un RateLimitedClient por fuente construido por el registro
    - cache buena de capitulos en memoria, sin persistencia

key-files:
  created:
    - apps/backend/nyanko_api/sources/engine.py
    - apps/backend/tests/test_source_budget.py
    - apps/backend/tests/test_source_engine.py
  modified:
    - apps/backend/nyanko_api/http.py
    - apps/backend/nyanko_api/sources/registry.py

key-decisions:
  - "El fetcher por fuente se construye desde SourceCapabilities y reutiliza RateLimitedClient; no hay limitador nuevo en sources/."
  - "La prioridad vive en http.py como cola de admision, manteniendo el sleep de ritmo fuera del semaforo."
  - "La cache de capitulos es de proceso, sin TTL/LRU ni SQLite; persistirla queda diferido a Fase 8."

patterns-established:
  - "DefaultSourceFetcher mergea headers declarados con headers de request y delega en RateLimitedClient."
  - "SourceEngine devuelve cache buena ante SourceError y solo escribe cache en camino feliz."

requirements-completed: [SRC-05, SRC-06, SRC-07]

coverage:
  - id: D1
    description: Fetcher generico aplica headers declarados por fuente y el registro crea un bucket por fuente
    requirement: SRC-05
    verification:
      - kind: unit
        ref: apps/backend/tests/test_source_budget.py#test_source_fetcher_applies_declared_headers
        status: passed
      - kind: unit
        ref: apps/backend/tests/test_source_budget.py#test_registry_builds_one_rate_limited_fetcher_per_source
        status: passed
    human_judgment: false
    rationale: "Verificado por el orquestador fuera del sandbox: suite completa 393 passed."
  - id: D2
    description: Dos consumidores de una fuente comparten el mismo bucket y lectura adelanta descarga
    requirement: SRC-06
    verification:
      - kind: unit
        ref: apps/backend/tests/test_source_budget.py#test_consumers_share_one_source_bucket
        status: passed
      - kind: unit
        ref: apps/backend/tests/test_source_budget.py#test_read_priority_overtakes_queued_downloads
        status: passed
    human_judgment: false
    rationale: "Verificado por el orquestador fuera del sandbox: suite completa 393 passed."
  - id: D3
    description: Cache buena de capitulos sobrevive errores y errores HTTP se traducen a SourceError tipados
    requirement: SRC-07
    verification:
      - kind: unit
        ref: apps/backend/tests/test_source_engine.py
        status: passed
    human_judgment: false
    rationale: "Verificado por el orquestador fuera del sandbox: suite completa 393 passed."

duration: unknown
completed: 2026-07-13
status: complete
---

# Phase 02 Plan 02: Motor de fuentes con presupuesto propio Summary

**Motor de fuentes con bucket por fuente, headers declarativos, prioridad de lectura y cache buena de capitulos.**

## Performance

- **Duration:** unknown
- **Started:** 2026-07-13T20:38:09-04:00
- **Completed:** 2026-07-13T20:38:09-04:00
- **Tasks:** 3 implementadas en el arbol de trabajo
- **Files modified:** 6, mas este SUMMARY

## Accomplishments

- `DefaultSourceFetcher` aplica headers declarados por `SourceCapabilities` y delega en `RateLimitedClient`.
- `build_source_registry()` crea un fetcher/bucket por fuente cuando no recibe fetcher de test.
- `RateLimitedClient.request()` acepta `priority` y asigna slots con heap de prioridad antes del sleep.
- `SourceEngine` cachea la ultima lista buena de capitulos y no la pisa ante `SourceError`.
- Los errores `httpx` relevantes se traducen a `SourceRateLimitError`, `SourceNotFoundError` y `SourceNetworkError`.

## Task Commits

Codex no puede escribir en `.git` desde su sandbox (`workspace-write`), asi que los commits
los hizo el orquestador tras verificar la suite fuera del sandbox:

- `04b26d8` feat(02-02): priority-aware waiter queue in the HTTP rate limiter
- `d419ac4` feat(02-02): the source engine owns the budget, not the clients
- `6b2dfcb` test(02-02): cover budget ownership and engine dispatch

## Files Created/Modified

- `apps/backend/nyanko_api/http.py` - agrega admision por prioridad al limitador existente.
- `apps/backend/nyanko_api/sources/engine.py` - agrega fetcher, builder de fetcher y motor de cache/errores.
- `apps/backend/nyanko_api/sources/registry.py` - construye e inyecta fetcher por fuente al registrar desde builder.
- `apps/backend/tests/test_source_budget.py` - cubre bucket compartido, techo, headers y prioridad.
- `apps/backend/tests/test_source_engine.py` - cubre cache buena y traduccion de errores.

## Decisions Made

- Se reutilizo `RateLimitedClient`; no se escribio limitador nuevo en `sources/`.
- La cache queda como `dict` de proceso, sin persistencia ni invalidacion avanzada.
- `fetcher` inyectado por tests sigue siendo override explicito para mantener compatibilidad de la suite existente.

## Deviations from Plan

None - plan executed exactly as written at code level.

## Issues Encountered

- El sandbox no permite escribir en `.git`, por lo que no se pudieron hacer commits atomicos, commitear este SUMMARY ni actualizar el roadmap como complete.
- No se ejecuto pytest por contrato local; self-check: pendiente de verificación por el orquestador.

## Self-Check: PASSED

Suite completa ejecutada por el orquestador fuera del sandbox: **393 passed** (383 antes de este plan,
+10 de los dos ficheros de test nuevos). Sin regresiones. Commits creados por el orquestador.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Cerrado. Codigo commiteado y suite verde (393 passed). El motor ya es dueño del presupuesto,
que es lo que el plan 02-03 necesita para exponerlo al renderer.

---
*Phase: 02-motor-de-fuentes-contrato-presupuesto-y-taxonom-a-de-errores*
*Completed: 2026-07-13*
