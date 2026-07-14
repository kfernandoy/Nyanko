---
phase: 02-motor-de-fuentes-contrato-presupuesto-y-taxonom-a-de-errores
plan: 01
subsystem: backend
tags: [sources, contract, errors, registry]

requires: []
provides:
  - Protocol Source versionado (search/chapters/pages) y SourceCapabilities
  - Tipos propios del motor: SourceSeries / SourceChapter / SourcePage
  - Taxonomia de errores tipados (SourceError y subclases)
  - Registro explicito con rechazo por version y LocalArchiveSource
affects: [sources, reader]

tech-stack:
  added: []
  patterns:
    - registro explicito de fuentes con rechazo visible en vez de fallo silencioso
    - capacidades declarativas por fuente (headers, requests_per_minute) como dato

key-files:
  created:
    - apps/backend/nyanko_api/sources/__init__.py
    - apps/backend/nyanko_api/sources/contract.py
    - apps/backend/nyanko_api/sources/errors.py
    - apps/backend/nyanko_api/sources/registry.py
    - apps/backend/nyanko_api/sources/local_archive.py
    - apps/backend/tests/test_sources.py
  modified: []

key-decisions:
  - "D-01: el Protocol Source expone exactamente search/chapters/pages; lo que una fuente NO hace se declara en SourceCapabilities (frozen dataclass), no con NotImplementedError."
  - "D-03: SourceSeries/SourceChapter/SourcePage son tipos del motor y viven separados de los modelos Pydantic del tracker."
  - "D-12: el mensaje al usuario se deriva del TIPO de error, no de str(exc)."
  - "D-13: SOURCE_API_VERSION es un entero con coincidencia exacta; una fuente con version distinta se rechaza pero queda visible con rejection_reason y el sidecar sigue arrancando."

patterns-established:
  - "Los tests se parametrizan sobre el registro SOURCES real, asi que una fuente nueva que viole el Protocol rompe la suite sola."

requirements-completed: [SRC-04, SRC-05, SRC-07]

coverage:
  - id: D1
    description: Una fuente con api_version distinta se rechaza al registrar y queda visible como rejected
    requirement: SRC-04
    verification:
      - kind: unit
        ref: apps/backend/tests/test_sources.py
        status: passed
    human_judgment: false
    rationale: "Verificado por el orquestador fuera del sandbox."
  - id: D2
    description: Los tests parametrizan sobre SOURCES reales y fallan si una fuente no cumple el Protocol
    requirement: SRC-04
    verification:
      - kind: unit
        ref: apps/backend/tests/test_sources.py
        status: passed
    human_judgment: false
    rationale: "17/17 en test_sources.py; 383 passed en la suite completa."
  - id: D3
    description: Cada fuente declara headers y requests_per_minute como dato, sin logica if source.name == ...
    requirement: SRC-05
    verification:
      - kind: unit
        ref: apps/backend/tests/test_sources.py
        status: passed
    human_judgment: false
    rationale: "Verificado por el orquestador fuera del sandbox."

duration: unknown
completed: 2026-07-13
status: complete
---

# Phase 02 Plan 01: Base del motor de fuentes Summary

**Contrato versionado, errores tipados, registro explicito y primera fuente (archivo local).**

## Accomplishments

- `contract.py`: Protocol `Source` con exactamente `search()` / `chapters()` / `pages()`, `SourceCapabilities`
  (frozen) y los tipos propios del motor. `SOURCE_API_VERSION = 1` (entero).
- `errors.py`: taxonomia tipada — `SourceError` y subclases `SourceNetworkError`, `SourceParseError`,
  `SourceRateLimitError`, `SourceNotFoundError`, `SourceUnsupportedError`.
- `registry.py`: registro explicito; una fuente con `api_version` distinta se rechaza pero queda visible
  (`status == "rejected"` + `rejection_reason`) sin tumbar el sidecar.
- `local_archive.py`: `LocalArchiveSource`, primera implementacion del contrato.
- `test_sources.py`: parametrizado sobre el registro `SOURCES` real.

## Task Commits

Codex no puede escribir en `.git` desde su sandbox (`workspace-write`), asi que los commits los hizo
el orquestador tras verificar la suite fuera del sandbox:

- `07ca9be` feat(02-01): source engine foundation — versioned contract, typed errors, explicit registry, local archive source
- `cc4003f` test(02-01): parametrize source contract tests over the real SOURCES registry

## Deviations from Plan

- **Test degradado y revertido por el orquestador.** Al no poder ejecutar pytest en su sandbox (el TEMP del
  sistema esta denegado y el fixture `tmp_path` revienta), Codex reescribio el helper `_workdir()` para usar
  `Path(".test-work")`: una ruta relativa dependiente del cwd que ensucia el repo. El orquestador lo revirtio a
  `tempfile.TemporaryDirectory()` (stdlib) antes de commitear. De ahi salio `.planning/CODEX-RULES.md`.

## Issues Encountered

- El sandbox de Codex (`workspace-write`) deniega tanto el TEMP del sistema (rompe pytest) como `.git`
  (impide commitear). Ambas cosas estan ahora documentadas en `.planning/CODEX-RULES.md`.

## Self-Check: PASSED

Suite completa ejecutada por el orquestador fuera del sandbox: **383 passed**, con `test_sources.py` en 17/17.

## Next Phase Readiness

El contrato y el registro existen, que es exactamente lo que el plan 02-02 necesita para hacer al motor
dueño del presupuesto.

---
*Phase: 02-motor-de-fuentes-contrato-presupuesto-y-taxonom-a-de-errores*
*Completed: 2026-07-13*
