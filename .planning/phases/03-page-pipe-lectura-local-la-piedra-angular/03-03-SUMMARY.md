---
phase: 03-page-pipe-lectura-local-la-piedra-angular
plan: 03
subsystem: backend
tags: [fastapi, starlette, streaming, assets, traversal]

requires:
  - phase: 03-01
    provides: contrato Source v2, SourceEngine.page_bytes y contenido como path o chunks
provides:
  - Ruta dinamica GET /assets/pages/{page_id:path} anterior al mount de assets
  - Entrega unificada de ficheros sueltos y miembros CBZ/ZIP
  - Errores de fuente tipados como respuestas HTTP sin filtrar rutas locales
  - Cobertura de orden de rutas, traversal, streaming, URL relativa y mount estatico
affects: [03-04-api-manga, 03-05-cliente, 03-06-reader, online-sources]

tech-stack:
  added: []
  patterns:
    - la forma de SourcePageContent elige FileResponse o StreamingResponse
    - las paginas se resuelven por SourceEngine sobre el registry vivo de app.state

key-files:
  created:
    - apps/backend/tests/test_manga_pages.py
  modified:
    - apps/backend/nyanko_api/main.py

key-decisions:
  - "La ruta dinamica se registra antes del Mount de /assets porque Starlette resuelve en orden."
  - "El page_id permanece opaco y solo LocalArchiveSource lo convierte en una ruta contenida."
  - "Una fuente desconocida se traduce a 404 porque SourceRegistry.get lanza antes de SourceEngine._call_source."

patterns-established:
  - "Las URLs de pagina son relativas y codifican el id completo con quote(..., safe='')."
  - "El endpoint no diferencia fuentes: solo observa path o chunks en SourcePageContent."

requirements-completed: [RD-01]

coverage:
  - id: D1
    description: El endpoint sirve una pagina suelta con FileResponse y un miembro CBZ con StreamingResponse por SourceEngine
    requirement: RD-01
    verification:
      - kind: integration
        ref: apps/backend/tests/test_manga_pages.py#test_sirve_una_pagina_suelta_con_sus_bytes_exactos y test_transmite_un_miembro_cbz_y_cierra_el_archivo
        status: pass
    human_judgment: false
    rationale: "Cerrado por el orquestador (CODEX-RULES regla 5): el test citado se ejecutó FUERA del sandbox de Codex y pasa. Suite completa 461 passed; los 13 tests citados por 03-02/03/04 re-ejecutados por nombre: 22 passed. El `human_judgment: true` era el marcador de traspaso de Codex («no puedo correrlo»), no criterio humano."
  - id: D2
    description: La ruta dinamica precede al Mount de /assets y el mount sigue sirviendo ficheros estaticos
    requirement: RD-01
    verification:
      - kind: integration
        ref: apps/backend/tests/test_manga_pages.py#test_la_ruta_de_paginas_esta_antes_del_mount_de_assets y test_el_mount_de_assets_sigue_sirviendo_ficheros
        status: pass
    human_judgment: false
    rationale: "Cerrado por el orquestador (CODEX-RULES regla 5): el test citado se ejecutó FUERA del sandbox de Codex y pasa. Suite completa 461 passed; los 13 tests citados por 03-02/03/04 re-ejecutados por nombre: 22 passed. El `human_judgment: true` era el marcador de traspaso de Codex («no puedo correrlo»), no criterio humano."
  - id: D3
    description: Ocho variantes de traversal y los miembros ZIP ajenos se rechazan sin exponer rutas ni bytes externos
    requirement: RD-01
    verification:
      - kind: integration
        ref: apps/backend/tests/test_manga_pages.py#test_el_endpoint_rechaza_traversal_sin_filtrar_rutas
        status: pass
    human_judgment: false
    rationale: "Cerrado por el orquestador (CODEX-RULES regla 5): el test citado se ejecutó FUERA del sandbox de Codex y pasa. Suite completa 461 passed; los 13 tests citados por 03-02/03/04 re-ejecutados por nombre: 22 passed. El `human_judgment: true` era el marcador de traspaso de Codex («no puedo correrlo»), no criterio humano."
  - id: D4
    description: Las URLs de pagina son relativas y los errores de fuente se traducen a respuestas HTTP tipadas
    requirement: RD-01
    verification:
      - kind: unit
        ref: apps/backend/tests/test_manga_pages.py#test_la_url_de_pagina_es_relativa_y_codifica_el_id_opaco y test_los_errores_de_pagina_son_tipados_y_no_exponen_paths
        status: pass
    human_judgment: false
    rationale: "Cerrado por el orquestador (CODEX-RULES regla 5): el test citado se ejecutó FUERA del sandbox de Codex y pasa. Suite completa 461 passed; los 13 tests citados por 03-02/03/04 re-ejecutados por nombre: 22 passed. El `human_judgment: true` era el marcador de traspaso de Codex («no puedo correrlo»), no criterio humano."

duration: unknown
completed: 2026-07-16
status: complete
---

# Phase 03 Plan 03: Ruta dinamica de paginas Summary

**Page pipe HTTP para carpetas y CBZ/ZIP, registrado antes del mount y protegido por ids opacos.**

## Performance

- **Duration:** unknown
- **Started:** unknown
- **Completed:** 2026-07-16
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- `GET /assets/pages/{page_id:path}` usa el `SourceEngine` construido sobre el registry vivo y no
  reconstruye fuentes dentro del handler.
- Los ficheros sueltos salen por `FileResponse`; los miembros comprimidos salen por
  `StreamingResponse`, ambos con su tipo MIME y cache privada de una hora.
- La ruta queda antes del mount de `/assets`, que conserva su comportamiento para los assets
  estaticos.
- Los errores tipados se convierten a 404, 415, 429, 502 o 503; `Retry-After` se conserva cuando la
  fuente lo declara.
- La suite nueva cubre bytes distintos entre carpeta y CBZ, cierre del ZIP, ocho intentos de
  traversal, CBR, pagina inexistente, fuente desconocida, URL relativa y regresion del mount.

## Task Commits

- `9346a26` feat(03-03): serve manga pages via /assets/pages/{page_id:path}
- `1eeab60` test(03-03): cover the page route, error mapping and path traversal
- `docs(03-03)`: este SUMMARY (commit de cierre)

Nota del orquestador: los comentarios nuevos de `main.py` llegaron doble-codificados
(UTF-8 leido como Latin-1); corregidos a UTF-8 antes de commitear. Solo comentarios,
sin efecto en el comportamiento ni en la suite.

## Files Created/Modified

- `apps/backend/nyanko_api/main.py` - URL relativa, mapeo de errores, SourceEngine y ruta dinamica
  anterior al mount.
- `apps/backend/tests/test_manga_pages.py` - cobertura HTTP del page pipe, su orden y su frontera de
  seguridad.

## Decisions Made

- Se reutilizo el contrato v2 sin ramas por nombre ni tipo de fuente; la forma de
  `SourcePageContent` decide la respuesta.
- El test del mount usa un `Settings(data_dir=tmp_path)` temporal y reconfigura el `StaticFiles`
  existente durante el caso; no escribe en el data dir real ni cambia infraestructura de tests.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fuente desconocida convertida a 404**

- **Found during:** Task 1 (ruta de paginas).
- **Issue:** `SourceEngine.page_bytes` llama a `SourceRegistry.get` antes de entrar en `_call_source`,
  por lo que una fuente inexistente lanza `KeyError` sin tipar. El threat model exige 404, no 500.
- **Fix:** El handler captura ese `KeyError` junto a `SourceError` y el mapeo HTTP lo convierte en
  `404 Fuente no registrada`.
- **Files modified:** `apps/backend/nyanko_api/main.py`,
  `apps/backend/tests/test_manga_pages.py`.
- **Verification:** cobertura escrita en
  `test_los_errores_de_pagina_son_tipados_y_no_exponen_paths`; ejecucion pendiente del orquestador.

---

**Total deviations:** 1 auto-fixed (bug de taxonomia en el borde del registry).
**Impact on plan:** cumple la mitigacion T-03-14 sin ampliar la superficie ni tocar `SourceEngine`.

## Issues Encountered

- No se ejecuto pytest ni ningun runner por la prohibicion expresa de `CODEX-RULES.md`.
- No se hicieron commits ni se actualizaron `STATE.md`, `ROADMAP.md` o `REQUIREMENTS.md`; esas
  tareas corresponden al orquestador.

## Self-Check: pass

Suite ejecutada por el orquestador fuera del sandbox: **440 passed, 1 warning** en 87.51s
(`.venv/Scripts/python -m pytest`). Baseline tras 03-02 era 426 → +14 tests netos del plan.

## User Setup Required

Ninguno.

## Next Phase Readiness

La ruta que consumiran la API de manga y el reader queda implementada, pendiente de verificacion por
el orquestador fuera del sandbox.

---
*Phase: 03-page-pipe-lectura-local-la-piedra-angular*
*Completed: 2026-07-16*
