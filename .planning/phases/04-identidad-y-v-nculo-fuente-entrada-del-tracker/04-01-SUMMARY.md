---
phase: 04-identidad-y-v-nculo-fuente-entrada-del-tracker
plan: 01
subsystem: backend
tags: [chapter-recognition, manga, local-archive, tdd]

requires:
  - phase: 03-page-pipe-lectura-local-la-piedra-angular
    provides: LocalArchiveSource y metadatos ComicInfo.xml para capitulos locales
provides:
  - componente puro recognize_chapter con la tabla de casos del plan
  - reconocimiento de extras, omake, especiales, decimales y sufijos alfabeticos
  - LocalArchiveSource delegado al unico reconocedor de capitulos
affects: [phase-05-sync-progreso, local-archive, manga-reader]

tech-stack:
  added: []
  patterns:
    - el reconocimiento de capitulos falla cerrado ante nombres sin numero o ambiguos
    - el adaptador local delega la interpretacion y solo aporta contexto del fichero y la serie

key-files:
  created:
    - apps/backend/tests/test_chapter_recognition.py
    - apps/backend/nyanko_api/chapter_recognition.py
  modified:
    - apps/backend/nyanko_api/sources/local_archive.py

key-decisions:
  - "Los marcadores explicitos de capitulo ganan; sin marcador, mas de un numero devuelve None."
  - "Los archivos se reconocen desde path.stem y reciben el nombre de la carpeta de serie; ComicInfo Number se interpreta sin titulo de serie."
  - "Los sufijos extra, omake y special ocupan .99, .98 y .97 para quedar despues del capitulo base y antes del siguiente."

patterns-established:
  - "Una sola implementacion pura para reconocer numeros de capitulo; los motores de fuentes delegan."

requirements-completed: [LNK-03]

coverage:
  - id: D1
    description: recognize_chapter expone la firma pura y cubre la tabla de 14 casos de reconocimiento
    requirement: LNK-03
    verification:
      - kind: unit
        ref: apps/backend/tests/test_chapter_recognition.py
        status: passed
    human_judgment: false
    rationale: "Medido por el orquestador fuera del sandbox: 15 passed. Rojo 9ada90e (exit 2, ModuleNotFoundError) -> verde 3096d27. Los tres casos nombrados del ROADMAP son literales: extra=12.99, omake=12.98, 12a=12.1."
  - id: D2
    description: LocalArchiveSource usa path.stem, descuenta el titulo de serie y conserva la prioridad de ComicInfo Number
    requirement: LNK-03
    verification:
      - kind: integration
        ref: apps/backend/tests/test_sources.py y apps/backend/tests/test_manga_api.py
        status: passed
    human_judgment: false
    rationale: "Medido por el orquestador fuera del sandbox: suite completa 476 passed, 0 failed (baseline Fase 3: 461, +15 de la tabla nueva). La delegacion cambia comportamiento a proposito (Vol.2 Cap 15: 2.0 -> 15; Cap 12 extra: 12.0 -> 12.99) y ningun test existente dependia del comportamiento viejo."
  - id: D3
    description: local_archive.py ya no contiene una implementacion alternativa del reconocimiento
    requirement: LNK-03
    verification:
      - kind: other
        ref: asercion de fuente sobre LocalArchiveSource._chapter_number
        status: passed
    human_judgment: false
    rationale: "Verificado por el orquestador: la regex vieja (re.search(r\"\\d+(?:\\.\\d+)?\", name), local_archive.py:242-244) ya no existe en el fichero; _chapter_number:251 delega en recognize_chapter(name, series_title) importado en :12. No quedan dos implementaciones — esa era la condicion del criterio 3."

duration: ~25min (2 pasadas de Codex + gates del orquestador)
completed: 2026-07-17
status: complete
---

# Phase 04 Plan 01: Reconocimiento propio de capitulos Summary

**Reconocedor puro de numeros de capitulo y archivo local delegado a una sola implementacion.**

## Performance

- **Duration:** ~25min
- **Started:** 2026-07-17
- **Completed:** 2026-07-17
- **Tasks:** 3 del plan; Tasks 2 y 3 ejecutadas en esta sesion
- **Files del plan:** 3

## Accomplishments

- La tabla de la Task 1 queda intacta y `recognize_chapter` materializa su contrato en un modulo
  puro que solo importa `re`.
- El reconocimiento distingue marcadores de volumen y capitulo, decimales explicitos, los tres
  sufijos con nombre y las letras `a` a `i`; sin numero o con varios numeros ambiguos devuelve
  `None`.
- `LocalArchiveSource._chapter_number` delega en el componente nuevo sin conservar la regex vieja;
  los archivos pasan `path.stem`, las carpetas `path.name` y el nombre de la serie se aporta como
  contexto solo cuando corresponde.

## Task Commits

- **Task 1:** tabla de casos ya entregada y commiteada por el orquestador antes de esta sesion.
- **Task 2:** cambios listos; commit pendiente del orquestador.
- **Task 3:** cambios listos; commit pendiente del orquestador.
- **Plan metadata:** pendiente del orquestador.

## Files Created/Modified

- `apps/backend/tests/test_chapter_recognition.py` - tabla de 14 casos creada en la Task 1 y no
  modificada en esta sesion.
- `apps/backend/nyanko_api/chapter_recognition.py` - componente puro de reconocimiento.
- `apps/backend/nyanko_api/sources/local_archive.py` - delegacion y contexto de archivo/serie.

## Decisions Made

- Se siguio el algoritmo fijado por el plan y no se importo `normalizer.py`: este modulo permanece
  aislado de I/O, BD, red y del resto de `nyanko_api`.
- Una letra desde `j` en adelante no suma un decimal; evita convertir, por ejemplo, `12z` en un
  progreso que colisione con otro capitulo real.

## Deviations from Plan

Ninguna. Las Tasks 2 y 3 se ejecutaron dentro de los ficheros declarados y el test de la Task 1 no
se modifico.

## Issues Encountered

- La suite no se ejecuto dentro del sandbox, segun `.planning/CODEX-RULES.md`. La verificacion de
  comportamiento queda pendiente del orquestador.
- `.planning/STATE.md` ya tenia cambios al iniciar esta sesion y se dejo intacto.

## User Setup Required

Ninguno.

## Self-Check: PASSED

Cerrado por el ORQUESTADOR fuera del sandbox del executor (CODEX-RULES reglas 2 y 5: el executor
escribió `unknown`, como debía; los resultados reales los mide y los firma el orquestador).

| Gate | Medido | Resultado |
|------|--------|-----------|
| Tabla de casos en ROJO **antes** del módulo | `pytest tests/test_chapter_recognition.py -q` sobre el árbol de la Task 1 | **exit 2**, `ModuleNotFoundError: No module named 'nyanko_api.chapter_recognition'` → commit `9ada90e` |
| La misma tabla en VERDE tras la Task 2 | mismo comando | **15 passed** → commit `3096d27` |
| Criterio 3, el «antes» como hecho de git | `git merge-base --is-ancestor 9ada90e 3096d27` | **exit 0** — el test es ancestro del módulo |
| Sin regresión en el camino ya enviado | `pytest -q` (suite completa) | **476 passed, 0 failed** (baseline Fase 3: 461, +15) |
| Una sola implementación (condición del criterio 3) | grep sobre `local_archive.py` | la regex vieja no existe; `_chapter_number:251` delega |
| El contrato no se editó para pasar | `git diff 9ada90e -- tests/test_chapter_recognition.py` | vacío — el test no se tocó tras el rojo |

**Defecto del plan encontrado al ejecutar, y corregido:** el gate del criterio 3 estaba escrito como
`git log --oneline --diff-filter=A ...` «lista el TEST antes que el MODULO». `git log` ordena del más
nuevo al más viejo, así que sin `--reverse` el MÓDULO sale arriba y el gate se lee como **fallado sobre
un árbol correcto**. Es el cuarto gate de esta fase que se escribió razonando y falló al medirse. El
plan ahora ancla el gate en `git merge-base --is-ancestor`, que no admite interpretación.

**Cambio de comportamiento deliberado (no es regresión):** la regex vieja era incorrecta y la tabla lo
fija — `Vol.2 Cap 15` devolvía `2.0` (agarraba el volumen) y `Cap 12 extra` devolvía `12.0` (el mismo
número que el capítulo 12). Ahora devuelven 15 y 12.99. Ningún test existente dependía del
comportamiento viejo: la suite pasó entera sin tocar un solo test.

## Next Phase Readiness

Las Tasks 2 y 3 quedan implementadas para que el orquestador verifique el plan y cierre sus commits
y artefactos de seguimiento.

---
*Phase: 04-identidad-y-v-nculo-fuente-entrada-del-tracker*
*Completed: 2026-07-17*
