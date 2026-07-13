# Architecture Research — v0.3 «Nyanko lee manga»

**Domain:** Manga reader + versioned source-adapter engine + offline downloads, integrated into a shipped Electron + Python-sidecar tracker
**Researched:** 2026-07-13
**Confidence:** HIGH for everything grounded in the codebase (every claim below cites a real file:line I read). MEDIUM/LOW for the two external facts (AnimeThemes API shape, RAR handling) — flagged inline.

> **Framing.** This is a SUBSEQUENT milestone. The existing architecture is load-bearing. Almost every question below already has an answer *in the repo* — the job is to find the precedent and follow it, not to design a second mechanism next to it. The single biggest risk in 0.3 is not building the wrong reader; it is building a **parallel** sync path, a **parallel** background-job mechanism, and a **parallel** asset pipeline alongside three that already work.

---

## Standard Architecture

### System Overview (existing = solid lines, new = `+`)

```
┌────────────────────────────────────────────────────────────────────────────┐
│  RENDERER (React/Vite, sandbox:true, contextIsolation:true, webSecurity)    │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────────┐ ┌─────────────────┐  │
│  │ Library  │ │Discovery │ │ Torrents │ │ +ReaderView│ │ +DownloadsView  │  │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └─────┬──────┘ └────────┬────────┘  │
│       └────────────┴────────────┴─────────────┴─────────────────┘           │
│                              │                                              │
│              ┌───────────────┴────────────────┐                             │
│              │  src/api.ts  (HTTP → sidecar)  │  src/native.ts (20 ops)     │
│              │  + normalizeAssetUrls()        │  → window.nyanko            │
│              └───────────────┬────────────────┘         │                   │
└──────────────────────────────┼──────────────────────────┼───────────────────┘
                    HTTP 127.0.0.1:<dynamic port>    contextBridge IPC
                               │                          │
                               │              ┌───────────┴─────────────┐
                               │              │ ELECTRON MAIN           │
                               │              │ sidecar.ts (spawn+gate) │
                               │              │ ipc.ts (handlers)       │
                               │              │ tray/updater/discord    │
                               │              └─────────────────────────┘
┌──────────────────────────────┼─────────────────────────────────────────────┐
│  PYTHON SIDECAR (FastAPI, nyanko-api.exe)                                   │
│                                                                             │
│  ┌─────────────────── main.py (routes) ────────────────────────────────┐    │
│  │  /api/library  /api/media/{id}/entry  /api/playback/*  /api/torrents│    │
│  │  + /api/manga/sources  + /api/manga/{}/chapters                     │    │
│  │  + /api/manga/chapters/{id}/pages   + /api/manga/downloads          │    │
│  └────────┬──────────────────────────────────────┬─────────────────────┘    │
│           │                                      │                          │
│  ┌────────┴────────────┐            ┌────────────┴───────────────────┐      │
│  │ providers.py        │            │ + sources/  (NEW package)      │      │
│  │  ProviderRegistry   │  ← mirror →│   SourceRegistry               │      │
│  │  MediaProvider(Prot)│            │   MangaSource (Protocol)       │      │
│  │  anilist/mal/kitsu  │            │   SOURCE_API_VERSION = 1       │      │
│  └────────┬────────────┘            │   local_archive.py (1st)       │      │
│           │                         │   <src_a>.py  <src_b>.py       │      │
│           │                         └────────────┬───────────────────┘      │
│           │                                      │                          │
│  ┌────────┴──────────────────────────────────────┴─────────────────────┐    │
│  │  http.py  RateLimitedClient + retry_with_backoff   (SHARED)          │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  Background threads (lifespan) │ Disk                                       │
│  ┌───────────────┐             │ %APPDATA%\app.nyanko.desktop\              │
│  │ MutationWorker│──edit_entry─┤   nyanko.sqlite3                           │
│  │ TorrentChecker│             │   assets/  ──► mounted at  /assets  ◄─┐    │
│  │ LibraryWatcher│             │     {provider}/{id}/cover.jpg          │    │
│  │ DetectorMgr   │             │     + manga/{...}/001.jpg   (NEW dir)  │    │
│  │ +DownloadWkr  │─────────────┤     + themes/{id}/{slug}.ogg (NEW dir) │    │
│  └───────────────┘             │   port, instance_token                 │    │
│                                └────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────┘
                                          ▲
                          `<img src>` / `<audio src>` hits /assets directly
                          (unauthenticated StaticFiles mount — main.py:1436)
```

### Component Responsibilities

| Component | Responsibility | NEW / MODIFIED / UNTOUCHED |
|-----------|----------------|---------------------------|
| `apps/backend/nyanko_api/sources/` (package) | Source-adapter engine: registry, versioned Protocol, capabilities, first-party sources | **NEW** |
| `apps/backend/nyanko_api/manga.py` | Page pipe: resolve a chapter → list of `/assets/...` URLs (from archive, from cache, or fetched) | **NEW** |
| `apps/backend/nyanko_api/downloads.py` | `DownloadWorker` thread, mirrors `MutationWorker` | **NEW** |
| `apps/backend/nyanko_api/animethemes.py` | AnimeThemes client next to `anilist.py` / `kitsu.py` | **NEW** |
| `apps/backend/nyanko_api/main.py` | +~10 routes, +`DownloadWorker` in `lifespan` (l.1388), +`SourceRegistry` build | **MODIFIED** |
| `apps/backend/nyanko_api/database.py` | +5 tables in `SCHEMA` (l.14), bump `CANONICAL_SCHEMA_VERSION` 7→8 (l.273), +accessors | **MODIFIED** |
| `apps/backend/nyanko_api/models.py` | +Pydantic models (`SourceInfo`, `SourceManga`, `SourceChapter`, `SourcePage`, `DownloadJob`) | **MODIFIED** |
| `apps/backend/nyanko_api/http.py` | Fix D-I-03 (`requests_per_minute=90` vs AniList's 30) — **required before online sources land** | **MODIFIED** |
| `apps/backend/nyanko_api/providers.py` | UNTOUCHED. The reader does not add a provider. | untouched |
| `apps/desktop/src/api.ts` | +manga/download/themes calls. `normalizeAssetUrls` (l.202) needs **zero change** | **MODIFIED** |
| `apps/desktop/src/ReaderView.tsx` | The reader UI | **NEW** |
| `apps/desktop/src/native.ts` + preload + `ipc.ts` | **Likely UNTOUCHED** — see Q7 | untouched (probably) |
| `apps/desktop/electron/main/*` | UNTOUCHED. No new main-process responsibility. | untouched |

---

## Q1 — Where does the source-adapter engine live?

### Decision: **the Python sidecar.** New package `apps/backend/nyanko_api/sources/`.

Not hedging: **Python. Electron main loses.**

**Why Python wins**

1. **The registry pattern already exists there, and it is exactly the right shape.** `providers.py` has `MediaProvider` (a `typing.Protocol`, l.47), `ProviderCapabilities` (a frozen dataclass of feature flags, l.28), `ProviderRegistry` (register/get/all, l.351), and `build_provider_registry()` (l.372). A source engine is a second instance of this exact structure with different verbs. Building it in Python is *copying a file*; building it in main is *inventing the pattern again in another language*.
2. **The page-delivery decision (Q2) forces it.** The chosen pipe fetches pages **with adapter-supplied headers** and writes them to `settings.assets_dir` for the `/assets` StaticFiles mount. Both the header knowledge and the asset dir live in the sidecar. Putting adapters in main means main must either duplicate the fetcher, or call back into the sidecar for every page — a pointless round trip.
3. **Everything the engine needs already exists in the sidecar and nowhere else:** `RateLimitedClient` + `retry_with_backoff` (`http.py`), the `cache` table + `cached_value`/`cached_list` helpers (`main.py:183-230`), the SQLite connection, the background-thread lifecycle (`lifespan`, l.1388). In Electron main there is no DB handle, no HTTP client with rate limiting, no cache. The JS version starts by re-implementing all four.
4. **Electron main is the *wrong process* for untrusted parsing.** Main runs with full Node privileges and no sandbox. HTML/JSON from a scraped manga site is the most attacker-adjacent input in the app. The sidecar is a separate OS process with no Electron powers — if a parser blows up, it blows up there. (This matters more, not less, the day third-party adapters arrive.)

**The one honest argument for main (JS), and why it still loses:** the long-term ecosystem play is community adapters, and JS/TS is the lingua franca for that (Mihon = Kotlin APKs — explicitly ruled out in PROJECT.md; Aidoku = WASM). But **third-party hot-loading is Out of Scope for 0.3** (PROJECT.md, "Fuera de Scope"). Choosing the harder host today to serve a capability we've explicitly deferred is paying interest on a loan we haven't taken. If community adapters ever land, the sandboxing problem needs solving *regardless* of language — and a Python engine can host a WASM/JS adapter runtime later just as well as main can.

### The versioned adapter API

`apps/backend/nyanko_api/sources/base.py` — **NEW**:

```python
# Contrato de fuentes. Espejo deliberado de providers.py: Protocol + capabilities
# + registry, mismos nombres, misma forma. Si te resulta familiar, es a propósito.
SOURCE_API_VERSION = 1   # entero, SOLO major. Sin minors: YAGNI.

@dataclass(frozen=True, slots=True)
class SourceCapabilities:
    search: bool = True
    popular: bool = False     # catálogo "populares" navegable
    latest: bool = False      # catálogo "últimas actualizaciones"
    page_headers: bool = False  # sus imágenes exigen Referer/UA → ver Q2

@dataclass(frozen=True, slots=True)
class SourcePage:
    url: str                          # http(s)://  |  file://  (archivo local)
    headers: dict[str, str] = field(default_factory=dict)  # ← Referer vive AQUÍ

class MangaSource(Protocol):
    id: str                 # "mangadex", "local"  → estable, es clave de BD
    display_name: str
    api_version: int        # DEBE == SOURCE_API_VERSION
    lang: str
    capabilities: SourceCapabilities

    async def search(self, query: str, page: int = 1) -> list[SourceManga]: ...
    async def manga_details(self, manga_key: str) -> SourceMangaDetails: ...
    async def chapters(self, manga_key: str) -> list[SourceChapter]: ...
    async def pages(self, chapter_key: str) -> list[SourcePage]: ...
    # Opcionales, gated por capabilities (igual que discover/season en MediaProvider):
    async def popular(self, page: int = 1) -> list[SourceManga]: ...
    async def latest(self, page: int = 1) -> list[SourceManga]: ...
```

Four methods are mandatory: `search`, `manga_details`, `chapters`, `pages`. That is the whole contract. Everything else is capability-gated, exactly like `ProviderCapabilities.seasons` / `.activity` gate `MediaProvider.season()` / `.activity()` today.

**`SourcePage.headers` is the single most important line in this document.** The adapter returns the headers its CDN demands *as data*. The page fetcher stays generic and knows nothing about any specific site. Every other design (headers hardcoded in the fetcher, headers in a config map, a per-source `fetch()` override) leaks source knowledge out of the source.

**How the version is declared and checked** — `sources/registry.py`, **NEW**:

```python
class SourceRegistry:
    def register(self, source: MangaSource) -> None:
        if source.api_version != SOURCE_API_VERSION:
            # NO se cae el sidecar. La fuente queda fuera y la UI la muestra
            # como no disponible con el motivo. Una fuente rota nunca tumba la app.
            logger.warning(
                "source %s targets API v%d, engine is v%d — not registered",
                source.id, source.api_version, SOURCE_API_VERSION)
            self._rejected[source.id] = (source.api_version, "api_version_mismatch")
            return
        self._sources[source.id] = source
```

**What happens when an adapter targets an old API version:** it is *rejected at registration*, logged, and surfaced in `GET /api/manga/sources` as `{"id": ..., "available": false, "reason": "api_version_mismatch"}`. It never crashes the sidecar and never half-works. Because 0.3 ships only first-party sources compiled into the binary, this path is *only* reachable if someone forgets to bump a constant — so it also gets a **self-check test** (`tests/test_sources.py`) asserting every source in `build_source_registry()` has `api_version == SOURCE_API_VERSION` and that the registry is non-empty. This is the same insurance `native.test.ts` gives the native boundary: *the mapping cannot drift in silence.*

---

## Q2 — How do page images reach a sandboxed `<img>`? **THE DECISION**

### Chosen: **sidecar writes pages under `assets_dir/manga/…`; the renderer gets relative `/assets/...` URLs; the existing StaticFiles mount serves them.**

The pipe, precisely:

1. Renderer: `GET /api/manga/chapters/{chapter_id}/pages` (through `api.ts`'s `request()`).
2. Sidecar `manga.py` resolves the chapter to a local page directory:
   - **downloaded** → `assets_dir/manga/{source}/{manga_key}/{chapter_key}/001.jpg …` (permanent)
   - **local archive** → pages extracted from the CBZ/ZIP into the same layout (stdlib `zipfile`)
   - **online, not downloaded** → adapter's `pages()` → fetch each `SourcePage.url` **with `SourcePage.headers`** into `assets_dir/manga/_stream/{chapter_id}/…` (ephemeral read-cache)
3. It returns **relative** URLs: `["/assets/manga/…/001.jpg", …]`.
4. `api.ts` `normalizeAssetUrls()` (l.202-212) rewrites any string starting with `/assets/` to `${liveApiUrl}${value}` — **already written, already shipped, zero changes.**
5. `<img src="http://127.0.0.1:<live-port>/assets/manga/…/001.jpg">` — served by `app.mount("/assets", StaticFiles(...))` (`main.py:1436`), which is **unauthenticated by design** (an `<img>` cannot send `X-Nyanko-Instance`; that's exactly why covers already work this way).

**Every constraint is satisfied, and mostly for free:**

| Constraint | How it's met |
|---|---|
| `sandbox:true`, `contextIsolation:true` | It's a plain HTTP `<img>`. No IPC, no Node, no preload surface. |
| `webSecurity:true` | Same-scheme http from a localhost origin. `<img>` isn't CORS-gated anyway, and the mount is same-origin with the API. No CSP meta tag exists in `apps/desktop/index.html`, so no `img-src` change needed. |
| **Referer/hotlink headers** | The *sidecar* (httpx) makes the upstream request, with `SourcePage.headers`. The renderer never touches the source CDN. This is the requirement that kills option D outright. |
| **Memory pressure on prefetch** | Pages live on **disk**, not in the JS heap. Prefetch = "have the sidecar pull page N+1 to disk"; the browser's own image cache handles decode/eviction. No blobs, no `revokeObjectURL` discipline, no 40-MB `ArrayBuffer` graveyard. |
| **Port stability (D-I-02, the "no covers ever again" bug)** | URLs are stored/returned **relative** and composed against the *live* port at request time. `_asset_url()` (`main.py:317`) already documents this exact trap and this exact fix. Following it means the reader cannot regress it. |
| Downloaded ≡ local (requirement #3) | Both are just files under `assets_dir/manga/…`, returned by the same endpoint. "Downloaded chapters read like local ones" is not a feature to build — it's what falls out. |

**Losing options, and why they lost:**

- **B — Electron custom protocol (`protocol.handle("nyanko-page://…")` in main).** Legitimately works with `sandbox:true` (needs `registerSchemesAsPrivileged` before `app.ready`). It loses because **main would then have to do the upstream fetching**, which means the per-source Referer/UA rules have to live in main — i.e. the adapter engine (or a shadow copy of it) migrates to JS, contradicting Q1. It also puts CBZ extraction in main. Cost: a whole second HTTP/parsing stack in the privileged process, to solve a problem that a mount we *already have* solves. Rejected.
- **C — Blob URLs over IPC** (`native.getPage()` → `ArrayBuffer` → `createObjectURL`). Loses on **memory**, which is the reader's #1 failure mode: every page is structured-cloned across IPC, retained as an `ArrayBuffer` in the renderer heap *plus* its decoded bitmap, until someone remembers to `revokeObjectURL`. A prefetch-3-ahead reader on 4000px pages will sit at hundreds of MB and OOM-blank on long chapters. It also expands `native.ts` with a high-volume binary op, which is precisely what a *boundary* is supposed to stay thin. Rejected.
- **D — `<img src="https://source-cdn/page.jpg">` straight from the renderer.** Zero backend work, and dead on arrival: an `<img>` cannot set `Referer`, so hotlink-protected sources (most of them) return 403; and it would leak the user's IP/UA directly to the source. Rejected.
- **E — A dedicated streaming proxy endpoint** (`GET /api/manga/pages/{chapter}/{n}` that pipes bytes live, no disk). This is the closest runner-up and is *fine*; it just does strictly less than the chosen option for the same effort — no disk cache, so re-reading a page re-hits the network, and the download feature then needs a *second* code path to write files. The chosen design is "option E, but it keeps the bytes", which collapses streaming + caching + downloading into one mechanism.

**The one real cost of the chosen option, stated honestly:** the ephemeral `_stream/` read-cache grows. Mitigation is small and must not be forgotten: prune `assets_dir/manga/_stream/` on sidecar startup (in `lifespan`, next to `database.prune_playback_events(...)`, `main.py:1399`) and drop a chapter's dir when the reader closes it. Ship it as a `# ponytail:` with a stated ceiling: *nuke-on-startup + on-close; add an LRU by size if users complain.*

---

## Q3 — Data model

Five new tables. **`CANONICAL_SCHEMA_VERSION` 7 → 8** (`database.py:273`) — which triggers `_backup_before_migration()` (l.575) automatically, so users get a `nyanko.backup-v8-*.sqlite3` before the change. The additive `CREATE TABLE IF NOT EXISTS` style in `SCHEMA` (l.14) is the whole migration; no rewrite needed.

**The critical constraint: do not duplicate `media`, `library_entries`, or `external_identities`.** The tracker's identity graph already exists and already handles manga:

- `media(id, media_type='MANGA', chapter_count, volume_count)` — l.75. Manga is already first-class here.
- `external_identities(media_id, provider_id, external_id)` — l.123, `UNIQUE(provider_id, external_id)`. This is *already* "canonical media ↔ AniList/MAL/Kitsu id". Resolved by `database.canonical_media_id(provider, external_id)` (l.1973).
- `library_entries(media_id UNIQUE, status, progress, score)` — l.155. **This is where reading progress lives.** `progress` is chapters-read for a MANGA row, episodes-watched for an ANIME row. `database.py:721` literally already branches `chapter_count if media_type == "MANGA" else episode_count`.

So "a manga on a source → a tracker entry" needs **exactly one new edge**, not a new identity system:

```sql
-- 1. Fuentes registradas y su estado (activada, orden). El catálogo real vive en
--    el registry en memoria; esto solo persiste la preferencia del usuario.
CREATE TABLE IF NOT EXISTS manga_sources (
    id          TEXT PRIMARY KEY,          -- source.id ("mangadex", "local")
    enabled     INTEGER NOT NULL DEFAULT 1,
    position    INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 2. LA ARISTA. "este manga en esta fuente" ES "esta media canónica".
--    media_id → media(id) → external_identities → AniList/MAL/Kitsu
--                        → library_entries      → progreso
--    chapter_offset: las fuentes numeran distinto que AniList (mismo problema que
--    media_mappings.episode_offset resuelve para el detector — misma solución).
CREATE TABLE IF NOT EXISTS manga_source_links (
    source_id       TEXT NOT NULL,
    source_manga_key TEXT NOT NULL,        -- id opaco de la fuente
    media_id        INTEGER NOT NULL REFERENCES media(id) ON DELETE CASCADE,
    chapter_offset  REAL NOT NULL DEFAULT 0,
    is_primary      INTEGER NOT NULL DEFAULT 1,  -- la fuente por defecto para leer
    linked_at       TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (source_id, source_manga_key)
);
CREATE INDEX IF NOT EXISTS idx_manga_links_media ON manga_source_links(media_id);

-- 3. Capítulos. Identidad + estado de lectura EN LA MISMA FILA (no una tabla de
--    join aparte: un capítulo pertenece a una fuente y lo lee un usuario).
CREATE TABLE IF NOT EXISTS manga_chapters (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id    TEXT NOT NULL,
    source_manga_key TEXT NOT NULL,
    chapter_key  TEXT NOT NULL,            -- id opaco de la fuente
    number       REAL,                     -- 12, 12.5 → REAL, igual que episodes.episode_number
    volume       REAL,
    title        TEXT,
    lang         TEXT,
    published_at INTEGER,
    page_count   INTEGER,
    -- estado de lectura (posición de página = reanudar donde lo dejaste)
    read_at      TEXT,
    last_page    INTEGER NOT NULL DEFAULT 0,
    -- descarga
    downloaded_path TEXT,                  -- RELATIVO a assets_dir. NUNCA absoluto,
                                           -- NUNCA con host:puerto dentro (D-I-02).
    UNIQUE (source_id, source_manga_key, chapter_key)
);
CREATE INDEX IF NOT EXISTS idx_manga_chapters_manga
    ON manga_chapters(source_id, source_manga_key);

-- 4. Cola de descargas. CALCO de pending_mutations (database.py:256): mismas
--    columnas de estado, mismo worker, mismo backoff. Ver Q4.
CREATE TABLE IF NOT EXISTS manga_downloads (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    chapter_id   INTEGER NOT NULL REFERENCES manga_chapters(id) ON DELETE CASCADE,
    status       TEXT NOT NULL DEFAULT 'pending',  -- pending|active|done|failed
    pages_done   INTEGER NOT NULL DEFAULT 0,
    pages_total  INTEGER NOT NULL DEFAULT 0,
    attempts     INTEGER NOT NULL DEFAULT 0,
    next_attempt_at INTEGER NOT NULL DEFAULT 0,
    error        TEXT,
    created_at   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (chapter_id)
);

-- 5. Carpetas de manga local. CALCO de library_folders (database.py:226).
CREATE TABLE IF NOT EXISTS manga_folders (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    path       TEXT NOT NULL UNIQUE,
    recursive  INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

**Joins to existing tables (the whole point):**

| Need | Where it comes from | New table? |
|---|---|---|
| "How far have I read?" | `library_entries.progress` (existing, l.155) | **no** |
| "Which AniList/MAL/Kitsu id is this?" | `external_identities` (existing, l.123) via `canonical_media_id()` (l.1973) | **no** |
| "Title, cover, chapter count, synopsis" | `media_details_cache` (existing, l.175 — has `chapters`, `volumes`, `media_type`) | **no** |
| "Which manga is this, on this source?" | `manga_source_links.media_id` → `media.id` | yes (1 edge) |
| "Where did I stop *inside* chapter 12?" | `manga_chapters.last_page` | yes |
| Search/browse results from a source | the existing `cache` table (`main.py:183` `cached_value`) with a `source:` resource prefix; add to `CACHE_RESOURCE_LIMITS` (l.276) | **no** |

**Explicitly NOT duplicated:** `episodes` (l.113) stays anime-only — a "manga chapter" is not an "episode" and cramming it in there would mean a `episode_type='CHAPTER'` hack whose only payoff is a shared table nobody queries (`episodes` is written in two places and read in none: `database.py:1390, 1508`).

**Reuse note worth a look during planning:** `media_mappings(provider, site_identifier, media_id, episode_offset)` (l.40) is *structurally identical* to `manga_source_links`. It's the browser detector's "site id → canonical media + offset" table. Reusing it is tempting and would be one table lighter — but it would overload `provider` to mean both "browser site adapter" and "manga source", and `manga_source_links` needs `is_primary`. **Recommendation: keep them separate, but note the shape is a proven one.** (If the roadmapper wants the lazier call, reusing `media_mappings` is defensible and costs one fewer table.)

---

## Q4 — The download queue

### It runs in the sidecar, as a `threading.Thread` worker draining a SQLite table. There is a precedent and it is not subtle.

`MutationWorker` (`main.py:1254-1306`) is exactly this mechanism, already shipped:
- a `threading.Thread(daemon=True)` started in `lifespan` (l.1421-1422),
- draining rows from `pending_mutations` via `database.due_mutations(now)` (`database.py:752`),
- with exponential backoff (`delay = min(600, 10 * 2**attempts)`, l.1293) and `MUTATION_MAX_ATTEMPTS = 8`,
- writing terminal state back (`mark_mutation_done` / `mark_mutation_retry` / `mark_mutation_failed`),
- stopped on shutdown (l.1429).

`DownloadWorker` in a new `downloads.py` is that class with `manga_downloads` instead of `pending_mutations` and "fetch N pages to disk" instead of "send one mutation". It gets registered in `lifespan` next to its three siblings (`TorrentChecker`, `MutationWorker`, `LibraryWatcher`). **Do not invent an asyncio-task queue, a job library, or a second process.**

**How the renderer observes progress: polling `GET /api/manga/downloads`.**

The precedent here is equally explicit. The library backfill exposes an in-memory progress dict via a plain GET (`_backfill_progress`, `main.py:153`; `GET /api/library/backfill`, l.2054-2065) and the renderer polls it on an interval to drive the toast (`api.ts:313` `backfillStatus()`; `App.tsx:1303-1334`, the `backfill-toast`). Downloads follow it exactly — except the state is *durable* (it's in `manga_downloads`), so the endpoint reads the table instead of a dict, which is strictly better: a download queue must survive a restart, a backfill needn't.

**The losing options here, briefly:** SSE would be a new transport with no precedent in the repo. A WebSocket has *one* precedent (`/api/playback/stream`, l.4361) — but read it: it's a `while True: … await asyncio.sleep(1)` loop that polls `detector_manager.latest()` and pushes on change. It is a poll wearing a WebSocket costume, and it exists because playback candidates need sub-second latency. A download queue does not. **Polling every 1-2s is the house style, and matching it means zero new transport, zero new client teardown logic.**

---

## Q5 — Progress sync path (do NOT build a second one)

### The path already exists. Reading a chapter enqueues an `edit_entry` mutation. That's it.

Traced end to end in the code:

1. `database.enqueue_mutation(provider, account, kind, external_id, payload, media_id, event_id)` — `database.py:725`. Inserts into `pending_mutations`.
2. `MutationWorker._drain()` — `main.py:1278` — picks it up.
3. `_send_mutation(settings, row)` — `main.py:1230-1248`. For `kind == "edit_entry"`:
   ```python
   media_type = payload.pop("media_type", "ANIME")
   await media_provider.edit_entry(
       token, int(row["external_id"]), MediaEntryUpdate(**payload), media_type=media_type)
   ```
   **`media_type` is already threaded through.** It reaches `AniListProvider.edit_entry` / `MyAnimeListProvider.edit_entry` (which passes it to the MAL manga endpoints) / `KitsuProvider.edit_entry` — `providers.py:151, 240, 319`. Manga sync to all three trackers is *already wired*; it's the pre-0.3 "Manga como ciudadano de primera en `edit_entry`" item in PROJECT.md.
4. On success the worker marks the mutation done, flips the linked `playback_events` row to `confirmed` (l.1299-1300), and invalidates the account cache (l.1301).

Existing callers that prove the shape: `bulk_update_library_entry` (`main.py:3001`) and `update_progress` (`main.py:2517`).

**Where the reader hooks in — one new endpoint, ~15 lines, zero new sync code:**

```python
@app.post("/api/manga/chapters/{chapter_id}/complete", status_code=202)
async def complete_chapter(chapter_id: int, provider=..., account=..., database=...):
    ch = database.get_manga_chapter(chapter_id)
    media_id = database.manga_media_id(ch["source_id"], ch["source_manga_key"])  # el link
    external_id = database.external_id_for(provider, media_id)                   # ya existe
    progress = int(ch["number"] + link["chapter_offset"])

    database.set_library_progress(media_id, progress)     # efecto local inmediato
    database.mark_chapter_read(chapter_id)
    event_id = database.insert_playback_event(            # ← la actividad de lectura
        source="read", raw_title=title, anime_title=title,  #   entra en el timeline
        episode=progress, status="pending", provider_id=provider,
        canonical_media_id=media_id, ...)
    database.enqueue_mutation(                            # ← EL ÚNICO paso de sync
        provider, account, "edit_entry", external_id,
        {"progress": progress, "media_type": "MANGA"},
        media_id=media_id, event_id=event_id)
    return {"queued": True}
```

Three things fall out of reusing the queue instead of calling the provider directly:

- **Offline reading syncs when you reconnect.** The mutation just sits in `pending_mutations` and retries with backoff. A direct `await provider.edit_entry(...)` would throw and lose the progress.
- **D-I-03 (the AniList rate-limit debt) is defused, not aggravated.** PROJECT.md flags it: *"hoy es latente porque el backfill es secuencial; un reader que hace ráfagas lo despierta."* Enqueuing means the reader **cannot burst** — `MutationWorker` drains 10 at a time on a 3-second tick (`due_mutations(limit=10)`, `_stop.wait(3)`). The reader is structurally incapable of hammering AniList. *(The `RateLimitedClient(requests_per_minute=90)` vs AniList's 30 mismatch in `http.py:78` still needs fixing — but the reader stops being the thing that detonates it.)*
- **Reading shows up in the activity timeline for free**, because `insert_playback_event(source="read", …)` is the same mechanism `edit_media_entry` uses with `source="edit"` (`main.py:2869`), which is what already renders local edits in the timeline.

> **What "auto-sync on chapter completion" means in the reader:** the last page becoming visible → `POST /api/manga/chapters/{id}/complete`. Guard with the same idempotence `confirm_playback` uses (`manga_chapters.read_at IS NOT NULL` → no-op), so re-reading doesn't re-enqueue.
>
> **Also note:** `PUT /api/media/{id}/entry?media_type=MANGA` (`main.py:2825`) is the *synchronous* manga-edit path used by the UI's edit modal. The reader must **not** call it (it awaits the provider inline). It's the fallback if a queued mutation permanently fails, and the reference for what a correct manga edit looks like.

---

## Q6 — AnimeThemes

**Fetch lives in the sidecar:** new `apps/backend/nyanko_api/animethemes.py`, sitting alongside `anilist.py`, `kitsu.py`, `myanimelist.py`. It is *not* a `MediaProvider` (it has no library, no mutations, no auth) — it's a plain client class, and it uses the shared `RateLimitedClient` from `http.py`.

*Confidence MEDIUM (websearch, unverified against the live API — the phase must confirm):* the AnimeThemes API is public for reads (token auth only for protected write actions), rate-limits at **90 req/min**, and returns `X-RateLimit-*` + `Retry-After` on 429 — which `RateLimitedClient` + `retry_with_backoff` already handle natively, and whose 90/min default happens to be exactly right for this one. Look it up by external resource id (the AniList/MAL id we already store in `external_identities`), so no new title-matching is needed.

**Caching:** the existing `cache` table via `cached_list(database, key, ttl, model, loader)` (`main.py:205`) with an `account_cache_key`-style key of `themes:{anilist_id}`. Add `"themes:": 200` to `CACHE_RESOURCE_LIMITS` (`database.py:276`) so it self-prunes like `media:`/`season:`/`discover:`. Themes essentially never change → a long TTL (30 days) with the existing stale-while-revalidate behaviour is right.

**How audio reaches the sandboxed renderer:**

Start with the **zero-work option: hotlink the CDN.** The sidecar returns the AnimeThemes CDN URL; the renderer renders `<audio src={url} controls>`. `webSecurity:true` does not block remote media, `<audio>` isn't CORS-gated for simple playback, and there is **no CSP meta tag** in `apps/desktop/index.html`, so nothing needs relaxing. AnimeThemes runs its CDN as a public asset host.

```python
# ponytail: hotlink directo al CDN de AnimeThemes — 0 líneas de plumbing.
# Techo conocido: si empiezan a bloquear hotlinking (o si alguien pide OP/ED
# offline), la ruta de subida es EXACTAMENTE la de las portadas — bajar el .ogg a
# assets_dir/themes/{anilist_id}/{slug}.ogg y devolver la URL RELATIVA /assets/...,
# que normalizeAssetUrls ya compone contra el puerto vivo. Mismo patrón que Q2.
```

That escape hatch matters: the fallback isn't a redesign, it's *the same pipe the manga pages use*. If hotlinking breaks, themes join `/assets` and nothing else changes.

**Do not fetch on card open.** Themes are 2-8 MB. Fetch metadata (title/slug/url) with the card; fetch *audio* only on explicit play.

---

## Q7 — Does `native.ts` need new ops?

### Default answer: **no. Zero new ops.** The boundary stays at 20.

The reader does not touch the filesystem from the renderer, because **the sidecar reads the archives** (Python `zipfile`) and hands back HTTP URLs. That is the entire consequence of the Q2 decision — it's why Q2 "cascades into everything else."

- **Picking a manga folder** → `native.openFolderDialog()` **already exists** (`native.ts:39`, `ipc.ts:57`, preload l.20). The manga library follows the `library_folders` + scanner pattern the anime local library already uses (`database.py:226`, `scanner.py:22`).
- **Opening a chapter file in Explorer** → `native.revealItemInDir()` / `native.openPath()` already exist.
- **Reading pages** → HTTP, not IPC.
- **Fullscreen reading** → CSS + the existing window controls. Not a native op.

**The one op that might be genuinely needed, and only if UAT demands it:** `openFileDialog(filters)` — for "open this single .cbz right now" without registering a folder. If it's added, the checklist is mechanical and the self-check enforces it:

1. `apps/desktop/electron/main/ipc.ts` — `ipcMain.handle("dialog:open-file", …)` with `dialog.showOpenDialog({properties:["openFile"], filters:[{name:"Manga", extensions:["cbz","zip","cbr"]}]})`. **Filters are set in main, never passed by the renderer** — same rule as `openExternal`'s http/https allowlist (l.42) and `openLogsFolder`'s zero-payload rule (l.20).
2. `apps/desktop/electron/preload/index.ts` — `openFileDialog: () => ipcRenderer.invoke("dialog:open-file")`.
3. `apps/desktop/src/native.ts` — the method **and** the `NATIVE_OPS` entry (l.115).
4. `native.test.ts` (l.20) fails the build if you do 3 and forget the manifest, in either direction. That test is why the 0.2 stubs never shipped (PROJECT.md, Key Decisions) — it will catch this too.

**Anti-goal, stated explicitly:** do **not** add a `native.readFile(path)` / `native.getPageBytes()` op. That is option C from Q2 sneaking back in through the boundary, and it turns the thin, audited, 20-op surface into a general-purpose filesystem read primitive from a sandboxed renderer.

---

## Q8 — Suggested build order

Derived from the dependency graph above. **The piece that unblocks the most is the page pipe (`/api/manga/chapters/{id}/pages` → `/assets/...`) — everything downstream is a producer that feeds it.** But it can't be built without the adapter shape, so the engine skeleton goes first.

```
[1] Source engine + data model
       │  (SourceRegistry, MangaSource Protocol, SOURCE_API_VERSION,
       │   5 tables, schema v8)
       ├──────────────┬──────────────────────┐
       ▼              │                      │
[2] Page pipe + LocalArchiveSource + ReaderView   ◄── the keystone
       │  (zipfile → assets_dir → /assets → <img>)
       ├──────────────┬──────────────────────┐
       ▼              ▼                      ▼
[3] Progress sync  [4] Online sources    [5] Download queue
    (enqueue_mutation)  (2-3 adapters)       (DownloadWorker)
                             ▲                    │
                             └────── needs D-I-03 fix first
[6] AnimeThemes  ── independent of 1-5, parallelizable
[7] 0.2 debt: W-3 (tray), RELEASING.md ── independent
```

| # | Phase | Depends on | Why here |
|---|---|---|---|
| **1** | **Source engine + data model.** `sources/` package (registry, Protocol, `SOURCE_API_VERSION`, capabilities, self-check test) + the 5 tables + schema v8. **No UI.** | — | Nothing else can be built without the contract and the tables. This is the requirement deferred from 0.2, and it is the cheapest thing to get *wrong* and the most expensive to change later. Ship it with the version-check self-check test. |
| **2** | **Page pipe + local reading.** `manga.py` (chapter → `/assets/…` URLs), `LocalArchiveSource` as the **first adapter** (CBZ/ZIP/folder, stdlib `zipfile`, zero network), `manga_folders` scan, `ReaderView.tsx`. | 1 | **The keystone.** Proves the whole delivery decision end-to-end with no network, no rate limits, no scraping fragility in the way. If the pipe is wrong, you find out here, cheaply. Delivers a shippable slice: *"Nyanko reads my CBZ collection."* |
| **3** | **Progress sync on chapter completion.** `POST /api/manga/chapters/{id}/complete` → `enqueue_mutation`. | 2 | Tiny (~15 lines + the idempotence guard), and it is **the core value** of the milestone ("el progreso sube solo"). Do it immediately after 2, not last — the moment local reading works, reading *tracks*, and the milestone's thesis is proven before the expensive parts start. |
| **4** | **Online sources.** 2-3 first-party adapters against the Protocol. Page fetching with `SourcePage.headers`. **Fix D-I-03 (`http.py:78`) as part of this phase.** | 1, 2 | Now this is *just adapters* — the reader, the pipe, the DB and the sync are all already done and don't change. Also the phase where source fragility (HTML changes, Cloudflare, hotlink headers) shows up, so it deserves its own research pass. |
| **5** | **Download queue.** `manga_downloads` + `DownloadWorker` (clone `MutationWorker`) + `GET /api/manga/downloads` polling + downloads UI. | 2, 4 | Reuses the page fetcher from 2/4 verbatim, just eager and writing to a permanent dir. "Downloaded reads like local" needs no code — the pipe already can't tell the difference. Cannot precede 4 (nothing worth downloading from a local archive). |
| **6** | **AnimeThemes.** `animethemes.py` + cache + `<audio>` on the card. | — | Fully independent. Genuinely parallelizable, or a good low-risk phase to slot between the two expensive ones. |
| **7** | **0.2 debt.** W-3 (tray↔UI detection-pause), `RELEASING.md`. | — | Independent; keep it off the reader's critical path. (D-I-03 is *not* here — it's folded into 4, where it actually bites.) |

**Biggest unblocker, stated plainly:** phase **2**. Phase 1 is a prerequisite, but phase 2 is where the architecture becomes true or false. Everything after it — online sources, downloads, progress sync — is a producer plugging into a pipe that already runs.

---

## Anti-Patterns (the ones this codebase will actually fall into)

### AP-1: A second sync path
**What people do:** the reader `await`s `provider.edit_entry(...)` directly on chapter completion, because it's one line and it works on the happy path.
**Why it's wrong:** it loses progress when offline, it bursts AniList (waking D-I-03 — PROJECT.md predicts this *by name*), it skips the `playback_events` timeline, and it means two places now know how to sync — which will drift.
**Instead:** `database.enqueue_mutation(..., kind="edit_entry", payload={... "media_type": "MANGA"})`. `_send_mutation` (`main.py:1240`) already handles it.

### AP-2: Absolute URLs with the port baked in
**What people do:** the pages endpoint returns `http://127.0.0.1:8765/assets/manga/…/001.jpg`, or `manga_chapters.downloaded_path` stores an absolute URL.
**Why it's wrong:** this is **the exact bug** documented at `main.py:317-323` and repaired by `_migrate_asset_urls_to_relative` (`database.py:400`) — the day the sidecar starts on a different port, the *entire library loses every cover, permanently and silently.* A reader that persists page URLs re-creates it at ten times the scale.
**Instead:** persist and return **relative** `/assets/...` only. `normalizeAssetUrls` (`api.ts:202`) composes against the live port. There is even a guard script — `apps/backend/scripts/check_stale_asset_ports.py` — extend it to cover the new columns.

### AP-3: A second background-job mechanism
**What people do:** the download queue gets an `asyncio.Queue`, or a job library, or SSE for progress — because it "feels" more modern than a polling thread.
**Why it's wrong:** the app already has four background workers on one pattern (`MutationWorker`, `TorrentChecker`, `LibraryWatcher`, `DetectorManager`, all started in `lifespan`, `main.py:1414-1424`) and one progress-observation pattern (poll a GET; `App.tsx:1303`). A fifth mechanism is a second thing to debug at 3am, and the durable-retry-with-backoff logic already exists and is proven.
**Instead:** clone `MutationWorker` into `DownloadWorker`. Poll `GET /api/manga/downloads`.

### AP-4: Page bytes across the IPC boundary
**What people do:** `native.getPage()` → `ArrayBuffer` → blob URL, because "the renderer needs the bytes."
**Why it's wrong:** memory (see Q2, option C), and it converts the audited 20-op native boundary into a filesystem read primitive.
**Instead:** HTTP. The renderer never needs bytes; it needs a `src`.

### AP-5: Hardcoding Referer/User-Agent in the page fetcher
**What people do:** `if source_id == "xyz": headers["Referer"] = "https://xyz.com/"`.
**Why it's wrong:** source knowledge leaks out of the source. The engine stops being versionable.
**Instead:** `SourcePage.headers` — the adapter returns them as data (Q1).

---

## Integration Points

### Internal boundaries

| Boundary | Communication | Notes |
|---|---|---|
| Renderer ↔ sidecar (manga data) | HTTP JSON via `api.ts` `request()` | Carries `X-Nyanko-Instance` (`api.ts:226`). Unchanged pattern. |
| Renderer ↔ sidecar (page/audio bytes) | **Plain `<img>` / `<audio>` against `/assets`** | Unauthenticated StaticFiles mount (`main.py:1436`) — by design; an `<img>` can't send headers. Relative URLs only. |
| Renderer ↔ Electron main | `native.ts` (20 ops) | **No new ops** (Q7). |
| Sidecar ↔ manga sources | `httpx` via `RateLimitedClient` + adapter-supplied headers | The only process that talks to a source CDN. |
| Sidecar ↔ trackers | `pending_mutations` → `MutationWorker` → `providers.py` | **Reused verbatim.** No new code. |
| Reader ↔ tracker identity | `manga_source_links.media_id` → `media` → `external_identities` / `library_entries` | One new edge; the identity graph is untouched. |

### External services

| Service | Integration | Gotchas |
|---|---|---|
| Manga sources (2-3, TBD) | `sources/*.py`, HTML/JSON parse, `RateLimitedClient` | Hotlink protection → `SourcePage.headers`. Cloudflare / layout churn → fragility budget; deserves its own research pass in phase 4. |
| AniList / MAL / Kitsu | **existing** `providers.py` | `edit_entry(media_type="MANGA")` already works on all three. **`http.py:78` rate-limit mismatch (D-I-03) must be fixed before phase 4.** |
| AnimeThemes | `animethemes.py` + shared `RateLimitedClient` | *MEDIUM confidence:* public reads, 90 rpm, `Retry-After` honoured. Look up by AniList/MAL id from `external_identities`. Hotlink the CDN; `/assets` is the fallback. |
| CBR / RAR archives | — | **HIGH-confidence gotcha:** `rarfile` reads headers in pure Python but needs an **external binary** (`unrar`/`7z`/`bsdtar`) for any *compressed* entry. A PyInstaller onedir sidecar would have to ship one. **CBZ/ZIP/folders are 100% stdlib (`zipfile`) with zero deps.** Recommendation: ship CBZ/ZIP/folders in phase 2; treat CBR as a **separate, explicitly-scoped task** whose real cost is "ship and license a third-party decompressor," not "parse an archive." Do not let it silently expand phase 2. |

---

## Sources

- Codebase, read directly (**HIGH**): `apps/backend/nyanko_api/{main,database,providers,http,config,scanner}.py`; `apps/desktop/src/{native,native.test,api}.ts`; `apps/desktop/electron/{main/index,main/ipc,main/sidecar,preload/index}.ts`; `.planning/PROJECT.md`.
- Key line references: `main.py:1436` (`/assets` mount), `main.py:317` (relative-URL fix, D-I-02), `main.py:1230-1306` (`_send_mutation` + `MutationWorker`), `main.py:2054` + `App.tsx:1303` (backfill polling precedent), `main.py:2825` (`edit_media_entry`, manga first-class), `providers.py:28-103` (registry + Protocol shape to mirror), `database.py:14-271` (schema), `api.ts:202` (`normalizeAssetUrls`), `native.test.ts:20` (boundary self-check).
- [AnimeThemes API — Rate Limiting](https://api-docs.animethemes.moe/intro/ratelimiting/) (**MEDIUM** — websearch, verify against the live API in phase 6)
- [AnimeThemes API — Audio](https://api-docs.animethemes.moe/wiki/audio/) (**MEDIUM**)
- [rarfile — PyPI](https://pypi.org/project/rarfile/) / [rarfile docs](https://rarfile.readthedocs.io/) (**HIGH** — external binary required for compressed entries)

---
*Architecture research for: manga reader + source-adapter engine integrated into Nyanko (Electron + FastAPI sidecar)*
*Researched: 2026-07-13*
