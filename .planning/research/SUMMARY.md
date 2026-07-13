# Project Research Summary

**Project:** Nyanko — milestone v0.3 «Nyanko lee manga»
**Domain:** In-app manga reader (local archives + scraped online sources) + versioned source-adapter engine + offline download queue + auto progress sync, added to a shipped Electron + Python-FastAPI-sidecar desktop tracker (Windows)
**Researched:** 2026-07-13
**Confidence:** HIGH

## Executive Summary

**The build is cheap; the correctness is expensive.** Four researchers converged on the same headline: v0.3 needs essentially **zero new dependencies** (one optional Python package, `beautifulsoup4`, and only for the first HTML-scraped source) and **zero or one new native op**. Archives are `zipfile`. HTTP + rate limiting + `Retry-After` backoff is `RateLimitedClient`, already shipped and already battle-tested against three providers. The download worker is a clone of `MutationWorker`. Progress sync is `enqueue_mutation(kind="edit_entry", payload={"media_type": "MANGA"})` — a path that already works end to end, because manga became first-class in `edit_entry` pre-0.3. The reader UI is ~200 lines of JSX against CSS `scroll-snap` + `content-visibility` + `loading="lazy"`; every React reader library solves one third of the problem and fights the other two. Even the source↔tracker mapping has a shipped precedent nobody noticed: `media_mappings(provider, site_identifier, media_id, **episode_offset**)` is *literally* the table this problem needs, offset column and all, built for the browser extension.

**So the work is not "can we build it" — it is "can we build it without corrupting a real 2,761-entry AniList library."** Every serious risk in this milestone is a **silent data-loss risk**, and most of them are already latent in code that exists today. `library_entries.progress` is `INTEGER` and manga chapter 10.5 has nowhere to go. The fuzzy matcher that correctly *proposes* an anime match would, wired eagerly to auto-sync, *durably* write chapter 12 of series A onto series B's AniList entry — and `pending_mutations` would faithfully retry it. `RateLimitedClient` is not a rate limiter but a concurrency limiter with a semaphore shared across two event loops; it has survived only because it never contends, and **fixing the "90 vs 30" number is what arms it**. A page URL persisted with the sidecar's ephemeral port in it re-creates, at ten times the blast radius, the bug that once silently blanked every cover in the library. None of these are hypothetical: each is cited to a file and a line.

**The recommended approach is therefore: pay all the foundations first, prove the thesis on local files before touching the network, and treat the identity binding as a phase, not a step.** Fix the rate limiter (all three of its bugs) and land the schema decisions *before anything writes a row*. Build the adapter engine with its per-source budget and error taxonomy in the contract — retrofitting a budget after the download queue exists means rewriting every adapter. Ship local CBZ reading as the keystone; it proves the page-delivery architecture with no network, no rate limits, and no scraping fragility in the way. Then bind, then sync — at which point the milestone's core value («el progreso sube solo») is *proven* before the two expensive chunks (online sources, downloads) start. Two things need a human decision before phase 2 closes, and both are in [Gaps](#gaps-to-address): which 2–3 online sources, and whether adapters are compiled into the binary (PROJECT.md's plan, maximum legal exposure) or loadable at runtime (the survivable posture, and — awkwardly — also the better engineering).

## Key Findings

### Recommended Stack

**Almost nothing new gets installed.** Zero new npm dependencies. At most one new Python dependency. The two genuinely new *engineering* surfaces — the source-adapter contract and the download worker — are code, not packages. Everything else is a seam that already exists in the tree and was built for a neighbouring problem.

**Core technologies:**
- **`zipfile` + `pathlib` + `re` (stdlib)** — CBZ/ZIP/image-folder reading. CBZ *is* a ZIP; `ZipFile.open()` streams entries lazily. The whole local reader backend is ~40 lines. Do not add `natsort` (5 lines of `re.split`), do not add `Pillow` (the browser decodes images).
- **`httpx` + `RateLimitedClient` + `retry_with_backoff` (in-repo)** — every source adapter, AnimeThemes, and the download worker. Already honours `Retry-After`. Instantiate **one per source**, with that source's declared budget. Must be fixed first — see Pitfall 1.
- **FastAPI `StaticFiles` @ `/assets` + `normalizeAssetUrls()` (in-repo)** — page delivery to the sandboxed renderer. This is the mechanism the codebase already built to kill the ephemeral-port bug. Do not invent a second one.
- **`asyncio`/`threading` + SQLite (stdlib)** — the download queue. Durable rows in `nyanko.sqlite3`, drained by a worker cloned from `MutationWorker`. No Celery, no arq, no Redis — they exist to cross a process boundary that does not exist here.
- **Native `<img>` / `<audio>` / CSS `scroll-snap` + `content-visibility`** — the reader viewport and OP/ED playback. The platform already does paging, lazy loading, prefetch, zoom, and Ogg/Opus decoding.
- **`beautifulsoup4` 4.15 (MIT) — the *only* new dependency**, and only when the first HTML-scraped source lands. Pure Python + stdlib `html.parser` backend → nothing for PyInstaller to miss. MangaDex is a JSON API, so this can be deferred to source #2.

**Verified live (2026-07-13):** MangaDex reads need no auth and return `externalUrl` + `pages: 0` for licensed chapters (model this from day one or Chainsaw Man's chapter list looks broken). AnimeThemes needs no auth, rate-limits at exactly **90/min** (matching `RateLimitedClient`'s default), serves `audio/ogg` (Opus), **`HEAD` returns 403 while `GET` returns 200/206**, and sends **no CORS headers** (so Web Audio, `crossOrigin`, and `wavesurfer` are physically impossible, not merely unnecessary).

Full detail: [STACK.md](STACK.md).

### Expected Features

Sorted by what makes the reader *credible*. The reference app is Mihon — but only for the reading model, **not** for the desktop surface (Mihon has no keyboard nav; it's a phone app. Copy Kavita/YACReader there).

**Must have (table stakes):**
- **Reading modes** — paged RTL (the manga default; opening L→R is broken on arrival), paged LTR, and **continuous vertical / webtoon** (half of what people read; undersold if you call it easy — tens of thousands of px of unknown-height images).
- **Per-series reading-mode memory** — a library holds both manga and webtoons. One column on the manga row. Do it day one; retrofitting means guessing defaults for existing users.
- **Desktop nav** — keyboard (←/→, PgUp/PgDn, Space, Home/End), mouse wheel, click zones, fullscreen, page counter, fit modes, zoom+pan.
- **Resume mid-chapter** (`last_page`) and **next/prev-chapter chaining with a transition screen** — the chaining is where "chapter finished" is *born*; it is the trigger point for sync.
- **Local files:** CBZ / ZIP / folder-of-images with **natural sort** (`2.jpg` before `10.jpg` — the #1 local-reader bug), `ComicInfo.xml` if present.
- **Chapter list** with number, **scanlator**, language, upload date, read state, and **five** download states (a half-downloaded chapter must not look readable). Plus sort/filter and **"mark previous as read"**.
- **Progress sync on reaching the last page** — Mihon's rule, verbatim. Floor decimals on the wire. **Monotonic guard.** One-way only (Nyanko → tracker).
- **Download queue** — batch enqueue, pause/resume/cancel, **serial per source / parallel across sources** (a hard constraint to avoid IP bans, not a tuning knob), atomic `.part` + rename, survives a crash.
- **AnimeThemes on cards** — list OP/ED, play audio, and **respect the `spoiler` / `nsfw` flags the API hands you**.
- **Debt D-I-03** — a *prerequisite*, not a cleanup item.

**Should have (competitive — cheap *because* Nyanko already has the surrounding app):**
- **Auto-suggested tracker link via the existing `matcher.py`** — Mihon's linking is 100% manual, always. Nyanko can *propose* with a confidence score. **Propose, never silently link.**
- **One reader over local + downloaded + online** — cheaper than three readers if the on-disk-format lever is pulled (emit CBZ; the downloader and the local reader must agree).
- **Chapter-finished confirm/undo + reading in the activity timeline** — the same interaction anime playback detection already has. This is what makes the reader feel like *Nyanko's* reader.
- **Double-page spread with manual offset** — Mihon literally marks this "TBA". A genuine desktop differentiator.
- **AnimeThemes at all** — nobody in this space does it.

**Defer (v0.3.x / v0.4+):**
- **CBR / RAR** — a *licensing* decision (unRAR's clause, or a bundled `archive.dll` through PyInstaller), not a technical one. Detect the extension and say "convert to CBZ". Escalate as its own scoped item; do not let it leak into a reader phase.
- EPUB/PDF (a different renderer entirely), theme playlists, AI upscaling, mini-player surviving navigation, auto-split wide pages, third-party hot-loaded adapters.

**Explicit anti-features** (requested, and wrong): a **"% read" completion threshold** (ambiguous, generates false positives → *corrupts the tracker*; long-strip makes % meaningless), **two-way sync** (conflict resolution on every chapter of every manga), **per-page progress to the tracker** (the trackers physically cannot store it — `$progress: Int!`), **parallel downloads within one source** (the fastest way to get every user's IP banned), and **copying Mihon's mobile settings screen** (volume keys, rotation lock — cargo cult).

Full detail: [FEATURES.md](FEATURES.md).

### Architecture Approach

**The existing architecture is load-bearing, and almost every question already has an answer in the repo.** The single biggest risk is not building the wrong reader — it is building a **parallel** sync path, a **parallel** background-job mechanism, and a **parallel** asset pipeline alongside three that already work and are proven.

**Major components:**
1. **`nyanko_api/sources/` (NEW)** — the adapter engine, in the **Python sidecar**, as a deliberate mirror of `providers.py` (Protocol + capabilities + registry, same shape, same names). Four mandatory methods (`search`, `manga_details`, `chapters`, `pages`); everything else capability-gated. **`SourcePage.headers` is the most important line in the design**: the adapter returns the `Referer`/UA its CDN demands *as data*, so the fetcher stays generic and source knowledge never leaks out of the source. `SOURCE_API_VERSION = 1`, checked at registration, enforced by a conformance test parametrized over every registered source. Python wins over Electron main because the registry pattern, the rate limiter, the cache table, the DB handle and the background-thread lifecycle **all already live there and nowhere else** — and because scraped HTML is the most attacker-adjacent input in the app, and main runs unsandboxed with full Node privileges.
2. **`nyanko_api/manga.py` (NEW) — the page pipe.** *The keystone.* Sidecar resolves a chapter → files under `assets_dir/manga/…` (extracted from CBZ, downloaded, or fetched with the adapter's headers) → returns **relative** `/assets/…` URLs → `normalizeAssetUrls()` composes them against the live port → `<img src>`. This single decision satisfies every constraint at once: `sandbox:true` untouched (it's a plain HTTP subresource, no IPC, no new native op), hotlink `Referer` solved (the sidecar makes the upstream request), memory bounded (pages live on **disk**; Chromium owns the decode and the eviction), the port trap closed by construction, and — critically — **"downloaded chapters read like local ones" stops being a feature and becomes the absence of one.** Same files, same endpoint, same code path.
3. **`nyanko_api/downloads.py` (NEW)** — `DownloadWorker`, a clone of `MutationWorker`: a daemon thread started in the existing `lifespan`, draining a durable `manga_downloads` table with the same exponential backoff. Progress observed by **polling `GET /api/manga/downloads`** — the house style (`backfill` already does exactly this). Not SSE, not a WebSocket, not a job library.
4. **Data model: 5 new tables, `CANONICAL_SCHEMA_VERSION` 7 → 8.** `manga_source_links` is **one new edge** — `(source_id, source_manga_key) → media_id [+ chapter_offset]` — because Nyanko's library entry **is** the tracker entry. Mihon needs three hops (source → local manga → Track → remote); Nyanko needs one. Do **not** duplicate `media`, `library_entries`, or `external_identities`; the identity graph already handles manga.
5. **Progress sync: no new code.** `POST /api/manga/chapters/{id}/complete` → `enqueue_mutation(...)` → `MutationWorker` → `providers.edit_entry(media_type="MANGA")`, which already works on all three trackers. ~15 lines. Reusing the queue gets you offline-syncs-on-reconnect, timeline activity, and burst-immunity **for free** — the worker drains 10 per 3-second tick, so the reader is *structurally incapable* of hammering AniList.
6. **`native.ts` stays at 20 ops.** Zero new ops is the default and probably the reality (`openFolderDialog` and `revealItemInDir` already exist). **Anti-goal, stated explicitly:** never add `native.readFile()` / `getPageBytes()` — that turns a thin, audited boundary into a general-purpose filesystem read primitive for a sandboxed renderer.

Full detail: [ARCHITECTURE.md](ARCHITECTURE.md).

### Critical Pitfalls

Ten of the twelve are **already latent in code that exists today**, each cited to a file and a line. These five are the ones that will actually hurt.

1. **D-I-03 is three bugs, not one — and "fix the number" is the trap.** (a) `requests_per_minute=90` vs AniList's 30. (b) `RateLimitedClient` **is not a rate limiter** — it holds the semaphore *during* the interval sleep, so `value=90` admits **90 simultaneous in-flight requests** with zero pacing. (c) The semaphore is a module-level singleton **shared across two event loops in two threads** (uvicorn's, and `asyncio.run()` inside the `MutationWorker` daemon thread). The author already fixed exactly this hazard for `_clients` (keyed per loop, with a comment explaining why) — **the semaphore never got the same treatment.** It has survived only because with `value=90` and a sequential backfill, `acquire()` never blocks, so no cross-loop waiter Future is ever created. **Changing 90 → 30 increases contention, makes `acquire()` block for the first time, and arms a dormant `RuntimeError`/silent-hang.** → Fix all three together, first, before any burst-producing feature exists. And **do not hardcode 30**: AniList's docs say 90/min is normal and 30/min is a *temporary degraded state*. Read `X-RateLimit-Limit` from the response and adapt.
2. **The renderer is `file://` in production** (`index.ts:83` → `loadFile`), so its origin is `null`. `fetch()` to a CDN is CORS-blocked, always. `<img>` isn't CORS-gated — but a `file://` page sends no useful `Referer`, and manga CDNs almost universally hotlink-protect → **403**. And in dev the renderer is `http://localhost:5173`, a *real* origin: **a reader that works perfectly for the entire implementation phase returns a wall of broken images the day it is packaged.** → No renderer-originated request ever leaves the machine. Every page byte flows renderer → sidecar → source. **Verify in a packaged build, not dev.** Also: there is currently **no CSP anywhere** in the app — add one with the reader (`img-src 'self' http://127.0.0.1:* blob: data:`), and never, ever relax `webSecurity`.
3. **The source↔tracker mapping is the worst failure in the milestone — treat it as data corruption, not UX.** The existing matcher is title-similarity based. That is exactly right for *proposing* a match to a human who confirms it. It is **catastrophic** as the silent input to an automatic write: user reads ch. 12 of series A → fuzzy match binds it to series B → the app silently sets progress on series B in the user's real AniList list → `pending_mutations` **retries it durably** → no undo, because nobody knew anything happened. The 5% mismatch rate is invisible in a demo and devastating in a 2,761-entry library. → The binding is **explicit, stored, and user-confirmed — never computed at sync time.** Auto-sync **fails closed** on an unconfirmed binding. Record `progress_before` on every sync (as `playback_events` already does) or there is no recovery at all. Mirror the playback detect→propose→confirm→undo flow that already works.
4. **Persisting a page URL with the sidecar's ephemeral port in it** — this project has *already* lost every cover in the library to this exact bug, and the reader is a far larger surface for it (page lists, download manifests, cache indexes, thumbnails are all URL-shaped data someone will want to persist). An offline-downloaded chapter that renders broken images is *worse* than the cover bug, because the user believes the bytes are safe on their disk. → **Relative paths or opaque IDs only**, resolved at render time. `normalizeAssetUrls` (`api.ts:202`) already does this. Extend `check_stale_asset_ports.py` to the new columns, and add a guard test that fails if any persisted column matches `LIKE 'http%'`.
5. **The legal exposure is real, and the takedown surface is the auto-updater.** Tachiyomi was killed in Jan 2024 by a Kakao C&D aimed at contributors *personally*; its concession was **removing the preloaded extension list**. Mihon ships **no sources at all** — that is load-bearing legal architecture, not a packaging preference. Nyanko as planned is **strictly worse than the project that got killed on every axis**: bundled first-party scrapers, written by a named author, in a code-signed, auto-updating binary. And because the updater feed *is* GitHub Releases (`app-update.yml`), a takedown does not merely break the download link — **it silently bricks auto-update for every installed user, permanently, with no channel left to reach them.** (Not hypothetical: v0.2.1/v0.2.2 releases already vanished and 404.) → **Decouple the update feed from the sources' takedown surface.** It is a small config change **now** and *impossible* later. Highest value-to-cost item in the entire milestone.

**Also load-bearing:** `library_entries.progress` is `INTEGER` and chapter 10.5 has nowhere to go (Pitfall 6); `killSidecar()` is `taskkill /T /F` with **zero flush opportunity**, so downloads need `.part` + atomic rename + startup reconciliation + archive verification (Pitfall 8); a page is a 200 KB JPEG on disk but a **24 MB decoded bitmap** in RAM, so the reader needs a bounded decode window and an **RSS number in its UAT criteria**, not a vibe (Pitfall 9); `Database.initialize()` runs every backfill on **every boot** and `schema_migrations` **gates nothing** (Pitfall 10); and a parse that finds **0 results must raise, never return `[]`** — silent-empty is how a Cloudflare challenge page (HTTP 200, HTML body) becomes "this chapter has 0 pages," cached (Pitfall 5).

**The seam risks are the ones no per-phase gate can catch** — and v0.2's retrospective already taught this lesson the hard way (B-1: two individually-correct phases combining into a silently-broken result that every gate passed). Seven candidates are enumerated in PITFALLS.md; the two structural answers are (a) **order phases so the seam lands *inside* a phase**, and (b) **budget an explicit cross-phase audit before the milestone closes** — that audit is the only control that caught B-1, and it caught it *after* every phase had passed.

Full detail: [PITFALLS.md](PITFALLS.md).

## Implications for Roadmap

Nine phases. The ordering is not stylistic — five of the constraints below are hard, and violating them is how this milestone ships its B-1.

### Phase 1: Foundations — rate limiter, schema, release-feed decoupling
**Rationale:** Everything in this milestone produces bursts, and everything writes rows. These three things are cheap now and **impossible or catastrophic to retrofit**. This phase exists because Pitfall 1 is armed by its own obvious fix, Pitfall 6 changes a column users will already have written to, and Pitfall 12's feed decoupling cannot be pushed to an app whose feed is already dead.
**Delivers:** `RateLimitedClient` rewritten — all three bugs (adaptive budget read from `X-RateLimit-Limit`, semaphore released *before* the interval sleep, keyed per event loop like `_clients` already is). Schema v8: the 5 new tables, `CANONICAL_SCHEMA_VERSION` 7→8 (which *fires the pre-migration backup* — the only rollback that exists). The **progress model, written down**: chapter numbers `REAL` locally, `floor()` on the wire, `library_entries.progress` stays `INTEGER` (no migration of an existing column against a real 2,761-entry DB), monotonic guard, `progress_before` recorded. Relative-URL-only storage contract + the guard test. Update feed moved off the sources' takedown surface.
**Addresses:** Debt D-I-03 (promoted from cleanup to prerequisite).
**Avoids:** Pitfalls 1, 3, 6, 10, 12 (the feed half). Seams A, C, E.
**Verification:** Burst 50 concurrent requests **from both event loops** — no `RuntimeError`, no hang. Migration exercised against a **copy of the real production DB** with `integrity_check` + row counts, not a fixture.

### Phase 2: Source adapter engine (no UI)
**Rationale:** The contract must exist before anything can be built against it, and it is the cheapest thing to get *wrong* and the most expensive to change later. This is the requirement deferred from 0.2.
**Delivers:** `nyanko_api/sources/` — `MangaSource` Protocol (4 mandatory methods), `SourceCapabilities`, `SourceRegistry`, `SOURCE_API_VERSION = 1` checked at registration (a bad source is *rejected and surfaced*, never crashes the sidecar). **`SourcePage.headers`** — per-source `Referer`/UA as data. **Per-source budget owned by the engine, not its callers** (reader prefetch and the download queue must draw from the *same* bucket, or two individually-correct limiters give you 2× the rate and a ban — Seam F). **Error taxonomy** — `ParseError` / `Blocked` / `SourceUnavailable` / `NotFound`; **0 results raises**, never returns `[]`; a failure never overwrites a good cached chapter list. `LocalArchiveSource` as the first adapter. A conformance test **parametrized over every registered source** — that test is what turns "versioned API" from a docstring into a gate.
**Uses:** `httpx` + the now-fixed `RateLimitedClient`. Mirrors `providers.py` structurally.
**Avoids:** Pitfalls 4, 5, and the policy half of 2. Seam F.
**Contains an open human decision** — bundled vs runtime-loadable adapters. See Gaps. Resolve it *in* this phase; the boundary cannot be retrofitted.
**PyInstaller trap:** `pkgutil`/`importlib` auto-discovery **silently finds zero sources in the frozen onedir build.** Works in dev, ships an empty source list. Use an explicit `from . import mangadex` + a `SOURCES` list.

### Phase 3: Page pipe + local reading — the keystone
**Rationale:** This is where the architecture becomes true or false, and it proves it with **no network, no rate limits, and no scraping fragility in the way**. If the page-delivery decision is wrong, you find out here, cheaply. Everything downstream — online sources, downloads, sync — is a producer plugging into a pipe that already runs.
**Delivers:** `manga.py` (chapter → files under `assets_dir/manga/…` → relative `/assets/…` URLs → the existing StaticFiles mount → `<img>`). `zipfile` CBZ/ZIP/folder reading with natural sort. `manga_folders` scan. `ReaderView.tsx`: paged RTL + LTR + continuous/webtoon, fit modes, zoom/pan, keyboard + wheel + click zones, fullscreen, page counter, **resume mid-chapter**, **chapter chaining** (which is where the "chapter finished" event is born), per-series mode memory. **The CSP lands here** — nobody else owns it (Seam G).
**Implements:** Architecture components 2 and 6.
**Avoids:** Pitfalls 9 (bounded decode window — and an **RSS number in the UAT criteria**, not "it feels fine"), 2, 3.
**Ships a real slice:** *"Nyanko reads my CBZ collection."*

### Phase 4: Identity binding — source manga ↔ tracker entry
**Rationale:** **Its own phase, deliberately.** It is tempting to fold this into the sync phase as "step 1" — that is precisely how it ends up eager and implicit, and it is the single highest-risk item in the milestone (Pitfall 3/7, Seam D). The sync phase must be able to *assume a trusted binding exists*, and be allowed to **refuse** when it doesn't.
**Delivers:** `manga_source_links` (mirroring the shipped `media_mappings` shape, `chapter_offset` included). `ChapterRecognition` as **its own named, pure, trivially-unit-testable component** (port Mihon's algorithm nearly verbatim — `extra` = .99, `omake` = .98, `12a` → 12.1; write the table of cases *first*). `matcher.py` **proposes** with a confidence score; the user **confirms**; `match_corrections` is the override. **Fail closed.**
**Avoids:** Pitfall 7. Seam D.
**Note:** `ChapterRecognition` is a *hidden* component — it belongs to neither the engine nor sync. Name it, or it gets smeared across both and tested in neither.

### Phase 5: Progress sync on chapter completion — the core value
**Rationale:** Tiny (~15 lines + an idempotence guard) and it is the milestone's thesis. Do it **immediately** after local reading works, not last: the moment reading *tracks*, the milestone is proven — before the two expensive chunks even start.
**Delivers:** `POST /api/manga/chapters/{id}/complete` → `enqueue_mutation`. Monotonic guard against the **tracker's** value. Floor on the wire, visibly. Re-read detection (`COMPLETED` + `chapter < progress` → offer REPEATING, never push `1`). `progress_before` recorded → confirm/undo, the same interaction anime playback already has. Reading lands in the activity timeline for free.
**Uses:** The existing `ProgressUpdate` + `pending_mutations` + `MutationWorker` path, verbatim. **Do not build a second sync path** (AP-1).
**Requires:** Phases 3 and 4, hard. Any roadmap that puts sync before binding is planning a fake phase.

### Phase 6: Online sources (2–3 first-party)
**Rationale:** By now the reader, the pipe, the schema and the sync are all done and *don't change*. This is "just adapters." It is also where source fragility (HTML churn, Cloudflare, hotlink headers) shows up.
**Delivers:** 2–3 adapters against the Protocol. Browse UI (popular / latest / search) + the chapter list (number, **scanlator**, language, upload date, read state, download state, sort/filter, "mark previous as read"). Online reading with **capped** prefetch (±2–3 pages, never "the whole chapter").
**Requires:** Phases 1 (the limiter), 2 (the engine), 3 (the pipe). The **feed decoupling from Phase 1 must be done before this ships.**
**Verification:** In a **packaged build** (`file://`), not dev — this is the phase where the dev/prod origin difference bites.
**Flagged for `--research-phase`.**

### Phase 7: Download queue
**Rationale:** The most expensive piece, and it can't precede online sources (there is nothing worth downloading from a local archive). It reuses the Phase 3/6 page fetcher verbatim — just eager, and writing to a permanent dir.
**Delivers:** `DownloadWorker` (clone `MutationWorker`), `manga_downloads`, `GET /api/manga/downloads` polling, the downloads UI. **Serial per source, parallel across sources.** Page lists resolved **at download time, not enqueue time** (signed/expiring URLs 404 on a chapter that sat in the queue for 20 minutes — this one detail invalidates the obvious design). `.part` + `fsync` + **atomic rename**, then mark complete. **Startup reconciliation** (any `downloading` row at boot was interrupted → reset + delete the `.part`) — one mechanism covering four bugs: the updater's hard kill, an app crash, Task Manager, and power loss. **Archive verification before marking complete.** Windows `MAX_PATH` handling. Updater **warn-and-resume** ("3 chapters are downloading — they'll resume after the update") — *in this phase*, not a later "polish" phase, because that is exactly the seam where it gets lost (Seam B).
**Avoids:** Pitfall 8. Seam B.
**Free win:** "Downloaded reads like local" needs **no code** — the pipe already can't tell the difference.

### Phase 8: AnimeThemes
**Rationale:** Depends on nothing, blocks nothing. Best value-to-cost ratio in the milestone, and the safest thing to cut if it runs long. Genuinely parallelizable — or a low-risk palate cleanser between the two expensive phases.
**Delivers:** `animethemes.py` + cache + OP/ED list on the card + play. **Zero fuzzy matching** — look up directly by the AniList/MAL/Kitsu id already in `external_identities` (all three `filter[site]` values verified working). **One** `<audio>` element, owned globally (fewer lines than per-card, *and* it makes "only one plays at a time" true by construction). Cache the **metadata**, not the CDN URL. Look up on **card open**, not on library render. Respect `spoiler` and `nsfw`.
**Avoids:** Pitfall 11.
**Gotchas already resolved:** `HEAD` → 403 (any existence probe reports every theme as missing — use a ranged `GET` or just let `<audio>`'s `error` event tell you). **No CORS headers** → never set `crossOrigin`, never touch it with Web Audio or `fetch()`. Prefer the 3.7 MB `.ogg` over the 30 MB `.webm`.

### Phase 9: 0.2 debt + cross-phase seam audit
**Rationale:** W-3 and RELEASING.md are independent — keep them off the reader's critical path. **The seam audit is not overhead; it is the control that works.** v0.2's cross-audit is the *only* thing that caught B-1, and it caught it after every individual phase had already passed.
**Delivers:** W-3 (tray ↔ UI detection-pause), `docs/extra/RELEASING.md` tracked. The cross-phase audit — PITFALLS.md's seam table **is** its checklist.
**Note:** D-I-03 is **not** here. It moved to Phase 1, where it belongs.

### Phase Ordering Rationale

**Five hard constraints** (everything else is negotiable):
1. **Rate-limit fix → before** the reader, downloads, and sync. It is currently filed as "0.2 debt." **It is a prerequisite.** Sweeping it up at the end is the single most likely way this milestone ships a B-1 (Seam A).
2. **Schema decisions → before anything writes a row.** Changing `progress` semantics after users have written rows means migrating a real library (Pitfalls 3, 6, 10).
3. **Adapter engine (with its budget + error taxonomy) → before** the online reader and the download queue. Retrofitting a per-source budget after the queue exists means rewriting every adapter (Seam F).
4. **Binding → before** progress sync. Not "step 1 of sync." Its own phase (Seam D).
5. **Feed decoupling → before** the first online source ships. A config change now; impossible later.

**Two groupings worth defending:**
- **Local reading before online sources** (Phase 3 before 6) inverts the "exciting feature first" instinct on purpose. The page pipe is the keystone, and testing it against a CBZ on disk removes network flakiness, rate limits, Cloudflare and scraping fragility from the debugging surface. It also ships a genuinely useful slice on its own.
- **Sync (Phase 5) before the two expensive chunks** proves the milestone's core value early. `enqueue_mutation` is ~15 lines. Putting the headline thesis *after* two HIGH-cost phases is how a milestone runs long and ships without its point.

**The two expensive pieces are the adapter engine and downloads** — exactly as PROJECT.md already predicted (*"Motor de adapters y descargas son los dos trozos caros; el resto cuelga de ellos"*). All four research files independently confirm it.

### Research Flags

Phases likely needing deeper research during planning (`/gsd-plan-phase --research-phase N`):
- **Phase 6 (Online sources):** **Yes.** Which 2–3 sources is unresolved, and per-site behaviour (Cloudflare posture, hotlink headers, HTML shape, ToS) is exactly the class of thing that must be checked against the live site, not inferred. The legal/architectural decision from Phase 2 also lands here.
- **Phase 2 (Adapter engine):** **Partially.** The *contract* is fully researched (Protocol shape, versioning, error taxonomy, the PyInstaller trap). What needs a decision pass, not a research pass, is bundled-vs-runtime-loadable — and that is a **human call**, not an agent one.
- **Phase 7 (Downloads):** **Light.** The mechanics are fully mapped (atomic rename, reconciliation, MAX_PATH, serial-per-source, the updater seam). The one open thing is exercising the updater seam against a queue that didn't exist when the updater last passed its gate.

Phases with standard patterns (skip research-phase):
- **Phases 1, 3, 4, 5, 8, 9.** Every one of these follows a precedent that already exists in the repo and is cited to a file and a line: `MutationWorker`, `normalizeAssetUrls`, `_backup_before_migration`, `media_mappings`, `matcher.py`, `playback_events` confirm/undo, the `/assets` mount, the backfill-polling pattern. There is nothing to go and learn — only precedent to follow. **Do not let a planner re-derive these; make them find the precedent.**

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | **HIGH** | Both external APIs (MangaDex, AnimeThemes) **queried live** on 2026-07-13 — response shapes, rate-limit headers, CORS behaviour, the `HEAD`→403 trap, the `externalUrl`/`pages:0` case. All package versions/licences checked against PyPI and npm registries. Installed deps read from `pyproject.toml` / `package.json`, not assumed. |
| Features | **HIGH** | Primary sources: Mihon's actual Kotlin source (`ChapterRecognition.kt`, `TrackChapter.kt`, `Track.kt` — the monotonic guard and the numbering algorithm read verbatim, not summarised), official Mihon/Kavita/Komga docs, and Nyanko's own schema. Issue reports (mihon#1793, #1575, #236, kavita#3531) are MEDIUM but corroborate the code. |
| Architecture | **HIGH** | Every claim cites a real `file:line` in this repo. The four "new" mechanisms all turn out to be clones of shipped ones. The two options that lost (Electron custom protocol, blob-URLs-over-IPC) lost on stated, checkable grounds. |
| Pitfalls | **HIGH** | Ten of twelve are latent in code that exists **today**, cited by line. The legal analysis rests on primary reporting (Kakao/Tachiyomi C&D, Sony/Aniyomi DMCA, Mihon's Nov 2025 notice) — and on this repo's own history of releases that already 404. MEDIUM only for per-source-site behaviour, which varies by design. |

**Overall confidence: HIGH.**

The research is unusually strong because this is a *subsequent* milestone on a codebase the researchers could read. The uncertainty that remains is not technical — it is **two decisions that only a human can make.**

### Gaps to Address

1. **Bundled vs runtime-loadable adapters — the one genuine conflict between research files, and a human decision.**
   STACK and ARCHITECTURE both recommend adapters **compiled into the sidecar** (explicit static imports; a manifest/sandbox/permission model is YAGNI while third-party loading is out of scope). PITFALLS #12 argues that compile-time-baked, first-party scrapers in a signed, auto-updating binary published by a named author is **the maximum-exposure legal configuration — strictly worse on every axis than the project that was killed for it** — and that runtime-loadable adapters are the mitigation that lets you comply with a takedown in an afternoon instead of a release cycle. Uncomfortably, it is *also* the better engineering (a dead source becomes replaceable without a release — Pitfall 5).
   **Note the distinction that makes this tractable:** "first-party sources shipped as *data* the app can update independently" is **not** the same as "third-party hot-loading" (repository + sandbox + permissions), which PROJECT.md rules out and which remains correctly out of scope. But it *does* open a code-execution surface, and pretending otherwise is how it becomes one by accident.
   **→ Resolve before Phase 2 closes.** The boundary cannot be retrofitted. Surface it to the human; do not let an executor pick.
2. **Which 2–3 online sources.** Not chosen by anyone. The criteria are both technical (JSON API vs scraped, Cloudflare posture, hotlink headers, stability) and legal (whose catalogue). MangaDex is the obvious, verified, no-auth, JSON-API first source — and it happens to need **no HTML parsing at all**, so `beautifulsoup4` can wait for source #2. **→ Decide in Phase 6 research.**
3. **Page delivery: two compatible designs, pick one and write it down.** STACK proposes streaming by index (`GET /pages/{n}` → bytes; no page URL exists anywhere, so the port trap is closed by *construction*). ARCHITECTURE proposes writing pages to `assets_dir` and returning **relative** `/assets/…` URLs through the existing mount. Both close the port trap correctly. **Recommendation: ARCHITECTURE's.** It collapses streaming + caching + downloading into **one** mechanism, reuses `normalizeAssetUrls` with zero changes, and makes "downloaded reads like local" fall out for free instead of needing a second code path in Phase 7. **→ Lock it in Phase 3; whichever is chosen, the invariant is identical: nothing containing a host or a port is ever persisted.**
4. **The `_stream/` read-cache growth policy.** ARCHITECTURE ponytails it as *nuke-on-startup + drop-on-chapter-close, add an LRU if users complain*. That is the right call — but the ceiling must be **stated in the phase**, or "unbounded page cache quietly eats the user's SSD" becomes a real bug (`CACHE_RESOURCE_LIMITS` is the precedent). **→ Phase 3.**
5. **CBR/RAR licence purity (`libarchive` "not derived from unRAR").** MEDIUM confidence — could not be confirmed from a primary source. **Moot while CBR is deferred**, which it should be. Revisit only if CBR is explicitly requested, as its own scoped item with the `THIRD-PARTY-NOTICES` budgeted.
6. **Whether 1–2 new native ops are actually needed.** STACK and ARCHITECTURE both say **zero** (`openFolderDialog` and `revealItemInDir` already exist). FEATURES assumes new ops for fullscreen and `powerSaveBlocker` — fullscreen is CSS, but keep-screen-awake is a genuine candidate. **→ Decide in Phase 3 UAT.** Either way, `native.test.ts`'s bidirectional self-check is the gate, and it is the thing that stopped the Phase-3 stubs from shipping in v0.2.

## Sources

### Primary (HIGH confidence)
- **This repository, read directly** — `apps/backend/nyanko_api/{main,database,providers,http,config,scanner,instance,matcher}.py`; `apps/desktop/src/{native,native.test,api}.ts`; `apps/desktop/electron/main/{index,ipc,sidecar,updater}.ts`; `pyproject.toml`; `package.json`. Every architectural and pitfall claim is cited to a `file:line`.
- **MangaDex API** — queried live 2026-07-13: `/manga`, `/manga/{id}/feed`, `/at-home/server/{id}`. No-auth reads; `externalUrl` + `pages:0` for licensed chapters; page CORS reflects `Origin: null`; `Cache-Control: immutable`; ~5 req/s with `Retry-After` on 429.
- **AnimeThemes API** — queried live 2026-07-13: no auth; `X-Ratelimit-Limit: 90`; `filter[site]` verified for AniList **and** MyAnimeList **and** Kitsu; `a.animethemes.moe/*.ogg` (OggS/Opus, ~3.7 MB, `Accept-Ranges: bytes`); **`HEAD` → 403, `GET` → 200/206**; **no `Access-Control-Allow-Origin`**.
- **Mihon source code** — `ChapterRecognition.kt`, `TrackChapter.kt`, `Track.kt`. The chapter-number algorithm and the monotonic guard, read verbatim.
- **Mihon / Kavita / Komga official docs** — reader settings, tracking ("Tracking is one-way"; "after reading the last page of a chapter"), downloads FAQ (no parallel downloads per source), local source (CBZ + ComicInfo.xml).
- **PyPI + npm registries** (2026-07-13) — versions and licences for `beautifulsoup4` 4.15.0 (MIT), `rarfile` 4.3 (ISC), `py7zr` 1.1.3, `libarchive-c` 5.3, `lxml`, `selectolax`, `httpx` 0.28.1; `react-zoom-pan-pinch`, `@tanstack/react-virtual`, `swiper`, `embla-carousel-react`, `react-window`.
- **AniList rate-limiting docs** — 90/min is normal; **30/min is a temporary degraded state**. (Confirms that hardcoding *either* number is wrong.)
- **Legal precedent** — Kakao C&D → Tachiyomi ceases development (Jan 2024; the concession was removing the preloaded extension list); Sony DMCA → ~200 Aniyomi extensions removed (Jun 2024); Mihon's "could be under threat" notice (Nov 2025).
- **`.planning/PROJECT.md` + `.planning/MILESTONES.md`** — the B-1 seam lesson, the 6-DB and port-in-URL scars, the deleted-releases-404 precedent.

### Secondary (MEDIUM confidence)
- Mihon issue reports (#1793 the monotonic-guard bug, #1575 decimal chapters, #236 per-page sync, #2920 parallel downloads) and Kavita #3531 (webtoon completion) — user-reported, but each corroborates the code.
- HakuNeko PR #4594 + Cloudflare community threads — confirm per-source `Referer` is standard practice, not paranoia.
- unRAR licence classification (Fedora/Debian: non-free; redistribution permitted with notice).

### Tertiary (LOW confidence — needs validation)
- The claim that libarchive's RAR reader is **not derived from unRAR** could not be confirmed from a primary source. Moot while CBR is deferred.
- Per-source-site behaviour (Cloudflare posture, selector stability, hotlink policy) for any source other than MangaDex — **unknown by design**, and the reason Phase 6 gets a research pass.

---
*Research completed: 2026-07-13*
*Ready for roadmap: yes*
