---
status: resolved
trigger: "manga-link-button-missing: The manga library view's new \"vincular\" (link) button/panel from plan 04-04 does not appear at all for the user, in the running Electron app."
created: 2026-07-17T16:00:00Z
updated: 2026-07-17T18:00:00Z
---

## Current Focus

hypothesis: CONFIRMED (round 2) - see Resolution.root_cause (updated) and Evidence 17:20-17:35
test: Human re-ran 04-UAT Test 1 and Test 2 against G:\manga, completing the confirm step. Verbatim: "si, funcionan" (yes, they work).
expecting: n/a - confirmed
next_action: n/a - resolved. Archiving session.

## Round 2 — New Symptom After Round-1 Fix

reported (verbatim): "cuando intenta vincular dice: Serie local no encontrada, además, si tengo capitulos separados en cbz me los va listando aparte también, en ese caso como identifica las series?"
translation: When attempting to link it says "Local series not found". Also: separate .cbz chapter files list separately — how are series identified in that case?

This is a NEW symptom, not covered by round 1's fix. Round 1 fixed button *visibility*; this is a
failure in the link *confirmation* action itself, once the button is clicked.

## Reasoning Checkpoint

reasoning_checkpoint:
  hypothesis: "In a flat library the link control never renders because both the prefetch filter (line 38) and the render gate (line 252) gate on `!capitulo.is_chapter`, and every loose top-level archive is is_chapter=True."
  confirming_evidence:
    - "G:\\manga (only registered manga root) is flat: 4 loose .cbz/.cbr, zero subdirs → all rows is_chapter=True (Evidence 16:22)."
    - "local_archive.py:133 `is_chapter=not is_directory or has_images` → True for every plain file, unconditionally."
    - "Both link consumers in MangaLibraryView gate on `!is_chapter`, so a flat root yields zero buttons."
  falsification_test: "If after the fix a flat-root file still renders no vincular button, or a nested subfolder chapter now wrongly renders one, the fix is wrong."
  fix_rationale: "Linkability is a separate axis from is_chapter (which must stay True to keep abrir=read). A top-level row IS the series in both layouts, so `esVinculable = enRaiz || !is_chapter` — one shared predicate used by both consumers. Backend id→title derivation stays the shared path; only strips the container extension that the newly-enabled loose-file path drags into the matcher."
  blind_spots: "Could not click the real Electron UI headlessly; verified via typecheck, backend tests, and pure-logic checks. A flat root holding multiple chapters of the SAME series links each file independently (per-source_id) — intended per UAT Test 8, but means multi-file series aren't auto-grouped."

## Symptoms

expected: Test 1 — pulsar el boton de vincular de una serie sin vinculo abre el panel con la propuesta, un porcentaje de confianza visible y hasta 5 alternativas; la vista NO navega dentro de la carpeta. Test 2 — con teclado (Tab), la fila de una serie ofrece dos paradas de foco (navegar / vincular) y Enter en cada una hace lo suyo.
actual: Test 1 — user reported (verbatim): "no veo ningun vinculo en la libreria de manga" (I don't see any link in the manga library). Test 2 — user reported (verbatim): "no aparece nigun boton" (no button appears at all).
errors: None reported by the user (no console/error text given).
reproduction: Open the manga library tab in the running Nyanko Electron app (`npm run dev`), with at least one manga folder registered. Test 1 and Test 2 in .planning/phases/04-identidad-y-v-nculo-fuente-entrada-del-tracker/04-UAT.md.
started: Discovered during UAT of phase 04 (identidad-y-vínculo), immediately after plan 04-04 implemented the link panel.

## Eliminated

- hypothesis: Electron app is running a stale build predating commits 3bcddca/fbc8aee (the link button code)
  evidence: `git log --format="%h %ad %s"` shows fbc8aee (2026-07-17 11:04) and every later commit (a7af5c4, 0544fb8, f9bc08e, e6ec51c, 21907d7 - the UAT-failure commit itself, 13:12) are all present in HEAD. `git status --short` is clean (no uncommitted drift) other than this new debug file. `MangaLibraryView.tsx` on disk (Read tool) contains the exact button markup described in the trigger (`.manga-library-item` as `<div>`, `manga-library-open` + `manga-library-link` siblings, link gated on `!capitulo.is_chapter`). Dev mode uses electron-vite HMR (renderer serves live TS/TSX from source, not a prebuilt bundle) so a stale renderer bundle is not a plausible mechanism here.
  timestamp: 2026-07-17T16:05:00Z
- hypothesis: CSS hides the `.manga-library-link` button (display:none, 0-size, overflow-clipped, off-screen)
  evidence: Read `apps/desktop/src/styles.css:381-413`. `.manga-library-item` is `display:grid; grid-template-columns: minmax(0,1fr) auto` (two visible columns). `.manga-library-link` is `display:grid; ... min-width:170px; border:1px solid var(--border); ...` — a normal visible block, no `display:none`, no `visibility:hidden`, no `width:0`, no negative positioning, no `overflow:hidden` ancestor clipping it. No other rule in the file targets `.manga-library-link` to hide it.
  timestamp: 2026-07-17T16:10:00Z

## Evidence

- timestamp: 2026-07-17T16:00:00Z
  checked: apps/desktop/src/MangaLibraryView.tsx (full file, 370 lines)
  found: Line 252: `{!capitulo.is_chapter && (<button type="button" className="manga-library-link" ...>)}`. The link button (and the whole vinculo state machine) is gated EXCLUSIVELY on `capitulo.is_chapter` being false. If every row returned by the backend for a given folder view has `is_chapter === true`, literally zero link buttons render, for every row, simultaneously — matching the user's report of a total absence, not a partial one.
  implication: Need to find out what determines `is_chapter` and whether it can be true for every top-level row in this user's real library.

- timestamp: 2026-07-17T16:12:00Z
  checked: apps/backend/nyanko_api/sources/local_archive.py:87-136 (`LocalArchiveSource.chapters()`)
  found: For each child of the folder being listed, `is_directory = path.is_dir()`; `has_images = is_directory and any direct child is an image file`; and critically `is_chapter=not is_directory or has_images`. A plain FILE (a `.cbz`/`.cbr`/`.zip` sitting directly in the listed folder) always yields `is_chapter=True` regardless of anything else, because `not is_directory` is `True` for files.
  implication: If a manga library ROOT folder contains chapter/volume archive files directly (no per-series subdirectory — a "flat" library), then listing that root returns rows that are ALL `is_chapter=True`. Under MangaLibraryView's `!capitulo.is_chapter` gate, none of them would ever get a link button.

- timestamp: 2026-07-17T16:15:00Z
  checked: .planning/phases/.../04-04-PLAN.md (Task 2 read_first + human-check step 10)
  found: The plan explicitly names this exact scenario as a known edge case: "Con una carpeta de biblioteca PLANA (los CBZ colgando directamente de la raiz registrada, sin subcarpeta de serie): esa serie tambien se puede vincular y su vinculo sobrevive. Es el caso `0:.` — no-regresion contra la Fase 3, que ya lo soporta y esta cerrada." The plan assumed this "already worked" because Phase 3 supports READING a flat CBZ-at-root layout — but the plan's acceptance criteria never actually specify how a flat/root-level series gets a link CONTROL to attach to, and the implementation gates the link button per-row on `!capitulo.is_chapter`, which structurally excludes every row in a flat-root layout.
  implication: This is a real gap the plan foreshadowed but did not close — not a regression introduced by a coding mistake, but an incomplete design for the flat-library case.

- timestamp: 2026-07-17T16:20:00Z
  checked: Live dev database at `apps/backend/data/nyanko.sqlite3` (confirmed as the actual dev DB in use: `apps/backend/nyanko_api/config.py` `_anchor_dir()` returns `Path(__file__).resolve().parent.parent` i.e. `apps/backend` when NOT frozen/packaged, and `electron/main/index.ts:109-110` confirms dev mode skips sidecar spawn entirely — "dev: la app usa el backend Python arrancado a mano" — so `NYANKO_DATA_DIR` is not injected by Electron in dev and the backend falls back to its anchored default `apps/backend/data/`). NOTE: initially queried the WRONG db at `%APPDATA%\app.nyanko.desktop\nyanko.sqlite3` (the prod/packaged compatibility path) which is stale/unrelated to this dev session (missing `kind` column entirely) — corrected by locating the actual dev db, which has `kind` column and version-tagged backups (v8-v11) proving it's the live, migrated dev database.
  found: `SELECT id, path, recursive, kind FROM library_folders` → only one `kind='manga'` row: `(7, 'G:\manga', 1, 'manga')`.
  implication: There is exactly one registered manga root, `G:\manga`, and it is the only source of rows the user could have tested against.

- timestamp: 2026-07-17T16:22:00Z
  checked: Filesystem listing of `G:\manga` (the registered manga root)
  found: |
    Directory contains ONLY files, no subdirectories:
    - Chainsaw Man 132 (2023) (Digital) (anadius).cbz
    - Chainsaw Man 133 (2023) (Digital) (anadius).cbz
    - Cyberpunk - Edgerunners Madness v01 (2026) (Digital-Empire).cbr
    - Star Wars - Jedi Knights v02 - A Higher Path (2026) (digital) (Marika-Empire).cbz
  implication: This is EXACTLY the "flat library" layout identified in the previous evidence entries. When `MangaLibraryView` lists this root (`api.mangaChapters(SOURCE_NAME, "7:.")`), `local_archive.py.chapters()` returns 4 rows, each a plain file → `is_directory=False` → `is_chapter=True` for ALL 4 rows. The `!capitulo.is_chapter` gate in `MangaLibraryView.tsx:252` therefore renders ZERO link buttons, for every row, on every page load. This reproduces both Test 1 ("no veo ningun vinculo") and Test 2 ("no aparece ningun boton") deterministically and completely, with no dependency on build freshness, HMR, or a runtime JS error.

- timestamp: 2026-07-17T17:20:00Z
  checked: Traced "Serie local no encontrada" as a literal string (Grep across apps/backend/nyanko_api). Only 1 raise site plausible for this action out of 8 total.
  found: |
    `PUT /api/manga/link` (`confirm_manga_link`, main.py:1751-1762) validates the series exists
    BEFORE writing the link by calling `await _source_engine(request).chapters(source, series_id)`
    and discarding the result — existence-check-by-side-effect, the only such hook the generic
    `Source` protocol exposes (contract.py has no separate `exists()`). This routes through
    `SourceEngine.chapters()` (engine.py:97) into `LocalArchiveSource.chapters()`
    (local_archive.py:87-91), which UNCONDITIONALLY required `series_path.is_dir()` and raised
    `SourceNotFoundError("Serie local no encontrada")` for any file. For a flat-root loose file,
    `_resolve_id(series_id)` resolves `series_path` to that FILE, not a directory — so the
    existence check always fails for exactly the rows round 1 newly made clickable.
  implication: |
    Round 1's frontend fix correctly exposes the vincular control on flat-root rows, and the user
    now reaches confirmarVinculo -> api.setMangaLink -> PUT /api/manga/link for the first time on
    such rows. That request 404s at the pre-write existence check, which never anticipated a file
    series_id. This is a new, distinct root cause layer (backend write-path validation), not
    something round 1's frontend/title-derivation fix touches or covers.

- timestamp: 2026-07-17T17:30:00Z
  checked: apps/backend/tests/test_manga_link.py::test_confirmar_valida_serie_capitulo_y_fuente_antes_de_escribir
  found: |
    Existing invariant test asserts confirming a link on `0:Berserk/Cap 13.cbz` (a CHAPTER nested
    inside a real series FOLDER, in a non-flat/nested library) must be REJECTED with 404 — a
    chapter is not its own series and must not be independently linkable when a real series folder
    exists above it.
  implication: |
    The fix cannot simply "allow any file" in chapters()'s existence path — that would let a
    nested chapter also pass as a fake series (this broke the test on first attempt: 200 instead
    of 404). The correct scope is narrower: only a file whose PARENT is the registered root itself
    counts as its own series (flat-root case). A file nested inside a subfolder anywhere else must
    still be rejected. This mirrors the frontend's own `enRaiz` scoping from round 1 — same
    "top-level-of-root is special" rule, now enforced on the backend write path too.

- timestamp: 2026-07-17T17:35:00Z
  checked: Design question from the user's report — "si tengo capitulos separados en cbz me los va listando aparte también, en ese caso como identifica las series?"
  found: |
    04-UAT Test 8 explicitly specifies this as the INTENDED behavior, not a bug: "Con DOS series
    distintas en la MISMA carpeta raiz (biblioteca plana), vincular solo la primera... la clave es
    source_id, no series_id" — i.e. each loose flat-root file is deliberately treated as its own
    independently-linkable unit, keyed by its own source_id. This was a conscious phase-04 design
    choice (per-file linking, not per-detected-series-name grouping), confirmed by the test suite
    itself, not an oversight introduced by round 1 or round 2's fixes.
  implication: |
    Auto-grouping multiple loose chapter files that share a series name (e.g. "Chainsaw Man 132.cbz"
    + "Chainsaw Man 133.cbz") into ONE linkable series identity is a real, separate feature gap —
    but it is explicitly OUT OF SCOPE for this bug (which is "the button/link is missing/broken"),
    not something to silently fold into this fix. Flagged to the user as a follow-up decision, not
    fixed here.

## Resolution

root_cause: |
  The link ("vincular") button in `MangaLibraryView.tsx` is gated on `!capitulo.is_chapter` (line 252),
  which assumes a manga library is organized as `root/SeriesFolder/ChapterArchive.cbz` — i.e. that every
  "series" is represented by a directory row distinct from its chapter rows. The user's actual manga
  library folder (`G:\manga`, the only registered `kind='manga'` folder) is a FLAT library: chapter/volume
  archive files (`.cbz`/`.cbr`) sit directly in the registered root with no per-series subdirectory.

  `local_archive.py`'s `chapters()` (line 133: `is_chapter=not is_directory or has_images`) classifies
  every plain file as `is_chapter=True` unconditionally. Listing `G:\manga`'s root therefore returns 4
  rows that are ALL `is_chapter=True` — there is no row in this library with `is_chapter=False`, so the
  link button's render condition (`!capitulo.is_chapter`) is false for every row, on every page, and the
  button never appears anywhere in the library view. This matches the user's report exactly: not a
  partial/one-off failure, a total absence across the whole visible library.

  This is a genuine, plan-foreshadowed-but-unclosed design gap (04-04-PLAN.md's own human-check step 10
  names the flat-library case and assumes it "already works" by analogy with Phase 3's read support,
  without specifying what UI element a flat-root series would attach its link control to). It is NOT a
  stale build, NOT a CSS visibility bug, and NOT a runtime JS error — all three were checked and ruled
  out (see Eliminated).

  ROUND 2 (after round-1 fix made the button clickable, a NEW symptom surfaced: confirming the link
  fails with "Serie local no encontrada"): `PUT /api/manga/link` (`confirm_manga_link`) validates the
  series exists before writing by calling `source.chapters(series_id)` and discarding the result — the
  only existence-check hook the `Source` protocol exposes. `LocalArchiveSource.chapters()`
  unconditionally required `series_path.is_dir()`, raising `SourceNotFoundError` for ANY file. A
  flat-root loose file resolves to a file, not a directory, so this pre-write check always 404s for
  exactly the rows round 1 newly made linkable. This is a second, independent gap in the same
  flat-vs-nested model mismatch — round 1 fixed the read/render side, round 2 fixes the write-validation
  side. Separately: the user asked how same-series loose chapter files (e.g. two Chainsaw Man .cbz) get
  identified as one series — confirmed via 04-UAT Test 8 that per-file independent linking (keyed by
  source_id, not by detected series name) is the INTENDED phase-04 design, not a bug; grouping is a
  distinct, out-of-scope feature request.
fix: |
  Introduced a "linkable series" axis distinct from `is_chapter` (which had to stay True for
  loose files so `abrir` keeps opening the reader instead of trying to navigate into a file).

  Frontend — apps/desktop/src/MangaLibraryView.tsx:
  - Added a single shared predicate `esVinculable(nodo, enRaiz) = enRaiz || !nodo.is_chapter`,
    where `enRaiz = ruta.length === 0` (top level of a registered root). A top-level row IS
    the series in BOTH layouts: a folder in a nested library, a loose archive in a flat one.
  - Routed BOTH link consumers through it (was the point of divergence): the prefetch filter
    (`cargarVinculos`, was `!nodo.is_chapter`) and the per-row render gate (was `!capitulo.is_chapter`).
  - Result: flat-root loose files now render the `manga-library-link` button (keyed on their own
    source_id) AND keep their reader open button → two focus stops per row. Nested behavior is
    unchanged: top-level folders still linkable; chapters inside a series folder still are not.

  Backend — apps/backend/nyanko_api/main.py (_series_title_from_id):
  - This helper newly receives loose-file ids (e.g. `7:Chainsaw Man 132 (2023).cbz`). Strip a
    KNOWN archive extension (.cbz/.cbr/.zip/.rar) so the matcher sees "Chainsaw Man 132 (2023)"
    not "...anadius).cbz". Guarded to only strip real archive suffixes (a folder "Vol.1" is left
    intact). Folder-series ids and the flat-root-itself id (`7:.`) are unaffected.

  ROUND 2 — Backend — apps/backend/nyanko_api/sources/local_archive.py (`LocalArchiveSource.chapters()`):
  - Added a file/dir duality at the top of `chapters()`, mirroring the duality `pages()` already has.
    When `series_path.is_file()` AND `series_path.parent == root` (file sits DIRECTLY at the registered
    root — the flat-library case) AND its suffix is a known archive extension: return a single-item
    list where the file is its own chapter (source_id == series_id == the file's id), instead of
    raising. This is the ONLY generic existence-check hook `confirm_manga_link` has, so fixing it here
    (the shared implementation both `manga_chapters` and `confirm_manga_link` route through via
    `SourceEngine`) fixes both current and any future caller — not a per-endpoint patch.
  - Scoped narrowly to `series_path.parent == root` (not "any file at any depth") specifically because
    an existing invariant test (`test_confirmar_valida_serie_capitulo_y_fuente_antes_de_escribir`)
    requires a chapter nested inside a real series folder (`0:Berserk/Cap 13.cbz`) to keep being
    rejected as "not a series" — caught by running the suite after the first (too-broad) attempt.
  - Design question (multiple loose chapters of the same series listing/linking separately): confirmed
    NOT a bug — 04-UAT Test 8 specifies per-source_id independent linking as the intended flat-library
    design. Not fixed here; flagged to the user as a distinct follow-up (auto-grouping by detected
    series name) if they want it.
verification: |
  Self-verified (could not drive the live Electron UI headlessly):
  - Round 1: `npm run check` (tsc --noEmit) in apps/desktop: clean, 0 errors.
  - Round 1: `_series_title_from_id` checks against a fake DB — all pass (extension strip, Vol.1
    non-strip, nested chapter, root-itself, bare titles with `!`).
  - Round 2: full backend suite `pytest` (apps/backend): 502 passed, including the
    `test_confirmar_valida_serie_capitulo_y_fuente_antes_de_escribir` invariant (nested chapter still
    404s) and `test_confirmar_admite_biblioteca_plana_y_acota_el_offset` (flat-root `0:.` link still
    works).
  - Round 2: direct exercise of `LocalArchiveSource.chapters()` against a temp dir with the exact
    reported file shape (two "Chainsaw Man 13X (2023) (Digital) (anadius).cbz" loose files at root):
    `chapters('7:.')` lists both as `is_chapter=True`; `chapters()` on EACH file's own source_id now
    returns a 1-item list (was: raised `SourceNotFoundError`) — this is what `confirm_manga_link`
    needed to stop 404ing. Confirmed a nested-inside-a-file nonsense id is still rejected.
  Pending human verification: 04-UAT Test 1 (link opens proposal panel, confidence %, up to 5
  alternatives, no navigation) and Test 2 (Tab exposes navigate + vincular focus stops, Enter acts),
  AND this time completing the confirm step (round 2's actual fix) against G:\manga in the live app.
files_changed:
  - apps/desktop/src/MangaLibraryView.tsx
  - apps/backend/nyanko_api/main.py
  - apps/backend/nyanko_api/sources/local_archive.py
