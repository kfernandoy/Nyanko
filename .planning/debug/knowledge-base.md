# GSD Debug Knowledge Base

Resolved debug sessions. Used by `gsd-debugger` to surface known-pattern hypotheses at the start of new investigations.

---

## manga-link-button-missing — flat-root manga library has no linkable rows and no working link confirm
- **Date:** 2026-07-17
- **Error patterns:** vincular, link button missing, no veo ningun vinculo, no aparece ningun boton, is_chapter, flat library, biblioteca plana, Serie local no encontrada, SourceNotFoundError, confirm_manga_link
- **Root cause:** Two-layer gap in flat-library (loose .cbz/.cbr directly at a registered root, no per-series subfolder) support: (1) `MangaLibraryView.tsx` gated the link button and its vinculos prefetch exclusively on `!capitulo.is_chapter`, and `local_archive.py`'s `chapters()` classifies every loose file as `is_chapter=True`, so a flat root had zero linkable rows anywhere; (2) after making the button clickable, `PUT /api/manga/link`'s pre-write existence check (`source.chapters(series_id)`) required `series_path.is_dir()` in `LocalArchiveSource.chapters()`, so it 404'd ("Serie local no encontrada") for any file-backed series_id.
- **Fix:** Introduced a "linkable series" axis distinct from `is_chapter` — `esVinculable(nodo, enRaiz) = enRaiz || !nodo.is_chapter` (`enRaiz = ruta.length === 0`), used by both the vinculos prefetch filter and the render gate. Gave `LocalArchiveSource.chapters()` file/dir duality (mirroring `pages()`): a file whose `parent == root` returns itself as a single-chapter series instead of raising; scoped strictly to `parent == root` so a nested chapter (`root/Serie/Cap.cbz`) still correctly 404s as non-series. `_series_title_from_id` strips the archive extension from loose-file series ids so the matcher gets a clean title.
- **Files changed:** apps/desktop/src/MangaLibraryView.tsx, apps/backend/nyanko_api/main.py, apps/backend/nyanko_api/sources/local_archive.py
---

