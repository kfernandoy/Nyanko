# Stack Research

**Domain:** In-app manga reader (local archives + online sources), versioned source-adapter engine, chapter download queue, AnimeThemes OP/ED audio playback — added to a shipped Electron + Python-sidecar desktop app (Nyanko v0.2.3, Windows-only).
**Researched:** 2026-07-13
**Confidence:** HIGH

## Headline

**Almost nothing new gets installed.** The five new features need **zero new npm dependencies** and **at most one new Python dependency** (`beautifulsoup4`, and only for the HTML-scraping sources — a JSON-API source like MangaDex needs none).

Everything else is already in the tree:
- **Archives** → `zipfile` + `pathlib` (Python stdlib).
- **HTTP + rate limiting + `Retry-After` backoff** → `httpx` + `nyanko_api/http.py::RateLimitedClient` (already written, already used by AniList/MAL/Kitsu).
- **Image delivery to the sandboxed renderer** → the `/assets` StaticFiles mount + `normalizeAssetUrls()` in `api.ts` — the exact mechanism the codebase already built to kill the ephemeral-port bug (D-I-02).
- **Download-queue progress push** → the `@app.websocket("/api/playback/stream")` pattern already in `main.py`.
- **Reader UI + audio** → hand-rolled React + native `<audio>`/CSS. No library.

The two genuinely new *engineering* surfaces are the source-adapter contract and the download worker, and both are code, not dependencies.

---

## What Is Already Installed (checked, not assumed)

`apps/backend/pyproject.toml`:
```
fastapi>=0.116,<1 · httpx>=0.28,<1 · keyring>=25.7,<26 · psutil>=7.2.2
pydantic-settings>=2.10,<3 · uvicorn[standard]>=0.35,<1
dev: pytest, pytest-asyncio, pyinstaller>=6.11, ruff
```
No HTML parser. No archive lib. No image lib. No ORM (raw `sqlite3`).

`apps/desktop/package.json`:
```
deps:    @xhayper/discord-rpc, electron-log 5.4.4, electron-updater 6.6.2, react 19.1.1, react-dom 19.1.1
devDeps: electron 43.1.0, electron-builder 26, electron-vite 5, vite 7, typescript 5.9, sharp 0.35.2 (BUILD-TIME ICONS ONLY), tsx
```
No state lib, no router, no UI kit, no data-fetching lib. `sharp` is a **devDependency** — it is not in the shipped app and must not be used at runtime.

**Reusable seams found:**

| Seam | File | Reuse for |
|------|------|-----------|
| `RateLimitedClient` + `retry_with_backoff` (honors `Retry-After`) | `apps/backend/nyanko_api/http.py` | Every source adapter, AnimeThemes, download worker |
| `app.mount("/assets", StaticFiles(...))` → `data_dir/assets` | `main.py:1436`, `config.py:88` | Serving downloaded/cached manga pages |
| `normalizeAssetUrls()` — rewrites any `"/assets/…"` string in a response to `${apiUrl}/assets/…` at fetch time | `apps/desktop/src/api.ts:202` | **The port-stability answer.** See "The ephemeral-port trap" below. |
| `_migrate_asset_urls_to_relative` | `database.py:400` | Precedent + the reason the rule exists |
| `@app.websocket("/api/playback/stream")` | `main.py:4361` | Download-queue progress → renderer, no polling |
| `native.ts` (20 ops) | `apps/desktop/src/native.ts` | **Needs 0 or 1 new op.** See "Native boundary impact". |

---

## Recommended Stack

### Core Technologies

| Technology | Version | Lives in | Purpose | Why Recommended |
|------------|---------|----------|---------|-----------------|
| `zipfile` | stdlib (py3.11) | **Python sidecar** | Read CBZ/ZIP page entries | CBZ *is* a ZIP. Stdlib reads entries lazily without extracting (`ZipFile.open(name)` → file-like). Zero deps, zero PyInstaller risk, zero license risk. A `rarfile`/`py7zr`/`libarchive` dependency buys nothing that `zipfile` doesn't already give for the format that ~all manga actually ships in. |
| `pathlib` + `re` | stdlib | **Python sidecar** | Image-folder chapters; natural sort of `1.jpg, 2.jpg, 10.jpg` | `sorted(key=lambda p: [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", p.name)])` — 1 line. Do **not** add `natsort`. |
| `httpx` | 0.28.1 (**installed**) | **Python sidecar** | All source-adapter HTTP, page proxying, AnimeThemes | Already the app's only HTTP client. Async, HTTP/2, per-request headers → the adapter can set the `Referer`/`User-Agent` a hotlink-protected source demands. |
| `RateLimitedClient` | in-repo | **Python sidecar** | Per-source and per-API throttling | Already implements semaphore + interval + `Retry-After`-aware exponential backoff. Instantiate one **per source** with that source's limit. Its default (`requests_per_minute=90`) is *exactly* AnimeThemes' documented limit — verified `X-Ratelimit-Limit: 90`. |
| FastAPI `StaticFiles` @ `/assets` | in-repo | **Python sidecar** | Serve downloaded/cached pages | Already mounted at `settings.assets_dir` = `%APPDATA%\app.nyanko.desktop\assets`. Downloaded chapters land under it and are served with no new code. |
| Native `<img>` / `<audio>` / CSS scroll-snap | browser | **Renderer** | Reader viewport + OP/ED playback | Ladder rung 4: the platform already does paging (scroll-snap), lazy loading (`loading="lazy"`), prefetch (`new Image().src`), zoom (CSS `transform`), and Ogg/Opus decoding (`<audio>`). See "Reader UI" — the React libs are a worse fit than 200 lines of JSX. |
| SQLite (`sqlite3` stdlib) | stdlib | **Python sidecar** | Download-queue state, reading progress, source cache | Already the persistence layer. The queue must survive an app restart → it is rows in `nyanko.sqlite3`, not an in-memory list. |
| `asyncio.Queue` + `asyncio.Semaphore` | stdlib | **Python sidecar** | The download worker itself | A background task started in the FastAPI `lifespan` (which already exists, `main.py:1402`). See "What NOT to Add" for why this is not Celery/arq/RQ. |

### Supporting Libraries

| Library | Version | Lives in | Purpose | When to Use |
|---------|---------|----------|---------|-------------|
| `beautifulsoup4` | **4.15.0** (MIT) | **Python sidecar** | CSS-selector HTML extraction in scraping source adapters | **The only genuinely new dependency, and only if a first-party source is HTML-scraped.** Ships `soupsieve` (CSS `.select()`) transitively and runs on the stdlib `html.parser` backend → **no compiled extension, no DLL, nothing for PyInstaller to miss**. Mihon's adapters are jsoup + CSS selectors; `soup.select("div.chapter a")` is the same shape, which keeps the prior-art port mechanical. |

That's the whole list. One package.

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| `pytest` + `pytest-asyncio` (**installed**) | Adapter contract tests | Write **one conformance test parametrized over every registered source** — it is the thing that makes "versioned API" mean something instead of being a docstring. |
| `ruff` (**installed**) | Lint | `nyanko_api/sources/` inherits the existing config. |
| `pyinstaller` (**installed**) | Sidecar packaging | ⚠️ See the PyInstaller trap under "Source adapters". |

## Installation

```bash
# Python sidecar — the ONLY new dependency, and only for HTML-scraped sources.
# apps/backend/pyproject.toml → [project] dependencies:
#   "beautifulsoup4>=4.15,<5",
cd apps/backend && uv sync

# Electron / renderer
# (nothing)
```

If the 2–3 launch sources are all JSON-API-backed (MangaDex is — verified below), even this can be deferred to the first scraped source.

---

## The ephemeral-port trap (the one that already bit this codebase twice)

**Constraint:** the sidecar prefers `:8765` but `instance.py::resolve_port` silently falls back to a random free port when 8765 is taken. Any URL with a port baked into it is a time bomb — which is exactly bug D-I-02 (`database.py:400`: every cover in the library vanished, permanently and silently).

**The codebase already solved this. Do not invent a second mechanism.** The invariant is:

> **Nothing that contains a host or a port is ever persisted or transported. The renderer composes the absolute URL at render time from the port it just read.**

The two enforcement points already exist: `api.ts::normalizeAssetUrls` rewrites `"/assets/…"` → `${apiUrl}/assets/…` on every response, and `api.ts::resolveApiUrl` re-reads the `port` file through `native.readAppDataFile("port")`.

### Recommendation: pages are served by the sidecar, addressed by *count*, not by URL

Give the reader **one uniform page endpoint** for every kind of chapter:

```
GET /api/manga/chapters/{chapter_id}/pages        → {"count": 19, "external_url": null}
GET /api/manga/chapters/{chapter_id}/pages/{n}    → image/jpeg | image/png | image/webp bytes
```

The renderer builds `` `${await getApiUrl()}/api/manga/chapters/${id}/pages/${n}` `` **inside the render** and puts it straight in `<img src>`. **No page URL is ever stored in SQLite, returned in a JSON payload, or held across a restart.** The port trap is closed by construction — there is no URL to poison.

This gives four things for free:
1. **Local CBZ, downloaded chapter, and online source are the same URL shape.** The reader has one code path. "Downloaded chapters read like local ones" becomes literally true instead of a feature to build.
2. **Hotlink protection is solved.** Most manga CDNs 403 an `<img>` from a `file://` origin (no/incorrect `Referer`, wrong UA). The sidecar sets whatever headers the adapter declares. *MangaDex happens to reflect `Origin: null` and works direct — verified — but that is luck, not a plan; the second source will not.*
3. **`sandbox:true` / `contextIsolation:true` are untouched.** `<img src="http://127.0.0.1:PORT/…">` is a no-CORS subresource load; it needs no preload op, no Node in the renderer, no new native-boundary surface.
4. **HTTP caching + prefetch work.** Set `Cache-Control: private, max-age=…` on the page response and `new Image().src = nextPageUrl` warms Chromium's cache; the subsequent `<img>` paints instantly.

If a payload ever *must* carry a page URL, it emits a **relative** `/assets/…` path and rides the existing `normalizeAssetUrls` rewrite. Anything else is D-I-02 again.

**Rejected: a custom `nyanko://` protocol handler in Electron main** (`protocol.handle`, Electron 43). It is port-free, but it forces the archive-opening *and* the source-fetching logic into Node — duplicating what the sidecar already does with `zipfile`/`httpx`, and adding a Node archive dependency. It solves a problem the codebase has already solved a cheaper way. Skipped.

**Auth note:** the sidecar's `X-Nyanko-Instance` token is currently enforced on exactly one route (extension pairing, `main.py:3049`) — the rest of the API is open on loopback. An `<img>` **cannot send a header**, so if instance-token enforcement is ever widened, the page route must either be exempted or take the token as a query param. Flag it now so a future security pass does not silently blank every page.

---

## Archive reading — and the RAR trap

### Ship: CBZ / ZIP / image folders. Stdlib only. Zero dependencies.

`zipfile` opens entries lazily (`ZipFile.open()` returns a stream — a 19-page chapter never gets fully extracted to RAM or to disk). Sniff with `zipfile.is_zipfile()` so a `.cbz` that is secretly a RAR gives a clear error instead of a stack trace. That plus natural-sorting the entries and filtering to image extensions **is the entire local reader backend**, and it is maybe 40 lines.

### Do NOT ship CBR/RAR in v0.3. This is a licensing decision, not a technical one.

There is **no way to decode RAR without picking a poison**, and a plan agent must not pick one silently:

| Path | License reality | Verdict |
|------|-----------------|---------|
| `rarfile` 4.3 (ISC) + bundled `UnRAR.exe`/`UnRAR.dll` | `rarfile` itself is clean ISC — but it is only a **wrapper**; it shells out to an external binary you must ship. That binary is **RARLAB's UnRAR**, whose license permits free redistribution *inside other software packages* **only if** the docs state the code may not be used to build a RAR-compatible archiver, with attribution. It is **not** OSI-free (Debian/Fedora classify it non-free). | Legal for a free app **with paperwork**. Requires a licence notice shipped in the installer + repo. Not a decision an executor should make on its own. |
| Bundling 7-Zip's `7z.exe` | 7-Zip is LGPL — **except its RAR decoder, which carries the same unRAR restriction**. Same clause, extra binary. | No gain over UnRAR. |
| `libarchive` (BSD-2) via `libarchive-c` 5.3 (CC0) | libarchive has read support for RAR and RAR5 (since 3.4.0) under BSD. This is the only path that plausibly avoids the unRAR clause entirely — but the "not derived from unRAR" claim is *not* something I could verify from a primary source (MEDIUM confidence), and it costs a bundled `archive.dll` + CFFI, which is exactly the kind of thing PyInstaller onedir gets wrong. | Best license story, worst packaging story. |
| `py7zr` 1.1.3 (LGPL-2.1) | Pure Python, no binary. **Does not do RAR** — 7z only. CB7 is vanishingly rare for manga. | Irrelevant. Don't add it. |

**Recommendation:** v0.3 supports CBZ/ZIP/folders. `.cbr`/`.rar`/`.cb7` are detected by extension and surfaced with an explicit *"not supported — convert to CBZ"* message. CBR is then a **scoped, human-approved follow-up** (`rarfile` + bundled UnRAR + a `THIRD-PARTY-NOTICES` entry), not something that gets absorbed into a reader phase.

> `ponytail:` CBZ+folders covers the overwhelming majority of manga on disk. RAR support costs a redistributable-binary decision with legal text attached; that is not a cost a reader phase should pay by accident.

---

## Reader UI — hand-roll it. Honestly.

I checked the field. **There is no React manga-reader library.** There are React libraries that each do *one* of the pieces, and gluing four of them together is more code, more bytes, and more fights than writing the thing.

| Candidate | Current | Why it loses |
|-----------|---------|--------------|
| `swiper` 14.0.5 | 2026-07 | A carousel. Brings a Web-Component/CSS-module payload for something CSS `scroll-snap-type: x mandatory` does in **two CSS properties**, natively, with correct touch/inertia. Fighting it for keyboard nav, RTL manga direction, and double-page spreads costs more than not having it. |
| `embla-carousel-react` 8.6.0 | 2026-04 | Same story, smaller. Still a carousel abstraction over a problem the platform solves. |
| `react-zoom-pan-pinch` 4.0.3 | 2026-04 | The *closest* to useful. But it owns the transform on a wrapper element, which fights continuous/webtoon scroll mode — and Nyanko needs both modes in the same component. Wheel-zoom + drag-pan on a CSS `transform: scale()` is ~30 lines you fully control. |
| `@tanstack/react-virtual` 3.14.6 | 2026-07 | Solid library, wrong problem. Virtualizing **variable-height images whose height you don't know until they decode** is the pathological case for virtualizers (scroll-anchor jitter). `content-visibility: auto` + `loading="lazy"` gives the same win natively with zero jank. |
| `react-window` 2.2.7 | 2026-02 | Same, and worse at variable sizes. |

**Build it:** one `<Reader>` component, a `mode` prop (`paged` / `continuous` / `webtoon`), and:

- **Paged:** flex row + `scroll-snap-type: x mandatory` + `scroll-snap-align: center`. Arrow keys → `scrollIntoView`. RTL by `direction: rtl`. ~0 JS for the actual paging.
- **Continuous / webtoon:** a plain vertical column of `<img>` with `loading="lazy"` + `content-visibility: auto` + `contain-intrinsic-size`. Chromium does the virtualization.
- **Zoom:** `transform: scale(z)` on the page wrapper, `wheel` + `ctrl` handler, clamp. ~30 lines.
- **Prefetch:** `new Image().src = pageUrl(n+1); new Image().src = pageUrl(n+2)` in an effect. 3 lines. Works *because* the sidecar sets `Cache-Control` and the URL is stable within the session.

> `ponytail:` a hand-rolled reader is ~200 lines of JSX+CSS against ~4 dependencies that each solve a third of the problem and fight each other on the other two thirds. Add `react-zoom-pan-pinch` **only if** pinch-zoom on a touchscreen turns out to be genuinely fiddly — that is the single escape hatch, and it is a one-line install later.

---

## Source adapters: Python modules in the sidecar, `SOURCE_API_VERSION = 1`

### What an adapter *is*

**A Python class in `nyanko_api/sources/`, in-process in the sidecar.** Not a JS module. Not a declarative manifest. Not a plugin file loaded from disk.

Why:
- Adapters need HTTP + HTML parsing + rate limiting + cookies + per-source `Referer`/UA. `httpx`, `RateLimitedClient` and `retry_with_backoff` are **already there and already battle-tested against three providers**. A JS adapter in Electron main would rebuild all of it and then still have to hand bytes to the sidecar (or duplicate the page proxy).
- Third-party hot-loading is **explicitly out of scope** (PROJECT.md). Without it, a manifest format, a sandbox, and a permission model are all **speculative** — the entire reason those exist. YAGNI. Delete them from the design.
- A declarative manifest (URL templates + CSS selectors) is *seductive* and dies on the first source that needs a POST, a token scraped from a `<script>`, an obfuscated image-URL array, or a Cloudflare-ish flow. Mihon learned this — their adapters are code with helpers, not data. Study the *shape* of their `ParsedHttpSource` (search → details → chapter list → page list), not their delivery mechanism.

### The contract (v1)

```python
# nyanko_api/sources/api.py
SOURCE_API_VERSION: Final = 1

class Source(Protocol):
    api_version: ClassVar[int]      # must equal a supported version
    id: ClassVar[str]               # stable, persisted in SQLite — never renamed
    name: ClassVar[str]
    lang: ClassVar[str]

    async def search(self, query: str, page: int) -> list[MangaRef]: ...
    async def details(self, manga_id: str) -> MangaDetails: ...
    async def chapters(self, manga_id: str) -> list[Chapter]: ...
    async def pages(self, chapter_id: str) -> list[PageRef]: ...
    def page_request(self, page: PageRef) -> PageRequest:   # url + headers (Referer/UA)
        ...
```

`page_request()` is the load-bearing one: it is what lets the **generic page proxy** in `main.py` fetch any source's image with that source's required headers, without the proxy knowing anything about the source.

`Chapter` must carry `external_url: str | None`. **Verified empirically:** MangaDex chapters for officially-licensed series come back with `pages: 0` and `externalUrl: "https://viz.com/..."` — the adapter engine has to model "this chapter exists but is not readable in-app; open it externally" from day one, or Chainsaw Man's chapter list looks broken.

### What versioning looks like *in practice*

Modest, because it must be:

1. `SOURCE_API_VERSION: Final = 1` in `sources/api.py`.
2. Every source declares `api_version = 1`.
3. The registry refuses to register a source whose `api_version` is not in `SUPPORTED_VERSIONS`, and logs it. That check + a `CHANGELOG` section in `sources/api.py` **is the whole versioning system** for v0.3.
4. One `pytest` conformance test **parametrized over every registered source** asserts the Protocol is satisfied and the return shapes hold. This is what turns the contract from a docstring into a gate.
5. Breaking change later → bump to `2`, and either shim v1 or port the (first-party, therefore trivially portable) sources.

Do **not** build a version-negotiation layer, a capability-flags system, or a deprecation policy for a registry that contains three first-party classes.

### ⚠️ PyInstaller trap — this one will actually bite

**`pkgutil` / `importlib` auto-discovery of `nyanko_api/sources/*` will silently find zero sources inside the frozen onedir sidecar.** PyInstaller only bundles modules it can see via static import analysis; a dynamically-scanned package directory isn't one. It works perfectly in `dev.py` and ships an app with an empty source list.

**Fix (lazy and correct):** an explicit list, no scanning.
```python
# nyanko_api/sources/__init__.py
from . import mangadex, source_b, source_c
SOURCES: Final = [mangadex.Source(), source_b.Source(), source_c.Source()]
```
Static imports → PyInstaller sees them → they ship. Adding a source is one import + one list entry. (The alternative — `hiddenimports` in the spec file — is a second place to forget.)

### HTML parsing

`beautifulsoup4` 4.15.0 + stdlib `html.parser` backend, CSS selectors via `.select()`. **Do not add `lxml` or `selectolax`**: both are compiled extensions (more PyInstaller surface, bigger onedir) bought for a speed difference that is irrelevant when you parse *one page at a time on user interaction*. bs4 lets you swap in `lxml` with a single constructor arg if a profile ever says otherwise — so the cheap choice is also the reversible one.

### First source: MangaDex (verified live, 2026-07-13)

- `https://api.mangadex.org` — **no auth, no API key** for reads (verified HTTP 200 with only a `User-Agent`).
- Flow: `GET /manga?title=…` → `GET /manga/{id}/feed?translatedLanguage[]=en` → `GET /at-home/server/{chapterId}` → `{baseUrl}/data/{hash}/{filename}`.
- Page images: **no `Referer`, no auth needed**; `Cache-Control: public, max-age=604800, immutable`; CORS **reflects the `Origin`, including `null`** — so a `file://` renderer *could* load them direct. Proxy them through the sidecar anyway, so every source is uniform and the second source (which will not be this friendly) needs no new plumbing.
- Rate limit: ~5 req/s global; 429 carries `Retry-After` → `retry_with_backoff` **already handles it correctly, unchanged**.
- MangaDex's JSON API means **the first source needs no HTML parsing at all** — `beautifulsoup4` can land with source #2.

---

## Download queue

**Lives entirely in the Python sidecar.**

- **State:** a `manga_downloads` table in `nyanko.sqlite3` (`queued / downloading / done / failed`, chapter ref, progress, error). Rows, not RAM — the queue must survive a restart and an app crash.
- **Worker:** one `asyncio.Task` started in the existing FastAPI `lifespan` (`main.py:1402`), pulling from an `asyncio.Queue` rehydrated from SQLite on boot, with an `asyncio.Semaphore` for concurrency and the source's own `RateLimitedClient` for politeness. Stdlib. No broker, no Redis, no Celery/arq/RQ/dramatiq — those exist to cross a process boundary that does not exist here.
- **Storage format: write a `.cbz`.** `%APPDATA%\app.nyanko.desktop\assets\manga\{source_id}\{manga_id}\{chapter_id}.cbz`, written with `zipfile.ZipFile(mode="w", compression=ZIP_STORED)` (images are already compressed; re-deflating burns CPU for ~0%). Then **"downloaded chapters read like local ones" is not a feature — it is the absence of one**: the same `zipfile` reader path serves both, and the same `/api/manga/chapters/{id}/pages/{n}` endpoint serves both. One code path, three features.
- **Progress → renderer:** a WebSocket, mirroring the existing `@app.websocket("/api/playback/stream")` (`main.py:4361`). No polling, no new native op.
- **Atomicity:** write `chapter.cbz.part`, `os.replace()` on completion. A killed app leaves a `.part`, never a half-chapter that reads as complete.

## Progress sync (chapter finished → AniList/MAL/Kitsu)

**No new stack.** The provider clients and `edit_entry` already treat manga as first-class (PROJECT.md, pre-0.3). Finishing a chapter is a call into the existing mutation path.

⚠️ **This is the feature that detonates debt item D-I-03.** `RateLimitedClient(requests_per_minute=90)` vs AniList's actual `X-RateLimit-Limit: 30`. It has been latent only because backfill is sequential. A reader — page prefetch, chapter list hydration, a binge session firing progress updates — makes bursts the normal case. **Fix D-I-03 before or with the sync phase, not after.** The fix is a constructor argument (`requests_per_minute=30` for the AniList client), not a redesign.

## AnimeThemes — verified live against the API, 2026-07-13

| Fact | Value | Confidence |
|------|-------|------------|
| Base URL | `https://api.animethemes.moe` | **HIGH** — queried it |
| Auth | **None.** HTTP 200 with no key, no token. | **HIGH** — queried it |
| Rate limit | **`X-Ratelimit-Limit: 90`** per minute, per IP (`X-Ratelimit-Remaining` decrements) | **HIGH** — read the header |
| Lookup by provider id | `GET /anime?filter[has]=resources&filter[site]=AniList&filter[external_id]={id}` — `filter[site]` also accepts **`MyAnimeList`** and **`Kitsu`** (all three verified HTTP 200 with a match) | **HIGH** |
| Include chain for one round-trip | `include=animethemes.animethemeentries.videos.audio` | **HIGH** |
| Theme shape | `{ type: "OP"\|"ED", sequence, slug: "OP1" }` → `animethemeentries[]` → `videos[]` → `audio` | **HIGH** |
| **Audio asset** | `https://a.animethemes.moe/CowboyBebop-OP1.ogg` — **`Content-Type: audio/ogg`**, container OggS, codec **Opus** (sniffed the `OpusHead` magic), ~3.7 MB, `Accept-Ranges: bytes` (206 works → seeking works) | **HIGH** |
| Video asset | `https://v.animethemes.moe/CowboyBebop-OP1.webm` — 720p, ~30 MB | **HIGH** |

### Therefore: audio playback is a plain `<audio>` element. Nothing else.

Chromium ships Ogg/Opus decoding. `<audio src="https://a.animethemes.moe/….ogg" controls>` plays from the sandboxed `file://` renderer with **zero dependencies, zero native ops, zero sidecar involvement**. `<audio>` is a no-CORS media load — it does not care that the origin is `file://`.

**Three landmines, all verified, all cheap to avoid:**

1. **`HEAD` on the CDN returns `403 Forbidden`. `GET` returns `200`/`206`.** Any "does this asset exist?" probe written with `HEAD` will report every theme as missing. Use a ranged `GET` (or just don't probe — let `<audio>`'s `error` event tell you).
2. **The CDN sends no `Access-Control-Allow-Origin`.** So: **never set `crossOrigin` on the `<audio>` element, and never touch it with the Web Audio API or `fetch()`** — both require CORS and will fail. That kills waveform visualisers, volume analysis, and gapless crossfade unless you proxy through the sidecar first. Don't.
3. `Cache-Control: no-cache, private` on the asset → a replay re-downloads ~3.7 MB. Acceptable. If it ever isn't, proxy-and-cache into the existing `/assets` mount — but that is a real feature, not a freebie.

Prefer the **`.ogg` audio** over the `.webm` video on cards: 3.7 MB vs 30 MB, and a card wants a play button, not a video player.

`AnimeThemes` metadata fetching lives in the **sidecar** (`RateLimitedClient()` — its 90/min default is already exactly right), cached in SQLite keyed by provider+external_id. The renderer receives the `a.animethemes.moe` URL and drops it in `<audio src>`. The URL is a **remote absolute URL from an upstream service**, not a sidecar URL — persisting it is fine and does **not** re-open the port trap.

---

## Native boundary impact (`src/native.ts` — 20 ops today)

**Best case: zero new ops.** Everything the reader needs crosses through `fetch()` to the sidecar (which `api.ts` already resolves port-correctly) or through `<img>`/`<audio>` subresource loads. `sandbox:true`, `contextIsolation:true`, `nodeIntegration:false`, `webSecurity:true` all stay exactly as they are.

The **only** plausible new op is **"add a local manga folder"** — and `openFolderDialog()` **already exists**. So: likely genuinely zero.

If a real need appears (e.g. "reveal downloaded chapter in Explorer"), `revealItemInDir()` also already exists. Anything else must be justified against `NATIVE_OPS` and its bidirectional self-check (`native.test.ts`), which is the gate that caught the Phase-3 stubs.

---

## Alternatives Considered

| Recommended | Alternative | When the alternative would win |
|-------------|-------------|--------------------------------|
| Sidecar serves pages over HTTP | Electron `protocol.handle("nyanko://")` in main | If the sidecar didn't exist, or if archive+source logic already lived in Node. Neither is true. |
| `zipfile` (stdlib) | `rarfile` 4.3 + bundled UnRAR | Only when CBR support is an explicit, human-approved requirement with the licence notice budgeted. |
| `zipfile` (stdlib) | `libarchive-c` 5.3 (BSD) | If CBR is required **and** the unRAR clause is unacceptable (e.g. a distro wants to package Nyanko). Costs a bundled `archive.dll` through PyInstaller. |
| `beautifulsoup4` + `html.parser` | `selectolax` 0.4.10 / `lxml` 6.1.1 | If a source needs bulk parsing of hundreds of pages and profiling proves parse time matters. One-arg swap in bs4. |
| Hand-rolled reader | `react-zoom-pan-pinch` 4.0.3 | If touchscreen pinch-zoom proves genuinely fiddly. Single escape hatch; one-line install, later. |
| `asyncio.Queue` + SQLite | `arq` / Celery / RQ | Never, here. They exist to cross a process/host boundary the sidecar does not have. |
| `<audio>` element | `howler.js` / `wavesurfer.js` | Never. `wavesurfer` needs Web Audio → needs CORS → the CDN doesn't send it. It literally cannot work without a proxy. |
| Python adapters in-process | JS adapters in Electron main | Only when third-party hot-loading arrives (explicitly a later milestone) — and even then, sandboxing is the hard part, not the language. |

## What NOT to Add

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| `sharp` at runtime | It's a **devDependency** (icon generation). Adding it to the shipped app pulls a native module into an `asar`/`sandbox:true` app for image work nobody needs. | Nothing. The browser decodes images. |
| `Pillow` in the sidecar | Tempting for page dimensions / thumbnails. Unnecessary: `img.naturalWidth` gives dimensions free in the renderer, and a chapter thumbnail is just page 0 with `object-fit: cover`. | stdlib + CSS |
| `natsort` | 5 lines of `re.split` | stdlib `re` |
| `lxml` / `selectolax` | Compiled extensions → PyInstaller onedir surface, bigger bundle, for parse speed that is irrelevant at one page per click | `beautifulsoup4` + `html.parser` |
| `py7zr` | Doesn't do RAR (7z only), and CB7 manga barely exists | Nothing |
| Any RAR lib, silently | The unRAR clause is a **redistribution decision with legal text attached**. It must not arrive as a transitive detail of a reader phase. | Ship CBZ; escalate CBR as its own decision |
| `swiper` / `embla` / `react-window` / `@tanstack/react-virtual` | Each solves ~⅓ of the reader and fights the other ⅔; combined they exceed a hand-rolled reader in both bytes and code | CSS `scroll-snap` + `content-visibility` + `loading="lazy"` |
| `howler.js` / `wavesurfer.js` / Web Audio API | AnimeThemes' CDN sends **no CORS headers** → Web Audio cannot decode it. Physically blocked, not merely unnecessary. | `<audio>` |
| Celery / arq / RQ / Redis | A broker for an in-process queue in a single-user desktop app | `asyncio.Queue` + SQLite |
| SQLAlchemy / an ORM | The backend is raw `sqlite3` with hand-written migrations. Introducing an ORM for 2 new tables means two persistence idioms forever. | Follow `database.py` |
| A source **manifest** format (JSON/YAML selectors) | Dies on the first source needing a POST, a scraped token, or an obfuscated image array — i.e. approximately source #2 | Python classes behind a `Protocol` |
| A source sandbox / permission model | Third-party adapters are **out of scope this milestone**. Building the sandbox now is speculative security theatre for code you wrote yourself. | `SOURCE_API_VERSION = 1` + a conformance test |
| `pkgutil.iter_modules` source discovery | **Silently finds zero sources in the PyInstaller onedir build.** Works in dev; ships broken. | Explicit `from . import mangadex` + a `SOURCES` list |
| Persisting any absolute sidecar URL | This is bug D-I-02. It blanked every cover in the library, permanently. | Relative `/assets/…` (auto-rewritten by `normalizeAssetUrls`) or, better, no URL at all — just a page count |
| A `HEAD` request to `a.animethemes.moe` | Returns **403**. Verified. Your existence check will report every theme as missing. | Ranged `GET`, or the `<audio>` `error` event |

## Version Compatibility

| Package | Compatible with | Notes |
|---------|-----------------|-------|
| `beautifulsoup4` 4.15.0 | Python ≥3.11 (sidecar is 3.11+) | Pulls `soupsieve` (CSS `.select()`) transitively. Pure Python → PyInstaller picks it up with no `hiddenimports` entry. |
| `zipfile` / `asyncio` / `sqlite3` | stdlib, py3.11 | Nothing to pin, nothing to break |
| `httpx` 0.28.1 (installed) | `RateLimitedClient` builds one `AsyncClient` **per event loop** (`http.py:103`) | Reuse the existing class; a download worker on the main loop is fine. Do **not** hand a client across loops — the comment in `http.py` explains why. |
| Electron 43.1.0 | `sandbox:true` + `contextIsolation:true` | Unchanged. No new preload surface. Preload stays CommonJS (a sandboxed preload cannot be ESM — already learned in Phase 1). |
| React 19.1.1 | Hand-rolled reader | No new peer deps → no React-19 peer-range roulette (a real risk with the carousel libs). |

## Sources

- **AnimeThemes API** — `https://api.animethemes.moe/anime?filter[has]=resources&filter[site]=AniList&filter[external_id]=1&include=animethemes.animethemeentries.videos.audio` — queried live 2026-07-13; response shape, `X-Ratelimit-Limit: 90`, no-auth, `a.animethemes.moe/*.ogg` (`audio/ogg`, OggS/Opus magic bytes), `v.animethemes.moe/*.webm`, HEAD→403/GET→206, no `Access-Control-Allow-Origin`. **HIGH — primary source, first-hand.**
- **MangaDex API** — `api.mangadex.org` `/manga`, `/manga/{id}/feed`, `/at-home/server/{id}`, MD@Home page fetch — queried live 2026-07-13; no-auth reads, `externalUrl`+`pages:0` for licensed chapters, page CORS reflects `Origin: null`, `Cache-Control: public, max-age=604800, immutable`. **HIGH — primary source, first-hand.**
- **PyPI registry** (`pypi.org/pypi/*/json`, 2026-07-13) — `beautifulsoup4` 4.15.0 (MIT), `rarfile` 4.3 (ISC), `py7zr` 1.1.3 (LGPL-2.1), `libarchive-c` 5.3 (CC0), `lxml` 6.1.1 (BSD-3), `selectolax` 0.4.10, `Pillow` 12.3.0, `httpx` 0.28.1. **HIGH — registry.**
- **npm registry** (2026-07-13) — `react-zoom-pan-pinch` 4.0.3, `@tanstack/react-virtual` 3.14.6, `swiper` 14.0.5, `embla-carousel-react` 8.6.0, `react-window` 2.2.7. **HIGH — registry.**
- **UnRAR licence** — [Fedora Licensing:Unrar](https://fedoraproject.org/wiki/Licensing:Unrar), [ScanCode unrar-v3](https://scancode-licensedb.aboutcode.org/unrar-v3.html), [Sophos UnRAR legal notice](https://docs.sophos.com/esg/sgn/8-3/quickstart/en-us/common/thirdpartylegal/UnRARLegalNotice.html) — redistribution inside other software permitted with notice; may not be used to re-create RAR compression; classified **non-free** by Fedora/Debian. **HIGH.**
- **libarchive RAR5** — [libarchive/libarchive#1035](https://github.com/libarchive/libarchive/issues/1035), [libarchive-formats(5)](https://man.freebsd.org/cgi/man.cgi?query=libarchive-formats&sektion=5&n=1) — RAR5 read support since 3.4.0, BSD-2. The "not derived from unRAR" characterisation could **not** be confirmed from a primary source. **MEDIUM on the licence-purity claim, HIGH on the capability.**
- **Nyanko codebase** — `apps/backend/pyproject.toml`, `nyanko_api/{main,config,http,instance,database}.py`, `apps/desktop/package.json`, `src/{native,api}.ts`, `electron/main/{index,sidecar}.ts` — read 2026-07-13. **HIGH.**

---
*Stack research for: manga reader + source-adapter engine + download queue + AnimeThemes audio, on an existing Electron/Python-sidecar app*
*Researched: 2026-07-13*
