---
phase: 04-identidad-y-v-nculo-fuente-entrada-del-tracker
reviewed: 2026-07-17T00:00:00Z
depth: standard
files_reviewed: 17
files_reviewed_list:
  - apps/backend/tests/test_chapter_recognition.py
  - apps/backend/nyanko_api/chapter_recognition.py
  - apps/backend/nyanko_api/sources/local_archive.py
  - apps/backend/nyanko_api/linking.py
  - apps/backend/tests/test_linking.py
  - apps/backend/nyanko_api/database.py
  - apps/backend/tests/test_database.py
  - apps/backend/tests/test_reader_persistence.py
  - apps/backend/tests/test_manga_link.py
  - apps/backend/nyanko_api/main.py
  - apps/backend/nyanko_api/models.py
  - apps/desktop/src/types.ts
  - apps/desktop/src/api.ts
  - apps/desktop/src/MangaLibraryView.tsx
  - apps/desktop/src/ReaderView.tsx
  - apps/desktop/src/i18n.tsx
  - apps/desktop/src/styles.css
findings:
  critical: 0
  warning: 3
  info: 3
  total: 6
status: issues_found
---

# Phase 04: Code Review Report

**Reviewed:** 2026-07-17T00:00:00Z
**Depth:** standard
**Files Reviewed:** 17
**Status:** issues_found

## Summary

Reviewed the diff against `10817eed5b45c534fbd75bb649b96d38f93ad3c3`: a new `chapter_recognition.py` heuristic parser, a new `linking.py` (`SeriesLink`/`resolve_link`/`require_link`), the `media_mappings.chapter_offset` v11 migration plus the `assert_manga_namespace` write/read/delete guard in `database.py`, four new `/api/manga/link*` endpoints and a widened `create_reading_event` response in `main.py`, and the frontend's new manga-link panel in `MangaLibraryView.tsx`.

The namespace-disjunction guard (`assert_manga_namespace`) is the load-bearing safety property of this phase and it is correctly enforced end-to-end: every write, delete, and read path for manga mappings passes through it, and `test_manga_link.py`/`test_linking.py`/`test_database.py` cover the anime/manga cross-contamination cases thoroughly (including repeated confirm, relink, unlink, and the "corrupted-by-a-different-caller" scenarios). `chapter_recognition.py`'s regex heuristics were traced by hand against several inputs beyond the parametrized test cases (accented "capítulo", mixed suffix/volume markers, ambiguous multi-number names) and degrade safely to `None` rather than guessing, matching the module's stated intent.

No BLOCKER-level defects were found in the reviewed diff. Three WARNING-level issues were found: a stale-state bug in the new manga-link panel that can silently reopen a closed panel on navigation, dead fallback code for chapter counts that never actually executes, and an SQL-vs-model duplicate validation gap around `chapter_offset` bounds that only pydantic enforces. A few INFO-level maintainability notes are also listed.

## Warnings

### WR-01: Link panel state is not reset when navigating between folders, so a closed panel can silently reopen

**File:** `apps/desktop/src/MangaLibraryView.tsx:29-105` (see also 132-138, 272)
**Issue:** `serieAbierta` (and its dependents `propuesta`, `idSeleccionado`, `desfaseCapitulos`, `errorVinculo`) are only cleared by the panel's own "Cerrar" button (`setSerieAbierta(null)`) or after a successful confirm/unlink. The `cargar()` effect that runs on every `ruta` change resets `vinculos` (line 35) but never resets `serieAbierta`.

Reproduction: open the link panel for a series row (`serieAbierta` = that row's object, panel visible), then navigate away without closing it (e.g. open a sibling folder via its own "abrir" button, which pushes a different `ruta` and re-fetches `capitulos`). The panel disappears because no row in the new list matches `serieAbierta.source_id` — but `serieAbierta` itself is still set. If the user then navigates back to the original folder (breadcrumb or "Volver"), the re-fetched `capitulos` list contains the same `source_id` again, so `panelAbierto` (`serieAbierta?.source_id === capitulo.source_id`, line 240) evaluates `true` immediately and the panel snaps back open — without the user ever clicking "Vincular"/"Cambiar vínculo" again. This also re-triggers the match-fetch effect (lines 107-130), silently issuing a new `/api/manga/link/match` request. Since the previous version of this file (before this phase) had no link panel at all, this is a new regression surface, not a pre-existing one.

**Fix:**
```tsx
// inside the `cargar` effect in MangaLibraryView.tsx, alongside `setVinculos({})`
const cargar = async () => {
  setCargando(true);
  setError(null);
  setVinculos({});
  setSerieAbierta(null); // <-- close any open panel when the folder view changes
  ...
```

### WR-02: `chapter_count` fallback in `_scan_match_library` is dead code that never fires

**File:** `apps/backend/nyanko_api/main.py:2247-2249`
**Issue:**
```python
chapter_count = entry.get("chapters")
if chapter_count is None:
    chapter_count = entry.get("chapter_count")
```
`entry` here is a row produced by `Database.get_combined_library` (`database.py:1994-2153`), which is `json.loads(row["original_payload"])` merged with a fixed set of keys (`status`, `progress`, `score`, `started_at`, `completed_at`, `canonical_id`, `provider`, `account_alias`, `title_romaji/english/native`, `genres`, `tags`, `cover_image`, `synonyms`). It never adds a `"chapter_count"` key, and the original payload is `MediaItem.model_dump(mode="json")` (`database.py:1453`), whose field is named `chapters`, never `chapter_count`. `"chapter_count"` only exists as a **column name** on the `media` table (`database.py:81`, `389`), which `get_combined_library`'s `SELECT` does not project. So when a synced item has `chapters is None` (provider hasn't reported a count yet), this fallback always evaluates to `None` too — it looks like a defensive fallback to the locally-cached count but can never actually recover one.

**Fix:** either drop the dead fallback, or make it real by projecting `m.chapter_count` in `get_combined_library`'s query and threading it through:
```python
# get_combined_library: add m.chapter_count to the SELECT list and to the payload merge,
# e.g. "chapter_count": row["chapter_count"], then in _scan_match_library:
chapter_count = entry.get("chapters") if entry.get("chapters") is not None else entry.get("chapter_count")
```

### WR-03: `chapter_offset` bound is duplicated only in pydantic, not in the DB layer — `Database.set_media_mapping` accepts any int

**File:** `apps/backend/nyanko_api/database.py:2466-2491`, `apps/backend/nyanko_api/models.py:214-216`
**Issue:** The `-9999..9999` bound that keeps `SeriesLink.absolute_chapter` sane is only enforced by `MangaLinkConfirm.chapter_offset = Field(..., ge=-9999, le=9999)` at the HTTP boundary. `Database.set_media_mapping(..., chapter_offset=...)` itself has no validation, so any other caller (tests, a future Fase 5 sync path, a script) can persist an out-of-range offset directly through the database layer, silently corrupting `absolute_chapter` math with no error anywhere. Given the `linking.py` docstring explicitly frames `chapter_offset` as safety-critical for sync correctness ("La Fase 5 lo convertirá..."), relying solely on the FastAPI request model for validation is a gap at the trust boundary that actually matters (DB layer), not the HTTP layer.
**Fix:** Add the same bound as a defensive check in `set_media_mapping` (or a `CHECK` constraint on the column), e.g.:
```python
def set_media_mapping(self, provider, site_identifier, media_id, episode_offset=0, chapter_offset=0, *, manga_link=False):
    if not -9999 <= chapter_offset <= 9999:
        raise ValueError(f"chapter_offset fuera de rango: {chapter_offset}")
    assert_manga_namespace(provider, manga_link)
    ...
```

## Info

### IN-01: Stale line-number reference in a load-bearing comment

**File:** `apps/backend/nyanko_api/database.py:2481-2482`
**Issue:** The comment `"main.py:3617-3618 documenta el precedente medido..."` hardcodes line numbers in another file. `main.py` gained ~200 lines in this same diff, so those numbers are already likely to point at the wrong lines, and will drift further with any future edit — the comment will silently mislead the next reader rather than fail loudly.
**Fix:** Reference the function/test name instead of line numbers (e.g. "ver `test_una_correccion_de_playback_no_reapunta_un_vinculo_de_manga`"), which survives refactors.

### IN-02: `/api/manga/link/match` and `GET /api/manga/link` return an opaque 500 for a non-manga `source`, with no direct test coverage for these two routes

**File:** `apps/backend/nyanko_api/main.py:1667-1748`
**Issue:** Both routes call `resolve_link(database, source, series_id)` unconditionally, which raises `ValueError` via `assert_manga_namespace` for any `source` outside `{"local_archive"}`. That `ValueError` is not caught locally, so it is handled by the global `Exception` handler (`main.py:1558-1561`) and surfaces as a generic `{"detail": "Internal server error"}` / 500. This mirrors the codebase's existing, deliberately-tested "fail loud" pattern for `POST /api/playback/correction` and `DELETE /api/manga/link` (see `test_una_correccion_de_playback_no_reapunta_un_vinculo_de_manga`, `test_un_delete_de_manga_no_borra_un_mapping_de_anime`), so it is consistent rather than a new defect — but unlike those two, neither `test_manga_link.py` nor `test_linking.py` has an explicit assertion pinning this behavior for `POST /match` or `GET /link`, so a future refactor of `resolve_link`'s error handling could silently change the status code for these two routes without any test catching it.
**Fix:** Add one assertion per route (mirrors the existing pattern), e.g. `client.post("/api/manga/link/match", params={"source": "crunchyroll", "series_id": "abc"})` and `client.get("/api/manga/link", params={"source": "crunchyroll", "series_id": "abc"})` both expecting 500, in `test_manga_link.py`.

### IN-03: `MangaLinkMatchResponse`'s "linked" branch recomputes `_scan_match_library` twice on the same request

**File:** `apps/backend/nyanko_api/main.py:1673-1690`
**Issue:** `_scan_match_library(database, media_type="MANGA")` is called once inside the `if link is not None:` branch (line 1676) and, structurally, the function is written so a maintainer skimming it might assume it's shared across branches — it is not (the second call at line 1690 is unreachable from the `link is not None` branch because of the early `return`), so there's no double-execution today, but the duplicated call sites make it easy for a future edit to introduce one. Not a functional bug now; flagged only because the two call sites are easy to accidentally desync (e.g. only one gets a future `media_type` filter fixed).
**Fix:** Hoist a single `library = _scan_match_library(database, media_type="MANGA")` above the `if link is not None:` branch and reuse it in both paths.

---

_Reviewed: 2026-07-17T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
