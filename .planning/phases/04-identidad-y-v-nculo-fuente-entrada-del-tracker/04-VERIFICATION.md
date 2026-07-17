---
phase: 04-identidad-y-v-nculo-fuente-entrada-del-tracker
verified: 2026-07-17T15:14:42Z
status: human_needed
score: 4/4 must-haves verified
behavior_unverified: 0
overrides_applied: 0
human_verification:
  - test: "Pulsar el boton de vincular de una serie sin vinculo (MangaLibraryView)"
    expected: "Se abre el panel con la propuesta, un porcentaje de confianza visible y hasta 5 alternativas; la vista NO navega dentro de la carpeta."
    why_human: "Requiere la app corriendo (Electron/React) para observar navegacion, layout y ausencia de burbujeo de click; no es verificable por grep."
  - test: "Con teclado (Tab), la fila de una serie ofrece dos paradas de foco (navegar / vincular) y Enter en cada una hace lo suyo"
    expected: "Dos controles de foco independientes, cada uno activable con Enter"
    why_human: "Comportamiento de foco/accesibilidad del DOM renderizado; no verificable estaticamente."
  - test: "Cerrar el panel de vinculo SIN pulsar confirmar, y reabrirlo"
    expected: "La serie sigue sin vincular (mirar una propuesta no la acepta)"
    why_human: "Requiere interaccion real con estado de componente en ejecucion."
  - test: "Elegir una alternativa distinta de la propuesta, fijar offset y confirmar"
    expected: "El panel se cierra y la serie muestra la entrada ELEGIDA, no la propuesta original"
    why_human: "Flujo de UI de varios pasos con estado async; no verificable por lectura de codigo."
  - test: "Reabrir el panel de una serie ya vinculada"
    expected: "Sigue vinculada a lo elegido, y no se propone nada nuevo (el vinculo cortocircuita el matcher)"
    why_human: "Requiere sesion interactiva contra el backend real."
  - test: "Desvincular una serie"
    expected: "La serie vuelve a 'sin vincular'"
    why_human: "Interaccion de UI en tiempo real."
  - test: "Reiniciar la app despues de confirmar un vinculo"
    expected: "El vinculo persiste (esta almacenado, no en memoria)"
    why_human: "Requiere reiniciar el proceso Electron/sidecar; no verificable estaticamente."
  - test: "Con DOS series distintas en la MISMA carpeta raiz (biblioteca plana), vincular solo la primera"
    expected: "La segunda serie sigue viendose 'sin vincular' (la clave es source_id, no series_id)"
    why_human: "Requiere una biblioteca de prueba con estructura especifica y observacion visual del resultado; el codigo fuente ya usa source_id en los 4 puntos de llamada (verificado estaticamente), pero el efecto compuesto necesita ejecucion."
  - test: "Terminar de leer un capitulo de una serie SIN vincular"
    expected: "El lector muestra el mensaje 'no vinculada, vinculala' en espanol (el reason del backend), no silencio"
    why_human: "Requiere completar un capitulo en la app en ejecucion para observar el aviso en su instante real (criterio 4, la mitad visible)."
  - test: "Con una carpeta de biblioteca PLANA (CBZ colgando de la raiz, series_id/source_id = '0:.')"
    expected: "Esa serie tambien se puede vincular y el vinculo sobrevive (no-regresion Fase 3)"
    why_human: "Requiere una biblioteca de prueba real con esa estructura de carpetas."
---

# Phase 04: Identidad y vínculo (fuente ↔ entrada del tracker) Verification Report

**Phase Goal:** Existe un vínculo explícito, almacenado y confirmado por el usuario entre una serie
de una fuente y una entrada del tracker — para que el sync pueda asumirlo, y negarse cuando no lo hay.

**Verified:** 2026-07-17T15:14:42Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `matcher.py` propone un vínculo con score de confianza; nada queda vinculado sin confirmación; la corrección del usuario manda | ✓ VERIFIED | `POST /api/manga/link/match` (`main.py:1667-1724`) calls `find_best_match`/`rank_matches` over the MANGA library and returns `match_score`, `suggestions`, and never calls `set_media_mapping`/`set_match_correction`. Test `test_match_propone_con_score_sin_persistir_ni_duplicar_sugerencias` asserts `match_score >= 0.99` AND `media_mappings` count stays 0. `PUT /api/manga/link` (`main.py:1751-1795`) is the sole writer — grep confirms exactly 1 of 5 `set_media_mapping` call sites passes `manga_link=True` (the PUT). `test_un_vinculo_confirmado_manda_sobre_el_matcher` proves an existing link short-circuits the fuzzy matcher (score 1.0, no re-run). 502/502 backend tests pass. |
| 2 | El vínculo se almacena (mirror de `media_mappings` con `chapter_offset`, como `episode_offset`); nunca se calcula en el sync | ✓ VERIFIED | `database.py:410` adds `chapter_offset` via `_add_column` (schema v11, `CANONICAL_SCHEMA_VERSION = 11` at `database.py:312`); `SCHEMA` constant unchanged (no new `CREATE TABLE`). `linking.SeriesLink.absolute_chapter()` (`linking.py:19-20`) is pure arithmetic over the stored offset (`chapter + self.chapter_offset`) — not a sync-time computation. `test_el_vinculo_confirmado_conserva_media_id_y_offset` and `test_el_capitulo_absoluto_conserva_decimales` verify round-trip and decimal preservation. |
| 3 | `ChapterRecognition` es componente propio, puro, unitariamente testeable, tabla escrita antes del código (`extra`=.99, `omake`=.98, `12a`→12.1), en verde | ✓ VERIFIED | `apps/backend/nyanko_api/chapter_recognition.py` is a standalone module importing only `re` (stdlib). `recognize_chapter("Ch.12 extra")` → 12.99, `"Ch.12 omake"` → 12.98, `"12a"` → 12.1 (constants at `chapter_recognition.py:22-24`, confirmed by reading the source). `git log --reverse --diff-filter=A` shows `9ada90e` (test, RED) committed before `3096d27` (module, GREEN) — literal commit-order proof, not narrative. `local_archive.py:246-251` (`_chapter_number`) delegates to `recognize_chapter`; no residual `re.search` for chapter numbers found in that file. 36/36 `test_chapter_recognition.py`+`test_linking.py` pass; full suite 502 passed. |
| 4 | Un intento de sync sin vínculo confirmado falla cerrado: se lo dice al usuario, no escribe, no encola. Verificado como test | ✓ VERIFIED | `linking.require_link` (`linking.py:51-57`) raises `UnlinkedSeriesError` with a user-facing Spanish message when no link exists; delegates to `resolve_link`, which enforces `assert_manga_namespace` so an anime mapping can never be read as a manga link. `test_una_propuesta_fuerte_no_es_un_vinculo_confirmado` proves a strong matcher proposal never counts as consent. `POST /api/manga/reading-events` (`main.py:1858-1888`) returns `linked: false` + `reason` (built from `UnlinkedSeriesError(...).message`, not raised) when unlinked, and the declared tripwire `test_un_evento_sin_vinculo_se_registra_y_no_encola` asserts `pending_mutations` stays 0. `require_link` has zero production callers as of this phase (only `resolve_link` is imported into `main.py`) — this is by design per the plan: Phase 5 is the one that must cross `require_link` before `enqueue_mutation`, and the tripwire test exists specifically to catch a future Phase-5 regression that skips it. |

**Score:** 4/4 truths verified (0 present, behavior-unverified)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `apps/backend/nyanko_api/chapter_recognition.py` | Pure component, stdlib only | ✓ VERIFIED | Exists, imports only `re`, exports `recognize_chapter` |
| `apps/backend/tests/test_chapter_recognition.py` | 14-case parametrized table, written before code | ✓ VERIFIED | Exists; git log confirms RED-before-GREEN ordering |
| `apps/backend/nyanko_api/linking.py` | `SeriesLink`, `UnlinkedSeriesError`, `resolve_link`, `require_link` | ✓ VERIFIED | All four symbols present, read in full |
| `apps/backend/tests/test_linking.py` | LNK-04 gate | ✓ VERIFIED | 5 tests, all passing |
| `media_mappings.chapter_offset` | Additive column, schema v11 | ✓ VERIFIED | `_add_column` at `database.py:410`; `CANONICAL_SCHEMA_VERSION = 11` |
| `database.MANGA_RESERVED_PROVIDERS` / `assert_manga_namespace` | Namespace guard, single source of truth | ✓ VERIFIED | Declared once (`database.py:314,320`); called from exactly 3 sites: `set_media_mapping` (`:2479`), `delete_media_mapping` (`:2496`), `linking.resolve_link` (`:35`) |
| `POST /api/manga/link/match`, `GET/PUT/DELETE /api/manga/link` | HTTP CRUD for manga links | ✓ VERIFIED | All 4 endpoints present in `main.py:1667-1806`, matching plan contract |
| `apps/backend/tests/test_manga_link.py` | HTTP-level gates incl. namespace-cross-boundary tests and tripwire | ✓ VERIFIED | 14 tests present and passing |
| `apps/desktop/src/types.ts` / `api.ts` | Mirror types + 5 client functions | ✓ VERIFIED | `MangaLink`, `MangaLinkMatch`, `ReadingEventResponse` present; `mangaLinkMatch`/`mangaLink`/`setMangaLink`/`deleteMangaLink`/`createReadingEvent` all route through `request<T>()` |
| `apps/desktop/src/MangaLibraryView.tsx` | Link panel, restructured row (no nested buttons) | ✓ VERIFIED | `.manga-library-item` is a `<div>`; `manga-library-open`/`manga-library-link` are sibling `<button>`s; no `stopPropagation`; all 4 link calls key on `.source_id` |
| `apps/desktop/src/ReaderView.tsx` | "unlinked" notice on reading-event response | ✓ VERIFIED | `.then((evento) => { if (!evento.linked && evento.reason) setAviso(evento.reason); })` at line ~172 |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| `local_archive._chapter_number` | `chapter_recognition.recognize_chapter` | direct call | ✓ WIRED | `local_archive.py:251`; no local regex remains |
| `database.set_media_mapping` / `delete_media_mapping` | `database.assert_manga_namespace` | direct call, first line of body | ✓ WIRED | Confirmed at `:2479` and `:2496` |
| `linking.resolve_link` | `database.assert_manga_namespace` | direct call | ✓ WIRED | `linking.py:35`, `manga_link=True` fixed |
| `main.py` endpoints | `linking.resolve_link` / `require_link` | import + call | ✓ WIRED | `match_manga_link`, `get_manga_link`, `create_reading_event` all call `resolve_link`; `require_link` imported but has no production caller yet (by design, Phase 5's job) |
| `main.confirm_manga_link` (PUT) | `database.set_media_mapping(..., manga_link=True)` | direct call | ✓ WIRED | Sole writer, confirmed by source read + plan's grep gate |
| `MangaLibraryView.tsx` | `api.ts` (`mangaLinkMatch`/`mangaLink`/`setMangaLink`/`deleteMangaLink`) | direct call | ✓ WIRED | All 4 keyed on `.source_id` |
| `ReaderView.tsx` (`createReadingEvent`) | `setAviso` → `<p className="reader-notice">` | `.then()` handler | ✓ WIRED | Confirmed at source |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Chapter recognition table green | `pytest tests/test_chapter_recognition.py -q` | 15 passed | ✓ PASS |
| RED-before-GREEN commit order (criterio 3) | `git log --reverse --diff-filter=A -- tests/test_chapter_recognition.py chapter_recognition.py` | test commit (`9ada90e`) lists before module commit (`3096d27`) | ✓ PASS |
| linking.py gate | `pytest tests/test_linking.py -q` | 5 passed | ✓ PASS |
| manga link HTTP gate | `pytest tests/test_manga_link.py -q` | 14 passed | ✓ PASS |
| Full backend suite (regression) | `pytest -q` (run once) | 502 passed, 0 failed | ✓ PASS |
| Frontend typecheck | `npm run check --workspace @nyanko/desktop` (`tsc --noEmit`) | 0 errors | ✓ PASS |
| No debt markers in phase files | `grep -nE "TBD\|FIXME\|XXX\|TODO\|HACK\|PLACEHOLDER"` across all 9 phase-touched files | no matches | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan(s) | Description | Status | Evidence |
|--------------|-----------------|-------------|--------|----------|
| LNK-01 | 04-02, 04-03, 04-04 | Vínculo explícito, almacenado y confirmado por el usuario; nunca calculado en sync | ✓ SATISFIED | `assert_manga_namespace` guard (3 call sites), `PUT /api/manga/link` sole writer, UI confirm-only flow with no auto-writing `useEffect` |
| LNK-02 | 04-01 (indirectly via chapter numbering feeding matches), 04-03, 04-04 | `matcher.py` propone con score; usuario confirma | ✓ SATISFIED | `POST /api/manga/link/match` returns score+suggestions, never writes; UI shows score as a percentage, not a color |
| LNK-03 | 04-01 | `ChapterRecognition` propio, puro, testeable, tabla antes del código | ✓ SATISFIED | `chapter_recognition.py` module, 14-case table, RED-before-GREEN commit order, `local_archive.py` delegates |
| LNK-04 | 04-02, 04-03, 04-04 | Sync falla cerrado sin vínculo confirmado | ✓ SATISFIED | `require_link` raises `UnlinkedSeriesError`; tripwire test asserts `pending_mutations` stays 0 on unlinked reading events; reason surfaced to user in ReaderView |

REQUIREMENTS.md's traceability table currently shows LNK-01 through LNK-04 as "Pending." Based on the codebase evidence above, **all four should flip to "Done"** — this is the expected pre-close state (the same pattern seen with FND-01..06 in Phase 1, which were flipped to "Complete" at phase close) and is not itself a gap.

### Anti-Patterns Found

None. Scanned all 9 phase-touched files (`chapter_recognition.py`, `linking.py`, `database.py`, `main.py`, `models.py`, `MangaLibraryView.tsx`, `ReaderView.tsx`, `api.ts`, `types.ts`) for `TBD|FIXME|XXX|TODO|HACK|PLACEHOLDER` and empty-implementation patterns — zero matches.

### Human Verification Required

The phase's own plan (04-04) explicitly defers two deliverables to `human_judgment: true` /
`human_verify_mode: end-of-phase` — D2 (link panel UI behavior: focus, proposal display, persistence,
per-series isolation) and D3 (reader's unlinked-chapter notice, observed live). This is expected and by
design per the task brief, not a gap: these are runtime UI/UX behaviors that static analysis cannot
observe (navigation vs. click-bubbling, keyboard focus order, cross-restart persistence, and the visual
appearance of the in-app notice). All source-level assertions backing these behaviors (row structure,
`.source_id` keying at all 4 call sites, absence of `stopPropagation`, the `.then()` handler reading
`linked`/`reason`) were verified statically above and hold. The 10 items harvested from the 04-04-PLAN.md
`<human-check>` block are listed in the frontmatter `human_verification` section above and should be
run as the phase's UAT before closing.

### Gaps Summary

No gaps found. All 4 ROADMAP success criteria are VERIFIED against the actual codebase (not just
SUMMARY claims): source read in full for every new/modified symbol, git commit order checked for the
RED-before-GREEN requirement, the full backend test suite (502 tests) run fresh, and the frontend
typecheck run fresh. The only reason this phase does not resolve to `passed` is the deliberately
deferred UI/UX human-verification items (D2/D3 of 04-04), which is the expected end-of-phase UAT gate,
not a defect.

---

*Verified: 2026-07-17T15:14:42Z*
*Verifier: Claude (gsd-verifier)*
