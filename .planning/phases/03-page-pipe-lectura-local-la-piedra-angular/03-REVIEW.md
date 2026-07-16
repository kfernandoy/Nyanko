---
phase: 03-page-pipe-lectura-local-la-piedra-angular
reviewed: 2026-07-16T00:00:00Z
depth: standard
files_reviewed: 30
files_reviewed_list:
  - apps/backend/nyanko_api/database.py
  - apps/backend/nyanko_api/main.py
  - apps/backend/nyanko_api/models.py
  - apps/backend/nyanko_api/sources/__init__.py
  - apps/backend/nyanko_api/sources/contract.py
  - apps/backend/nyanko_api/sources/engine.py
  - apps/backend/nyanko_api/sources/local_archive.py
  - apps/backend/tests/test_database.py
  - apps/backend/tests/test_manga_api.py
  - apps/backend/tests/test_manga_pages.py
  - apps/backend/tests/test_reader_persistence.py
  - apps/backend/tests/test_source_api.py
  - apps/backend/tests/test_source_budget.py
  - apps/backend/tests/test_source_engine.py
  - apps/backend/tests/test_sources.py
  - apps/desktop/electron.vite.config.ts
  - apps/desktop/electron/main/csp.test.ts
  - apps/desktop/electron/main/splash.ts
  - apps/desktop/index.html
  - apps/desktop/package.json
  - apps/desktop/scripts/reader-rss.mjs
  - apps/desktop/src/App.tsx
  - apps/desktop/src/MangaLibraryView.tsx
  - apps/desktop/src/ReaderView.tsx
  - apps/desktop/src/api.ts
  - apps/desktop/src/i18n.tsx
  - apps/desktop/src/readerWindow.test.ts
  - apps/desktop/src/readerWindow.ts
  - apps/desktop/src/styles.css
  - apps/desktop/src/types.ts
findings:
  critical: 3
  warning: 6
  info: 2
  total: 11
status: issues_found
---

# Phase 3: Code Review Report

**Reviewed:** 2026-07-16
**Depth:** standard
**Files Reviewed:** 30
**Status:** issues_found

## Summary

The security posture holds: CSP is closed-by-default with `script-src 'self'` in production
and no `unsafe-eval` anywhere; `contextIsolation`/`nodeIntegration:false`/`sandbox:true`/
`webSecurity:true` are intact in both windows and asserted by `csp.test.ts`; path traversal in
`LocalArchiveSource._resolve_id` is correctly closed (resolve-then-`relative_to`, verified by
the parametrized traversal tests); the ComicInfo XXE/billion-laughs guard is genuine. No
security regression found.

Correctness is a different story. Three defects block this phase:

1. **The `!` separator collision silently 404s every page of any series whose name contains
   `!`** — reproduced against the real source. Manga titles with `!` are commonplace.
2. **The RD-09 retention mechanism is found and it is CSS**: `.reader-page--preload img` drops
   the size constraints the visible page carries, so the four off-screen preload pages are laid
   out at full intrinsic resolution (2000×3000) instead of viewport scale. This is the code that
   makes RSS track decode-window size, exactly as the harness measured.
3. **The chapter offline-cache in `SourceEngine` is dead code in production** — a new engine is
   constructed per request, so the cache is always empty. The test that proves it works reuses a
   single engine and therefore tests a path production never takes.

## Critical Issues

### CR-01: `!` in any path segment makes every page of the chapter unreadable (404)

**File:** `apps/backend/nyanko_api/sources/local_archive.py:26,164,176-179`

**Issue:** `ARCHIVE_MEMBER_SEPARATOR = "!"` is used to join an archive id to a ZIP member, but
`pages()` emits page ids built from raw filesystem paths without ever escaping or rejecting `!`.
`page_bytes()` then splits on the *first* `!` in the whole id, so any `!` in a series folder,
chapter folder, or page filename is misparsed as the archive/member boundary.

Reproduced against the real source with a realistic title:

```
pages() OK        -> ['0:Oh My Goddess!/Cap 1/001.jpg']
page_bytes FALLA  -> SourceNotFoundError: Archivo local no encontrado
```

The failure is silent and total: `chapters()` lists the series, the reader opens, `/api/manga/pages`
returns 200 with a full page list, and then *every* `<img>` 404s. The user sees an empty reader with
a correct page counter. Titles containing `!` are common in manga (`Yotsuba&!`, `Bakuman!`,
`Oh My Goddess!`, `Shirobako!`), so this is not a corner case — it is a whole class of libraries
that cannot be read. This is the phase's core value proposition failing.

**Fix:** Do not overload a legal filename character as a structural delimiter. The lazy correct fix
is to split on the archive suffix rather than the first `!`, so the boundary is derived from the
data instead of guessed:

```python
async def page_bytes(self, page: SourcePage | str) -> SourcePageContent:
    page_id = page.source_id if isinstance(page, SourcePage) else page
    # El separador solo es estructural DESPUES de una extension de archivo: un "!" en
    # "Oh My Goddess!/Cap 1/001.jpg" es parte del nombre, no una frontera.
    archive_id, member = page_id, None
    for extension in ARCHIVE_EXTENSIONS | UNSUPPORTED_ARCHIVE_EXTENSIONS:
        marker = f"{extension}{ARCHIVE_MEMBER_SEPARATOR}"
        index = page_id.lower().find(marker)
        if index != -1:
            archive_id = page_id[: index + len(extension)]
            member = page_id[index + len(marker) :]
            break
    _, _, candidate = self._resolve_id(archive_id)
    ...
```

Add a regression test with `!` in the folder name, the chapter name, and the page filename, plus a
`.cbz` whose *own* path contains `!` (`0:Oh My Goddess!/Cap 2.cbz!1.jpg`) — that last one is the case
the current `split("!", 1)` gets wrong in both directions.

---

### CR-02: Preload pages are laid out at full intrinsic resolution — this is the RD-09 retention

**File:** `apps/desktop/src/styles.css:413-416`, `apps/desktop/src/ReaderView.tsx:464-477`

**Issue:** This is the mechanism the phase is looking for. The decode window itself is sound —
`decodeWindow` is correct, capped at 5, and `ReaderView` genuinely mounts only the windowed pages
(no `createObjectURL`, no bitmap kept in JS state, no cache surviving the window; the comment at
`ReaderView.tsx:33-34` is accurate). The leak is not retention past the window. It is that **each
page inside the window costs far more than it should**, and it is caused by CSS:

```css
.reader-page--visible img { display: block; max-width: 100%; max-height: 100%; object-fit: contain; }
.reader-page--preload   { position: absolute; top: 0; left: -100000px; pointer-events: none; }
.reader-page--preload img { display: block; max-width: none; max-height: none; }   /* <-- */
```

`.reader-fit-width .reader-page--visible img { width: 100% }` (line 417) targets `--visible` only.
So:

- The **visible** page is constrained to the stage and decodes at roughly viewport scale.
- The **four preload** pages have every size constraint explicitly removed and no `width`, so they
  lay out at intrinsic size — 2000×3000 in the harness. Each one is a full-resolution image in the
  render tree (`left:-100000px` moves it, it does not remove it from layout or paint, unlike
  `display:none` or `content-visibility:hidden`).

Two consequences, both bad:

1. **Memory scales with window size at full-resolution cost per slot** — precisely the behaviour the
   harness measured (620 MB at window 5, 153 MB at window 1). Shrinking the window shrinks the number
   of full-res off-screen images, which is why the measurement responds to window size. It is tracking
   real bitmap retention, and this CSS is what it is tracking.
2. **The preload is functionally wasted.** Because the preload renders at 2000px and the visible page
   renders at ~stage width, they need *different* decodes. The full-res preload decode is not the one
   reused when the page scrolls into view — Chromium re-decodes at display scale. So these elements pay
   maximum memory for zero decode reuse.

Aggravating factor: `.reader-page--preload` is absolutely positioned inside `.reader-pages`, which is
`position: relative` and **always** carries a transform (`ReaderView.tsx:462`, `transformacion` is
`translate(0px, 0px) scale(1)` even at rest). That makes `.reader-pages` the containing block and a
transform/stacking root whose paint bounds must span from `-100000px` to the stage width. Oversized
composited-layer bounds are a known Chromium memory pathology and plausibly explain why the per-slot
cost measures well above the raw 24 MB bitmap. Treat the full-res decode as the proven cause and the
layer bounds as the likely amplifier — profile after the fix rather than assuming.

**Fix:** The preload's only job is to warm the cache. It does not need a live, full-size, rendered
element to do that. Drop the off-screen DOM entirely and warm the HTTP cache instead — smaller diff,
no layout box, no decode, no oversized layer:

```tsx
// ReaderView.tsx — render ONLY the visible group; warm the rest of the window with no DOM.
useEffect(() => {
  const controller = new AbortController();
  for (const indice of ventana) {
    if (paginasVisibles.includes(indice)) continue;
    const pagina = paginaPorIndice.get(indice);
    // Solo calienta la cache HTTP: sin elemento vivo no hay layout, ni decode, ni bitmap.
    if (pagina) void fetch(pagina.url, { signal: controller.signal }).catch(() => {});
  }
  return () => controller.abort();
}, [paginaPorIndice, paginasVisibles, ventana]);
```

```tsx
{paginasVisibles.map((indice) => {          // era: ventana.map(...)
  const pagina = paginaPorIndice.get(indice);
  if (!pagina) return null;
  return (
    <div key={pagina.index} className="reader-page reader-page--visible">
      <img src={pagina.url} alt={pagina.filename} decoding="async" draggable={false} />
    </div>
  );
})}
```

Then delete `.reader-page--preload` and `.reader-page--preload img` from `styles.css`. The response
already carries `Cache-Control: private, max-age=3600` (`main.py:1518`), so the warmed page paints
from cache on turn.

If the team prefers keeping rendered preload elements, the minimum viable fix is to give them the
same box as the visible page and take them out of paint — but this is strictly worse than the above
and still pays for decodes at the wrong scale:

```css
.reader-page--preload { position: absolute; inset: 0; content-visibility: hidden; pointer-events: none; }
.reader-page--preload img { display: block; max-width: 100%; max-height: 100%; object-fit: contain; }
```

Re-run `npm run test:reader-rss` after the change — the harness is the acceptance evidence, and it
is already wired to fail loudly (`reader-rss.mjs:442-447`).

---

### CR-03: `SourceEngine` chapter cache is dead in production; its test exercises a path prod never takes

**File:** `apps/backend/nyanko_api/main.py:1097-1099`, `apps/backend/nyanko_api/sources/engine.py:76-100`, `apps/backend/tests/test_source_engine.py:74-81`

**Issue:** `SourceEngine.chapters()` implements a deliberate offline fallback — on `SourceError`,
serve the last known good chapter list from `self._chapters`:

```python
except SourceError:
    if key in self._chapters:
        return list(self._chapters[key])
    raise
```

But every request builds a brand-new engine:

```python
def _source_engine(request: Request) -> SourceEngine:
    registro: SourceRegistry = request.app.state.source_registry
    return SourceEngine(registro)          # <-- instancia nueva por request
```

`self._chapters` is therefore always `{}` at the start of every request. The `if key in self._chapters`
branch can never be true in production, and `self._chapters[key] = list(fresh)` writes into a dict that
is discarded when the response ends. The entire cache — and the fallback it exists to power — is dead
code. `/api/manga/chapters` will hard-fail on any transient source error even though the code was
written specifically to prevent that.

This is masked by the test, which is the more serious problem: `test_chapters_returns_good_cache_after_source_parse_error`
(and `test_empty_chapters_are_parse_error_and_do_not_cache_empty_list`, which asserts `engine._chapters == {}`)
construct **one** engine and call it twice. The test is green and proves nothing about the deployed
behaviour. "Tests pass" is not evidence here.

**Fix:** Build the engine once and hold it on `app.state` alongside the registry, so its lifetime
matches the registry it wraps. Both rebuild points already exist (`main.py:1469`, `2130`, `2146`):

```python
def _source_engine(request: Request) -> SourceEngine:
    return request.app.state.source_engine
```

```python
# lifespan (main.py:1469) y en add_library_folder / delete_library_folder:
app.state.source_registry = build_source_registry(library_folders=database.get_library_folders())
app.state.source_engine = SourceEngine(app.state.source_registry)
```

Note the registry rebuild on folder mutation intentionally drops the cache with it — that is correct,
since the root keys change. Then add a test that goes through the API surface (two `TestClient` GETs
against `/api/manga/chapters` with the source failing on the second) so the assertion covers the path
production actually uses.

## Warnings

### WR-01: `preventDefault()` in `onWheel` is a no-op — React registers wheel as a passive listener

**File:** `apps/desktop/src/ReaderView.tsx:263-275`

**Issue:** `alUsarRueda` calls `event.preventDefault()` in three places, including the `ctrlKey` zoom
branch. React attaches `wheel` (along with `touchstart`/`touchmove`) at the root container with
`passive: true` — this has been true since React 17 and is unchanged in the React 19.1 used here.
`preventDefault()` inside `onWheel` therefore does nothing except emit *"Unable to preventDefault
inside passive event listener invocation"* to the console. Consequences: ctrl+wheel triggers Electron's
native page zoom **and** the reader's own zoom simultaneously, and in paged mode the wheel still
performs native scrolling underneath the page turn.

**Fix:** Register the listener manually with `{ passive: false }` and drop the `onWheel` prop:

```tsx
useEffect(() => {
  const raiz = modo === "vertical" ? contenedorVertical.current : escenarioPaginado.current;
  if (!raiz) return;
  // passive:false explicito: React registra wheel como passive y preventDefault se ignora.
  const alRodar = (event: WheelEvent) => { /* misma logica, con preventDefault efectivo */ };
  raiz.addEventListener("wheel", alRodar, { passive: false });
  return () => raiz.removeEventListener("wheel", alRodar);
}, [modo, mover, ajustarZoom]);
```

Verify by holding ctrl and scrolling: today the whole UI zooms alongside the page.

---

### WR-02: Closing the reader within 500 ms of the last page turn loses that page's progress

**File:** `apps/desktop/src/ReaderView.tsx:184-191`

**Issue:** The progress write is debounced 500 ms, and the effect cleanup unconditionally cancels the
pending timer:

```tsx
const temporizador = window.setTimeout(() => { void api.setReaderProgress(...); }, PROGRESS_DEBOUNCE_MS);
return () => window.clearTimeout(temporizador);
```

On unmount (Escape, `onClose`, chapter change) the cleanup runs and the pending write is dropped, never
flushed. A user who turns to page 50 and immediately closes the reader reopens on page 49 or earlier.
The debounce is correct for the steady-state case; the missing part is the flush on teardown. Reading
position is the one piece of state this feature exists to keep.

**Fix:** Flush on unmount using a ref holding the latest page, so the cleanup does not re-run per page:

```tsx
const paginaPendiente = useRef(paginaActual);
paginaPendiente.current = paginaActual;

useEffect(() => {
  if (!listo || total === 0) return;
  return () => {
    // El debounce se cancela al desmontar; sin este flush la ultima pagina leida se pierde.
    void api.setReaderProgress(SOURCE_NAME, chapter.source_id, paginaPendiente.current).catch(() => {});
  };
}, [chapter.source_id, listo, total]);
```

---

### WR-03: Reader progress and prefs are keyed by an unstable library-folder id

**File:** `apps/backend/nyanko_api/sources/local_archive.py:265-279,304-305`, `apps/backend/nyanko_api/database.py:228-233,273-289`

**Issue:** `_load_roots` uses the DB row's `id` as the root key, and `_make_id` bakes it into every
`source_id` (`"3:Serie/Cap 1"`). Those `source_id`s are then persisted as the primary keys of
`reader_prefs.series_id` and `reader_progress.chapter_id`. But `library_folders.id` is
`INTEGER PRIMARY KEY AUTOINCREMENT` — removing a folder and re-adding the same path yields a **new**
id, so every stored reading position and per-series preference for that library silently orphans.
The user's progress across their entire manga library vanishes after one remove/re-add in Settings,
with no error. Nothing ever cleans the orphan rows either, so they accumulate.

**Fix:** Key the root on something stable across re-add — the folder path is the natural candidate,
and `library_folders.path` already carries a `UNIQUE` constraint. Hashing it keeps ids opaque and
short while surviving re-add:

```python
raw_key = folder.get("path") if isinstance(folder, Mapping) else folder
root_key = hashlib.sha256(str(Path(str(raw_key)).resolve()).encode()).hexdigest()[:12]
```

This is a migration: existing rows keyed by the old numeric ids need mapping or a documented reset.
If that cost is not acceptable in 0.2.x, at minimum stop deleting `library_folders` rows on removal
(soft-delete with a `removed_at` column) so ids are never reused.

---

### WR-04: A folder holding both images and subfolders is treated as a chapter, hiding its subfolders

**File:** `apps/backend/nyanko_api/sources/local_archive.py:87-106`, `apps/desktop/src/MangaLibraryView.tsx:68-74`

**Issue:** `is_chapter = not is_directory or has_images` classifies any directory containing at least
one loose image as a chapter. `MangaLibraryView.abrir()` then routes it to the reader instead of
navigating into it, and `pages()` returns only the loose images — the subdirectories become
unreachable. The very common layout

```
Serie/Vol 1/cover.jpg
Serie/Vol 1/Cap 1/001.jpg
Serie/Vol 1/Cap 2/001.jpg
```

renders `Vol 1` as a bogus one-page "chapter" and makes Cap 1 and Cap 2 unopenable from the UI.

**Fix:** A directory with subdirectories is a container, not a chapter — images beside them are art,
not pages:

```python
has_children = is_directory and any(child.is_dir() for child in path.iterdir())
is_chapter = not is_directory or (has_images and not has_children)
```

---

### WR-05: `read_page` streams library files with no instance-token check

**File:** `apps/backend/nyanko_api/main.py:1507-1529`

**Issue:** `/assets/pages/{page_id}` performs no authentication, while the extension endpoints in the
same file gate on `X-Nyanko-Instance` with `secrets.compare_digest` (`main.py:3312-3314`, `3356-3359`,
`3411-3414`). CORS does not help: `<img src="http://127.0.0.1:PORT/assets/pages/...">` from any web page
is not a CORS-restricted load, so any site the user visits can probe the port range and use image
`load`/`error` events as an oracle for whether a given page id exists — leaking library structure and
filenames. Path traversal is properly closed, so this is confined to files genuinely inside a
registered root; that is what keeps it a Warning rather than Critical.

The `/assets` mount has the same property today, so this is consistent with existing posture rather
than a new hole — but this endpoint is new in this phase and is the right place to stop widening the
unauthenticated surface.

**Fix:** Apply the same gate the extension routes already use:

```python
@app.get("/assets/pages/{page_id:path}")
async def read_page(
    page_id: str,
    request: Request,
    source: str = "local_archive",
    x_nyanko_instance: str | None = Header(default=None),
) -> Response:
    if not x_nyanko_instance or not secrets.compare_digest(
        x_nyanko_instance, request.app.state.instance_token
    ):
        raise HTTPException(status_code=403, detail="Nyanko instance token required")
```

Note this requires the renderer to stop using bare `<img src>` for pages (headers cannot be attached to
an image load). If that trade is not worth it in this phase, the cheaper mitigation is a single-use or
time-scoped token embedded in the page URL itself by `_page_url`. Either way, record the decision
rather than leaving it implicit.

---

### WR-06: `double_page_offset` is unbounded at the API boundary

**File:** `apps/backend/nyanko_api/models.py:70-74`, `apps/desktop/src/readerWindow.ts:29`

**Issue:** `ReaderPrefsUpdate.double_page_offset: int | None = None` accepts any integer and
`set_reader_prefs` writes it straight through. `pagePairs` only ever tests `offset === 1`, so any
other value silently degrades to 0. The stored value then round-trips into a `<select>` whose options
are 0 and 1 (`ReaderView.tsx:403`), leaving the control showing a value the DB does not hold. No crash,
but it is an unvalidated write at a trust boundary that makes the persisted state and the UI disagree.

**Fix:** Constrain it to the two values that mean anything:

```python
double_page_offset: Literal[0, 1] | None = None
```

## Info

### IN-01: `stopPropagation` on the reader controls is dead code

**File:** `apps/desktop/src/ReaderView.tsx:364`

**Issue:** `<header className="reader-controls" onClick={(event) => event.stopPropagation()}>` guards
against clicks bubbling into the page-turn handler, but `.reader-controls` is a **sibling** of
`.reader-stage` (both are children of `.reader`), not a descendant. `alHacerClick` is bound to the
stage, so header clicks never reach it and there is nothing to stop.

**Fix:** Delete the handler. If it was added to fix a real click-through, that bug is elsewhere and is
still live — worth confirming before removal.

---

### IN-02: `eventosEmitidos` grows unbounded across a reading session

**File:** `apps/desktop/src/ReaderView.tsx:64,157-158`

**Issue:** The dedup set is a ref that persists for the lifetime of the mounted `ReaderView`. Because
`onChapterChange` swaps the `chapter` prop without unmounting, a long session adds one `source_id`
string per chapter finished and never removes any. Small and bounded by session length rather than a
true leak, but it is unbounded-by-construction state in the component the phase's memory ceiling
targets.

**Fix:** Nothing needed for 0.2.x. If it ever matters, dedup server-side on
`(source_name, chapter_id)` in `insert_reading_event` — the row is the real dedup key and Phase 5 will
want it there anyway.

---

_Reviewed: 2026-07-16_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
