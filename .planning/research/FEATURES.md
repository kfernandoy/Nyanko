# Feature Research

**Domain:** Manga reader + source engine + offline downloads + reading-progress sync, inside an existing multi-provider anime/manga tracker (Nyanko v0.3)
**Researched:** 2026-07-13
**Confidence:** HIGH (primary sources: Mihon source code + official docs, live AnimeThemes API, Nyanko's own schema; MEDIUM only where noted)

## TL;DR for the roadmapper

Three things dominate everything below:

1. **The source↔tracker mapping is already 80% built in Nyanko and nobody noticed.** `media_mappings(provider, site_identifier, media_id, episode_offset)` is *exactly* the table this problem needs — it was built for the browser extension (MALSync-style) and it already carries the `episode_offset` column that solves "the source's numbering disagrees with the tracker's". Chapter mapping is a mirror of it, not an invention. See [The Crux](#the-crux-sourcetracker-entry-mapping).
2. **AnimeThemes is orthogonal to the entire reader spine and nearly free.** Verified live: you can query it by AniList *or* MAL id directly (`filter[has]=resources&filter[site]=AniList&filter[external_id]=101922`), so there is **zero fuzzy matching**. Nyanko already stores that id on every library item. It also serves audio-only `.ogg` files, so the player is a native `<audio>` tag. This can ship first, last, or in parallel — it blocks nothing and nothing blocks it.
3. **"Downloaded chapters read like local ones" is an architectural lever, not a feature.** If the downloader emits the *same on-disk format the local reader already consumes* (CBZ + `ComicInfo.xml`, which is what Mihon does), then the reader has exactly one local code path and downloads get offline reading for free. If it emits anything else, you build the reader twice. Decide this before writing either.

---

## Feature Landscape

### Table Stakes (Users Expect These)

Missing any of these and the reader is not credible. Sorted by feature area.

#### Reader — core

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Paged **right→left** (default for manga) | Mihon's default reading mode. A manga reader that opens L→R is broken on arrival. | LOW | Direction is a CSS/index-order flip, not a second renderer. |
| Paged **left→right** | Manhua, western comics, and user preference. | LOW | Same renderer as above. |
| **Continuous vertical / long strip (webtoon)** | Manhwa/webtoons are half of what people read. Mihon ships "Long strip" and "Long strip with gaps"; Kavita ships "Infinite Scroll/Webtoon". Non-negotiable. | **MEDIUM** | Undersold if you call it easy: a long strip is tens of thousands of px tall with images of unknown height. Needs virtualization/windowing or it eats memory and janks. Pages must reserve height *before* load or the scroll position jumps under the user. |
| **Reading mode remembered per series** | A library holds both manga (RTL) and webtoons (vertical). A single global mode forces the user to re-set it on every open. Mihon has a per-series viewer override. | LOW | One column on the manga row. Do it from day one — retrofitting it after users have a library means guessing defaults. |
| Fit modes: fit-width / fit-height / fit-screen / original | Table stakes across Mihon (Scale type), Kavita (Height/Width/Original), YACReader. | LOW | Pure CSS `object-fit` + max-width/height. |
| **Zoom + pan** | Scan quality varies; small text is unreadable at fit-screen. | MEDIUM | Ctrl+wheel zoom, double-click zoom-to-point, drag-to-pan. The fiddly part is keeping the zoom anchored under the cursor. |
| **Keyboard navigation** (←/→, PgUp/PgDn, Space, Home/End) | This is a **desktop** app. Mihon lacks it (it's a phone app, it uses volume keys); Kavita/Komga/YACReader all have it. On desktop it is table stakes *even though the reference app doesn't have it*. | LOW | Don't copy Mihon here. Copy YACReader. |
| Mouse-wheel navigation | Desktop baseline. Wheel = next/prev page in paged mode, scroll in webtoon mode. | LOW | Mode-dependent binding. |
| Click zones (left half / right half) | Mihon's tap zones, translated to mouse. Users click, not just key. | LOW | Respects reading direction (RTL inverts them). |
| **Fullscreen** (F11 / F, Esc to exit) | Universal. | LOW | Electron `setFullScreen`. Must route through `native.ts`. |
| Page counter + jump-to-page | "Where am I / take me to page 40." Kavita binds `G`. | LOW | |
| **Resume mid-chapter** (remember last page read) | Users close the app mid-chapter constantly. Kavita stores the page number per chapter; Mihon stores `lastPageRead`. | LOW | One `last_page_read` column on the chapter row. Cheap and enormously felt. |
| **Next-chapter chaining + transition screen** | At the end of ch.12, the reader shows "Next: Ch. 13" and continues on one more input. Mihon calls these "chapter transitions". Without it the reader is a file viewer. | MEDIUM | Also needs the *previous*-chapter transition, and an end-of-series state. This is where "chapter finished" fires — it is the trigger point for progress sync. |
| **Page prefetch / preload (N ahead)** | For online sources this is the difference between "a reader" and "a slideshow of loading spinners". | MEDIUM | Prefetch depth ~3–5. Must respect the per-source rate limit — this is exactly the burst that wakes up debt **D-I-03**. |
| Background color (black / gray / white) | Reading at night on a white background is hostile. Every reader has it. | LOW | |
| Keep screen awake while reading | Expected; trivially available. | LOW | Electron `powerSaveBlocker`, one call through `native.ts`. |

#### Reader — local files

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| **CBZ / ZIP** | The dominant format. | LOW | Python `zipfile` is stdlib. Free. |
| **Folder of images** | Mihon's local source supports it and calls it the *fastest* option. | LOW | Natural-sort the filenames (`2.jpg` before `10.jpg` — a naive sort gets this wrong and it is the #1 local-reader bug). |
| Image formats: JPG/PNG/WebP | Baseline. | LOW | AVIF/JXL: skip. |
| `ComicInfo.xml` metadata read | The de-facto comic metadata standard; Mihon, Kavita, and Komga all consume it. Gives Series/Number/Title/Volume/Writer for free instead of parsing filenames. | LOW | Stdlib XML. Read it if present, fall back to filename parsing. |
| **CBR / RAR** | Users have CBR files. But see the honest note. | **MEDIUM–HIGH** | *Do not undersell this.* Python `rarfile` needs an **external unrar/bsdtar binary bundled into the PyInstaller onedir**. The unrar license permits decompression-only use free of charge, so it is legally usable, but it's a native binary you now ship, sign, and update. Alternative: do it renderer-side with `node-unrar-js` (WASM, self-contained, no external binary). **Recommendation: ship CBZ/ZIP/folder in the first reader cut (stdlib, zero cost) and treat CBR as its own scoped item.** It is the single easiest thing to defer without hurting credibility. |

#### Browse / chapter list (the path from "I want to read X" to "pages on screen")

The flow, confirmed against Mihon's source API contract:

```
Sources list → pick a source → Popular | Latest | Search (+ filters)
   → manga page (cover, title, author, status, description, genres, [Add to library] [Link tracker])
      → chapter list
         → read
```

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Per-source **Popular** / **Latest** / **Search** | This is the Mihon source contract: `fetchPopularManga(page)`, `fetchLatestUpdates(page)`, `fetchSearchManga(page, query, filters)`. All paginated with a `hasNextPage` flag. | MEDIUM | Infinite-scroll pagination on the grid. |
| Manga detail page from a source | `fetchMangaDetails` → title, author, artist, description, genre, status, thumbnail. | LOW | Reuse the existing detail-card layout. |
| **Chapter list** with: name, **chapter number**, **scanlator**, **language**, **upload date** | These are exactly the fields on Mihon's `SChapter` (`name`, `chapter_number`, `scanlator`, `date_upload`, `url`) and they exist because users need them. Scanlator especially: the same chapter exists 3× from 3 groups and they are *not* interchangeable. | MEDIUM | `date_upload` is epoch **ms**, `0` = unknown → show "Unknown", don't show 1970. |
| **Read / unread state** per chapter (+ partial "page 8/20") | Core. | LOW | |
| **Download state** per chapter (not downloaded / queued / downloading / downloaded / error) | The chapter list is where users manage downloads. Two states (yes/no) is not enough — a half-downloaded chapter must not look readable. | MEDIUM | Five states, not two. See Downloads. |
| Sort asc/desc + filter (unread only / downloaded only / by scanlator) | Table stakes; a 400-chapter list is unusable without it. | LOW | |
| **"Mark previous as read"** | The single highest-value quality-of-life action in the whole chapter list. Users arrive at a source having already read 120 chapters elsewhere. | LOW | Bulk update. Interacts with progress sync — see the monotonic guard. |
| Unread count badge | Baseline. | LOW | |

#### Downloads

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| **Download queue** with per-chapter progress | The feature *is* the queue. | **HIGH** | See the honest complexity note below. |
| Pause / resume / cancel / clear, reorder | Mihon: More → Download queue, drag the `=` handle to reorder, cancel individually or all. | MEDIUM | |
| Batch enqueue: "download next 1 / 5 / 10 / 25 / unread / all" | Nobody clicks 200 chapters one at a time. | LOW | Trivial once the queue exists. |
| **Serial per source, parallel across sources** | This is a **hard constraint, not a tuning knob**: Mihon explicitly forbids parallel downloads from a single source to avoid IP bans, while allowing up to 5 sources concurrently. | MEDIUM | Bake it into the queue's scheduler from the start. Retrofitting a per-source serial lock into a naive parallel worker pool is a rewrite. |
| Downloaded chapters readable offline through the **same reader** | The stated requirement. | LOW **if** the on-disk format matches the local reader's; HIGH if not. | The lever from the TL;DR. Emit CBZ + `ComicInfo.xml`. |
| Downloaded state visible in the chapter list | See above. | LOW | |
| Configurable download location + disk usage display | Users put manga on a second drive. | LOW | Through `native.ts` dialog op (already exists). |
| Delete downloads (per chapter / per manga / all) | Storage management. | LOW | |
| Retry on failure; resume when back online | Networks fail mid-200-chapter batch. Mihon does this. | MEDIUM | |

**Honest complexity note on the download queue — this is a HIGH, not a MEDIUM:**

- **Signed/expiring image URLs.** Many sources sign page URLs with a short TTL. If you resolve `fetchPageList` at *enqueue* time, a chapter that sits in the queue for 20 minutes downloads 404s. **Page lists must be resolved at download time, not at queue time.** This one detail invalidates the obvious design.
- **Per-source headers/referer.** Image CDNs often reject requests without the right `Referer`/`User-Agent`. The downloader must go through the *source adapter*, not a generic HTTP fetch.
- **Partial-download states are corrupting.** A chapter that is 60% downloaded must never be readable. Mihon's answer: download into a `_tmp_` folder, atomic-rename on completion. Copy it.
- **Windows `MAX_PATH` (260 chars).** `downloads/<Source Name>/<Very Long Light Novel Style Manga Title>/<Chapter Name> (abcdef).cbz` blows past 260 characters routinely. This is a **Windows-specific, guaranteed** bug (Nyanko is Windows-primary). Plan for long-path handling or hashed directory names now.
- **Filename sanitization.** Mihon replaces `"*:<>?\|/` with `_`, and appends a **hex hash suffix** to chapter folders precisely because two chapters can share a name.
- **Crash recovery.** The queue must survive an app kill mid-download. It's a persisted queue, not an in-memory one.

#### Progress sync

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| **Chapter counts as read on reaching the last page** | Mihon's rule, verbatim: progress updates occur *"after reading the last page of a chapter, or marking a chapter as read"*. This is the industry answer. | LOW | **Do not invent a % threshold.** See anti-features. |
| Explicit **mark read / mark unread** | The manual escape hatch. Komga, Kavita, Mihon all have it. | LOW | |
| Progress pushes automatically to AniList/MAL/Kitsu | The stated core value of the milestone. | MEDIUM | **Reuses Nyanko's existing `ProgressUpdate` + `/api/library/progress` + `MutationWorker` wholesale.** Do not build a second sync path. |
| **Monotonic guard: never lower remote progress** | Mihon's `TrackChapter` skips the tracker entirely when `chapterNumber <= track.lastChapterRead`. Mihon issue **#1793** is the bug report from *not* checking hard enough. Without this, re-reading ch.1 of a 200-chapter manga silently destroys the user's tracker progress. | MEDIUM | This is a correctness/data-loss guard, not a nicety. It must compare against the **tracker's** value, not just the local one. |
| Offline queue + retry | Mihon: *"offline progress syncs when back online"* — failures go to a `DelayedTrackingStore` with a background retry job. | LOW | **Nyanko's `MutationWorker` already is this.** Free. |
| Status auto-transition (first chapter → CURRENT; last chapter → COMPLETED + finish date) | Mihon adjusts *"status, start & finish date"* on start/complete. | LOW | `CanonicalStatus` already models CURRENT/COMPLETED/REPEATING. Free. |
| One-way sync only (Nyanko → tracker) | Mihon is explicit: *"Tracking is one-way: Mihon → Tracker."* | — | This is a *decision*, and it is the right one. See anti-features. |

#### AnimeThemes on detail cards

Verified live against `api.animethemes.moe` on 2026-07-13.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| List OPs/EDs on the detail card: slug (`OP1`/`ED2`), type (OP/ED/IN), song title, artist(s), episode range | This is literally the API payload shape. Anything less is throwing data away. | LOW | `include=animethemes.animethemeentries.videos.audio,animethemes.song.artists` |
| Lookup by AniList / MAL id (no title matching) | **Verified: both work.** `filter[has]=resources&filter[site]=AniList&filter[external_id]=101922` → Kimetsu no Yaiba. `site=MyAnimeList&external_id=38000` → same. | LOW | Nyanko already stores `external_id` per provider in `external_identities`. **This feature does zero matching.** |
| **Play button → audio** | | LOW | AnimeThemes serves audio-only `.ogg` at `a.animethemes.moe`. A native `<audio>` element plays it. **Zero dependencies.** |
| **Respect the `spoiler` flag** | The API gives you `spoiler: true` per entry. Rendering "Episodes 23-26" for a late-series OP without honoring it is a spoiler bug you were handed the fix for. | LOW | Blur/collapse the episode range (and any late-version entry) behind a click. |
| Respect the `nsfw` flag | Same argument, same field. | LOW | |
| Cache the response | | LOW | Existing `cache` / `media_details_cache` tables. |

**Rate limit:** AnimeThemes returns `X-Ratelimit-Limit: 90` — which happens to match `RateLimitedClient(requests_per_minute=90)`, Nyanko's existing default. Reuse it as-is. (Note this is *not* true of AniList, which reports `X-RateLimit-Limit: 30` — that's debt item **D-I-03**, and the reader is what wakes it up.)

---

### Differentiators (Competitive Advantage)

These make Nyanko's reader better than a generic one. Most of them are cheap *because* Nyanko already has the surrounding app — that's the whole point.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **The library is already the tracker entry** | Mihon has to reconcile three identities: source manga → local manga row → tracker entry. **Nyanko's library entry *is* the tracker entry.** So linking a source manga to a tracker is a single join, not a chain. This is a structural advantage over the reference app and it should be visible in the UX: you don't "add a tracker to a manga", you "point a source at a manga you already track". | — | Architectural, not a feature to build. But it should drive the UI. |
| **Auto-suggested tracker link via the existing matcher** | Mihon's linking is 100% manual: search the tracker, pick the entry. Nyanko already has `matcher.py` (`find_best_search_match`, `rank_matches`) doing MALSync-style scoring across romaji/english/native/synonyms — **and it's duck-typed**, so it works on a source's manga object with no changes. Nyanko can *propose* the link with a confidence score and let the user confirm. | MEDIUM | Propose, never silently link. Reuse `match_corrections` as the override table. |
| **Unified reader for local + downloaded + online** | Most tools do one. Mihon does online+downloaded well and local as a second-class "Local source". A single reader over all three is the differentiator, and it's *cheaper* than three readers if the format lever is pulled. | MEDIUM | Requires the CBZ+ComicInfo download output decision. |
| **Reading activity in the existing timeline** | "You read Ch. 47 of Chainsaw Man" alongside anime episodes and remote activity. The activity timeline already ingests local edits. | LOW | Reuse. |
| **Chapter-finished confirm/undo** | The anime side already has playback detection with confirm/undo. Applying the *same* interaction to "chapter finished → progress 47 → [Undo]" makes the reader feel like part of Nyanko rather than a bolted-on app. | LOW | Reuse the `playback_events`/confirm-undo pattern. |
| **Torrent feed ↔ manga** (already-matched library) | The existing torrent feed matches against the library. Manga entries are in that library. | LOW | Probably free; verify. |
| Double-page spread with manual offset toggle | On a 16:9 monitor, one portrait page wastes half the screen. Kavita ships Single / Double / Double (Manga). Mihon marks split/rotate wide pages as *"TBA"* — i.e. the mobile reference app **doesn't have this**, so it's a genuine desktop differentiator rather than a copy. | MEDIUM | The offset toggle matters: covers throw the pairing off by one and every reader that lacks the toggle gets complaints. |
| Auto-detect + split wide pages | A 2-page spread scanned as one wide image, split into two. Kavita has it; Mihon doesn't. | MEDIUM | Nice, not necessary. |
| Mini-player that survives navigation | Once there's a play button on the card, a player that dies when you close the modal is *annoying*, not neutral. Keeping OP playback alive while you browse the library is the thing that turns AnimeThemes from a curiosity into a feature. | MEDIUM | Requires the `<audio>` element to live at App level (above the router), not inside the card. This is the only structural cost of the whole music feature. |
| Crop borders / color filter / grayscale | Cheap polish; Mihon has all three. | LOW | Filler for a phase with slack. |

---

### Anti-Features (Commonly Requested, Often Problematic)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| **"Chapter counts as read at X%"** (e.g. 80%) | Sounds forgiving — "I basically finished it". | Ambiguous and generates **false positives**, which in a sync feature means corrupting the user's tracker. Long-strip chapters make "%" meaningless (one tall image = 1 page). Kavita has open bugs (#3531) about chapters *not* marking complete in webtoon mode for exactly this class of reason. | **Last page reached.** Mihon's rule, unambiguous. Plus an explicit manual "mark as read". |
| **Two-way sync (tracker → local read state)** | "My AniList says 47, why does Nyanko say 12?" | Mihon is explicitly one-way and that is a *considered* decision. Two-way means conflict resolution on every chapter of every manga: which side wins, what about chapters the source doesn't have, what about decimals the tracker can't represent. Nyanko already has a `conflicts` table for library entries — do **not** extend that machinery down to chapter granularity. | One-way (Nyanko → tracker). Optionally, a **one-shot, user-triggered** "mark chapters ≤ tracker progress as read" import when linking. That gets 95% of the value at 5% of the cost. |
| **Per-page progress sync to the tracker** | "Sync exactly where I am." | The trackers physically cannot store it. AniList's mutation is `$progress: Int!`. MAL's field is `num_chapters_read` (int). Kitsu likewise. Nyanko's own `ProgressUpdate.progress` is `int = Field(ge=0)`. Mihon issue **#236** requests this and it remains open because there is nowhere to put it. | Store page position **locally** (which is table stakes anyway, for resume). Send integers to the wire. |
| **Third-party hot-loadable adapters** | "Like Mihon extensions." | Already declared out of scope in PROJECT.md, and correctly: a repository + sandbox + permission model is a security surface that deserves its own milestone. Mihon's extensions are Kotlin APKs — there is no compatibility shortcut regardless. | Versioned adapter API + 2–3 first-party sources (the stated plan). Design the API as if third parties were coming; don't ship the loader. |
| **EPUB / PDF reading** | "Kavita does it." | Completely different renderer, different pagination model, different metadata. It is a large chunk of Kavita's codebase. Nyanko is a manga tracker growing a manga reader, not a general ebook reader. | Skip. If light novels ever matter, that's a separate milestone. |
| **Playing the OP *video* (WebM) in the card** | "Show the animation!" | The Kimetsu OP1 NCBD1080 WebM is **51 MB**. A 720p one is 29 MB. Streaming that to autoplay a card preview is an absurd bandwidth cost for a feature whose value is the *song*. The `.ogg` audio is a small fraction of it. | Audio-only playback + a "Watch on AnimeThemes" link that opens the browser (the `opener` native op already exists). |
| **Theme playlists / downloading themes / a music library** | Natural next thought once music plays. | Different product. Scope creep with no relation to the milestone's core value. | List + play + link out. Stop there. |
| **Volume-key nav, notch/cutout handling, rotation lock** | They're in Mihon's settings, so they look like table stakes. | They are **mobile-only** artifacts. Copying Mihon's settings screen wholesale onto a desktop app is cargo-culting. | Keyboard + mouse + fullscreen. Copy YACReader/Kavita for the desktop surface, not Mihon. |
| **Parallel downloads within one source** ("it'd be faster") | Obvious throughput win. Mihon issue #2920 asks for it. | It is the fastest way to get every user's IP banned from the source. Mihon refuses it deliberately. | Serial per source, parallel **across** sources (up to ~5). |
| **AI upscaling / denoising pages** | "Scans look bad." | Gold plating, heavy, and it makes every page load slow to fix a problem the user didn't ask you to fix. | Zoom, and let the user pick a better scanlation group (which is why the chapter list needs the scanlator field). |

---

## The Crux: source↔tracker entry mapping

Treating this as the first-class design problem it is. **This is the single highest-risk item in the milestone**, and it is also the one where Nyanko has the biggest unfair advantage.

### How Mihon does it (primary source: `Track.kt`, `TrackChapter.kt`)

Mihon's identity chain has three links:

```
(sourceId, mangaUrl)  →  local manga row (mangaId)  →  Track(trackerId, remoteId)  →  AniList/MAL entry
```

The `Track` model, verbatim from the source:

| Field | Type | Role |
|-------|------|------|
| `mangaId` | Long | the **local** manga |
| `trackerId` | Long | which service (AniList / MAL / Kitsu / …) |
| `remoteId` | Long | the **remote** entry id |
| `lastChapterRead` | **Double** | progress — note it is a **float locally** |
| `totalChapters` | Long | |
| `status` | Long | |

And the binding is **manual**: the user opens the series → Tracking → search the tracker → pick the entry. Mihon's docs are blunt about it: *"search with a different title if there is no match."* The only automatic linking is for "enhanced" services (Komga, Kavita, Suwayomi) — and those are automatic **only because the source and the tracker are the same server**, which already knows the id. That exception proves the rule: automatic linking requires a shared identifier.

The push logic, from `TrackChapter`:
- Fires after a chapter is read.
- **Guard:** if `chapterNumber <= track.lastChapterRead`, **skip the tracker entirely.** No update attempted.
- Update is `track.copy(lastChapterRead = chapterNumber)` → service update.
- On failure: push to a delayed-tracking store, schedule a retry job.

### How Nyanko's chain is different — and shorter

Nyanko's library entry **is** the tracker entry (`media` + `external_identities(media_id, provider_id, external_id)` + `library_entries`). There is no separate "local manga" identity to reconcile. So the chain collapses to one hop:

```
(source_id, source_manga_key)  →  media_id   [+ chapter_offset]
```

**And that table already exists.** Shipped, in production, in `database.py`:

```sql
CREATE TABLE IF NOT EXISTS media_mappings (
    provider TEXT NOT NULL,
    site_identifier TEXT NOT NULL,
    media_id INTEGER NOT NULL,
    episode_offset INTEGER NOT NULL DEFAULT 0,   -- <<<< THE NUMBERING-DISAGREEMENT SOLUTION
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(provider, site_identifier)
);
```

It was built for the browser extension (map a page on some streaming site → a tracker entry, with an offset because the site numbers episodes continuously and the tracker splits by season). **That is the identical problem, one media type over.** The manga mapping is a mirror of this table (or the same table with a `chapter_offset`), not a new design.

Supporting pieces that also already exist:
- `match_corrections(raw_pattern → media_id)` — the precedent for "the user overrides a bad auto-match".
- `external_identities(..., confidence REAL)` — mappings already carry a confidence score.
- `episodes.episode_number` is already **`REAL`**, not INTEGER — decimal numbering is already accepted in this schema.

### The sub-problems, each of which needs an explicit decision

1. **Identity of a source manga.** Use `(source_id, manga_url)`. Mihon is explicit: *"A `SManga` entry is identified by its `url`"*, and during backup only `url` and `title` are stored. **The `source_id` must be stable across source renames** — Mihon computes it from `name + lang + versionId` and warns you to pin it explicitly when renaming, or users' libraries break. Nyanko's adapter engine must have a stable, explicit source id from v1. Getting this wrong is unrecoverable for users later.

2. **Auto-link vs manual.** Reuse `matcher.py` to *propose* with a score; require user confirmation below a threshold. **Never silently link** — a wrong link means writing another manga's progress onto the user's tracker.

3. **Parsing a chapter number out of a chapter name.** Source chapter names are freeform garbage (`"Ch.12.5 - Extra"`, `"Vol.3 Chapter 12 (v2)"`). This is its own component. Mihon's `ChapterRecognition` algorithm, which is worth copying nearly verbatim:
   - Lowercase; **strip the manga title out of the chapter name**; replace `,`/`-` with `.`; strip whitespace before extra/special/omake.
   - Strip "unwanted tags" (vol/version/season) before matching.
   - Try `(?<=ch\.) *NUMBER` first; then any `([0-9]+)(\.[0-9]+)?(\.?[a-z]+)?`; then first number found; else **`-1.0`** (unknown).
   - Suffix handling: numeric decimals kept as-is; **`extra` = .99, `omake` = .98, `special` = .97**; a trailing letter maps to tenths (`a`→.1 … `z`→.9). So `"12a"` → `12.1`.
   - Complexity: **MEDIUM** — it looks like "a regex" but it's a pile of edge cases. It is, however, bounded, pure, and *trivially unit-testable*. Write the table of cases first.

4. **Numbering disagreement between source and tracker.** The source counts 1..200 continuously; the tracker splits the work into parts/seasons; or the source includes a prologue the tracker doesn't. → **signed `chapter_offset`**, exactly as `episode_offset` already does. Surface it in the link UI ("Source ch. 1 = Tracker ch. ___").

5. **Decimal chapters (12.5).** Store **REAL locally, `floor()` on the wire.** Every tracker takes an int (`$progress: Int!` / `num_chapters_read`), and Nyanko's own `ProgressUpdate.progress` is `int = Field(ge=0)`. So ch. 12.5 → progress `12`. That is *correct* (12.5 is a split of 12, not a 13th chapter), but users report it as a bug — Mihon issue **#1575** is exactly this. **Make it visible in the UI**, don't just floor it silently.

6. **Monotonic guard.** Never lower remote progress. Copy Mihon's `chapterNumber <= lastChapterRead → skip`, but compare against the **tracker's** current value (Mihon issue **#1793** is the bug from not doing that). This is the guard that protects against data loss — do not simplify it away.

7. **Re-reads.** After COMPLETED, reading ch.1 must not push `1`. Detect `status == COMPLETED && chapter < progress` → offer **"Start a re-read"** → set `REPEATING`. Nyanko already models `CanonicalStatus.REPEATING`, and `myanimelist.py` already sends `num_times_reread`. Mostly free; the *detection* is the work.

8. **Out-of-order reading.** Push **max(chapters read)**, not "the last chapter I opened". Falls out of the monotonic guard.

9. **Reading a source manga that isn't in the library yet.** Offer "add to library" inline. The Discovery↔library integration already does this for search results — reuse the pattern.

**Complexity of the mapping feature as a whole: HIGH.** Not because any one piece is hard, but because there are nine of them and each one is a silent-data-corruption bug if you get it wrong. It deserves its own phase and its own test table.

---

## Dependencies on EXISTING Nyanko features

**Reuse beats rebuilding.** This is the map.

| Existing piece | Reused by | Verdict |
|---|---|---|
| `media_mappings(provider, site_identifier, media_id, **episode_offset**)` | Source↔tracker mapping | **Direct reuse / mirror.** The offset column already solves the numbering-disagreement problem. |
| `matcher.py` — `find_best_search_match`, `rank_matches`, `_titles` | Auto-suggesting the tracker link | **Direct reuse.** MALSync-style scoring, already duck-typed, already handles romaji/english/native/synonyms + sequel-marker penalties. |
| `match_corrections` | User override of a wrong auto-link | Direct reuse (pattern, if not the table). |
| `external_identities(media_id, provider_id, external_id, confidence)` | Resolving library item → AniList/MAL id | **Direct reuse.** This is also what makes AnimeThemes free. |
| `ProgressUpdate` + `POST /api/library/progress` + `MutationWorker` | Chapter progress sync | **Direct reuse — do not build a second sync path.** Already has: queueing, retry with backoff, `Retry-After` handling, offline resilience. Only change needed: floor decimals + the monotonic guard. |
| `providers.py`: `capabilities.manga`, `library_manga`, `manga_details`, `search_manga`, `edit_entry`, `update_progress` | Everything on the tracker side | **Already first-class for manga.** Nothing to add. |
| `provider_mappings.py`: `CanonicalStatus` (incl. `REPEATING`), `CanonicalFormat.MANGA` | Status transitions, re-reads | Direct reuse. |
| `http.py`: `RateLimitedClient`, `retry_with_backoff` (`Retry-After`-aware) | Source adapters, download worker, AnimeThemes client | **Direct reuse — but this is where debt D-I-03 bites.** See below. |
| `scanner.py` (`iter_video_files`, `parse_file`, `_title_from_folders`) | Local manga scan | **Pattern reuse, NOT code reuse.** `VIDEO_EXTENSIONS` ≠ archive extensions; an episode number in a filename ≠ a chapter in a folder/archive name. This is a *new* scanner written in the same shape. Do not let anyone plan this as "extend the scanner". |
| `local_files(path, media_id, **episode INTEGER**, parsed_title, matched)` | Local manga chapters | Same shape (1 file → 1 numbered unit → 1 media). But `episode` is **INTEGER** and chapters need **REAL**. Either a sibling table or a widened column + a type discriminator. |
| `library_folders(path, recursive)` | Configuring manga folders | Reuse, but needs a content-type discriminator (a manga folder is not an anime folder). |
| `episodes.episode_number REAL` | The chapters table | Precedent — decimal numbering is already blessed in this schema. |
| Detail card / modal | AnimeThemes list + player; entry point to the chapter list | Host component. |
| Activity timeline (local edits already land here) | "Read Ch. 47" events | Direct reuse. |
| `playback_events` + confirm/undo UX | "Chapter finished → progress → [Undo]" | **Pattern reuse.** This is what makes the reader feel like Nyanko. |
| Discovery ↔ library (filter out in-library items, add from search) | Source browse; "add to library" from a source manga page | Pattern reuse. |
| `native.ts` (single native boundary, 18 ops) | All file I/O: local scan, archive reads, download writes, fullscreen, powerSaveBlocker, folder picker | **Everything crosses it.** New ops needed. This boundary is load-bearing — respect it. |
| `cache` / `media_details_cache` | AnimeThemes responses, source chapter lists | Direct reuse. |
| Torrent feed matching against library | Manga entries are already in the library | Probably free. Verify. |

### The debt that the reader activates

PROJECT.md already flags **D-I-03**: `RateLimitedClient(requests_per_minute=90)` vs AniList's actual `X-RateLimit-Limit: 30`, and correctly notes it's *"latente porque el backfill es secuencial; un reader que hace ráfagas lo despierta."* That is exactly right and it is now load-bearing:

- **Page prefetch** bursts against the source.
- **The download queue** bursts hard against the source.
- **Batch "mark previous as read"** bursts against the *tracker* — this is the one that hits AniList's real 30/min ceiling.

**D-I-03 must be fixed before or with progress sync, not after.** It is not a cleanup item; it is a prerequisite. (For reference: AnimeThemes reports `X-Ratelimit-Limit: 90`, so the existing default is fine *there* — the problem is specifically AniList.)

---

## Feature Dependencies (new features)

```
[I. AnimeThemes on cards]  ── depends on nothing in this milestone ──> SHIPS INDEPENDENTLY
      └──requires──> existing: detail card + external_identities + RateLimitedClient

[A. Reader core]  (local files: CBZ/ZIP/folder → pages → modes/zoom/keys/resume/chaining)
      └──requires──> existing: native.ts (fs ops)

[B. Local manga library]  (manga scanner + chapters table + associate to library entry)
      └──requires──> [A]  (a scanner with nothing to open is pointless)
      └──requires──> existing: matcher.py, match_corrections, library_folders

[C. Source adapter engine + 2-3 sources]
      └──requires──> existing: http.py (RateLimitedClient)
      └──MUST define──> stable source_id  (unrecoverable if wrong)

[D. Browse + chapter list UI]
      └──requires──> [C]
      └──enhanced by──> existing: Discovery↔library patterns

[E. Online reading]
      └──requires──> [A] + [C] + [D]
      └──requires──> page prefetch + per-source image headers

[F. Source↔tracker mapping]        <<<< THE RISK
      └──requires──> [C]  (needs a source manga identity to map)
      └──requires──> ChapterRecognition (own component, testable in isolation)
      └──requires──> existing: media_mappings, matcher.py

[G. Progress sync on chapter finish]
      └──requires──> [F]   (no mapping ⇒ nothing to sync to)
      └──requires──> [A]   (the "chapter finished" event is born in the reader)
      └──requires──> existing: ProgressUpdate + MutationWorker
      └──BLOCKED BY──> debt D-I-03 (AniList 30/min)

[H. Downloads]
      └──requires──> [C]  (pageList, at DOWNLOAD time — not enqueue time)
      └──requires──> [A]  (something must read the output)
      └──requires──> [B]'s on-disk format decision  (emit CBZ + ComicInfo.xml)
      └──conflicts with──> naive parallel workers (per-source serial is mandatory)
```

### Dependency Notes

- **[G] requires [F], hard.** There is no "sync progress" without "which tracker entry". Any roadmap that puts progress sync before mapping is planning a fake phase.
- **[H] requires [B]'s format decision, not [B] itself.** The downloader and the local reader must agree on the on-disk format. Make that decision in [A]/[B] and [H] gets offline reading for free. Defer it and you write the reader twice. **This is the cheapest architectural win available in the milestone.**
- **[E] requires [D], not the reverse.** You can browse without reading online (it degrades to "add to library"), but you can't read online without having navigated to a chapter.
- **[I] requires nothing.** It shares no code with the reader spine. Use it as a warm-up phase, a parallel track, or a palate cleanser between the two expensive chunks ([C] and [H]).
- **[C] and [H] are the two expensive pieces**, exactly as PROJECT.md already says: *"Motor de adapters y descargas son los dos trozos caros; el resto cuelga de ellos."* Research confirms it.
- **ChapterRecognition is a hidden component.** It is not part of [C] and not part of [G] — it sits between them and it deserves to be named, or it will get smeared across both and tested in neither.

---

## MVP Definition

### Launch With (the reader is not credible without these)

- [ ] **Reader core** — paged RTL + paged LTR + continuous vertical; fit modes; zoom/pan; keyboard + wheel + click-zone nav; fullscreen; page counter; **resume mid-chapter**; **next/prev chapter chaining**; per-series mode memory
- [ ] **Local files** — CBZ / ZIP / folder-of-images (natural sort!); ComicInfo.xml if present
- [ ] **Local manga library** — scan, parse, associate to an existing library entry
- [ ] **Source adapter engine** — versioned API, **stable source ids**, per-source rate limiting/headers; 2–3 first-party sources
- [ ] **Browse + chapter list** — popular/latest/search; chapter list with number, scanlator, language, upload date, read state, download state; sort/filter; **mark previous as read**
- [ ] **Online reading** — with page prefetch
- [ ] **Source↔tracker mapping** — auto-suggested via `matcher.py`, user-confirmed, with `chapter_offset`
- [ ] **Progress sync** — last-page-reached → floor → **monotonic guard** → existing `ProgressUpdate`/`MutationWorker`; status transitions; confirm/undo
- [ ] **Download queue** — per-chapter + batch; pause/resume/cancel; **serial per source**; emits CBZ+ComicInfo; downloaded state in the chapter list; offline reading through the same reader
- [ ] **AnimeThemes on cards** — list + audio play + spoiler/nsfw flags respected
- [ ] **Debt: D-I-03** — AniList rate limit (prerequisite for progress sync, not a cleanup)

### Add After Validation (v0.3.x)

- [ ] **CBR / RAR** — deliberately deferred: needs a bundled unrar binary (PyInstaller) or a WASM lib. Add when users ask, which they will, but it doesn't block credibility.
- [ ] Double-page spread + manual offset — high desktop value, but the reader is credible in single-page
- [ ] Auto-split wide pages
- [ ] Mini-player surviving navigation — add as soon as anyone complains that closing the card kills the song (they will)
- [ ] "Download ahead" / auto-download while reading
- [ ] Delete-after-read with category exclusions
- [ ] Crop borders, color filter, grayscale
- [ ] One-shot "import read chapters from tracker progress" on link

### Future Consideration (v0.4+)

- [ ] Third-party hot-loaded adapters (repository + sandbox + permissions) — already out of scope, correctly
- [ ] More first-party sources
- [ ] Volume-level progress (`progressVolumes` / `num_volumes_read` both exist on the providers)
- [ ] Bookmarks within a chapter

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Reader core (paged + webtoon + nav + resume + chaining) | HIGH | MEDIUM | **P1** |
| Local files: CBZ/ZIP/folder | HIGH | LOW | **P1** |
| Source adapter engine + 2–3 sources | HIGH | **HIGH** | **P1** |
| Browse + chapter list | HIGH | MEDIUM | **P1** |
| Online reading + prefetch | HIGH | MEDIUM | **P1** |
| **Source↔tracker mapping** | HIGH | **HIGH** | **P1** (the risk) |
| **Progress sync (floor + monotonic guard)** | HIGH | MEDIUM | **P1** (the core value) |
| **Download queue** | HIGH | **HIGH** | **P1** |
| AnimeThemes list + audio play | MEDIUM | **LOW** | **P1** (best value/cost ratio in the milestone) |
| Debt D-I-03 (AniList rate limit) | — (invisible until it breaks) | LOW | **P1** (prerequisite) |
| CBR/RAR | MEDIUM | MEDIUM–HIGH | P2 |
| Double-page spread + offset | MEDIUM | MEDIUM | P2 |
| Mini-player across navigation | MEDIUM | MEDIUM | P2 |
| Download-ahead / delete-after-read | MEDIUM | LOW | P2 |
| Auto-split wide pages | LOW | MEDIUM | P3 |
| Crop borders / filters | LOW | LOW | P3 |
| Bookmarks | LOW | LOW | P3 |

---

## Competitor Feature Analysis

| Feature | Mihon (mobile, the stated model) | Kavita / Komga (desktop/web) | Our approach |
|---------|----------------------------------|------------------------------|--------------|
| Reading modes | Paged RTL/LTR/vertical, Long strip, Long strip w/ gaps | Single, Double, Double (Manga), Infinite scroll/webtoon | Mihon's set, plus Double for desktop |
| Desktop nav | **None** (volume keys, tap zones) | Keyboard + mouse | **Copy Kavita/YACReader, not Mihon** |
| Double-page | **"TBA"** (doesn't have it) | Yes, with offset | Differentiator — P2 |
| Tracker linking | **Manual** search-and-pick, always | N/A (they *are* the server) | **Auto-suggest + confirm** (reuse `matcher.py`) — differentiator |
| Local↔tracker identity | 3 hops (source → local manga → Track → remote) | N/A | **1 hop** (library entry *is* the tracker entry) — structural advantage |
| Chapter numbering | `ChapterRecognition` regex cascade; `lastChapterRead: Double`, floored on the wire | Filename/ComicInfo based | Copy Mihon's algorithm; `REAL` locally, `floor()` on the wire |
| Numbering disagreement | Not really handled (open pain) | N/A | **`chapter_offset`** — reuse the shipped `episode_offset` concept |
| Progress guard | `chapterNumber <= lastChapterRead → skip` | N/A | Same, but compare against the **tracker's** value (fixes their #1793) |
| Sync direction | **One-way**, explicitly | N/A | One-way. Plus an optional one-shot import on link |
| Downloads | Serial per source, parallel across ≤5; `Source/Manga/Chapter (hash).cbz`; `_tmp_` + rename | N/A | Copy wholesale — including the constraints |
| "Counts as read" | **Last page reached**, or explicit mark | page-position + completed flag; manual mark | Last page reached + explicit mark |
| Anime themes | ✗ | ✗ | **Nobody in this space does it.** Genuine differentiator, and it's cheap |

---

## Sources

**Primary (HIGH confidence):**
- Mihon source: [`ChapterRecognition.kt`](https://raw.githubusercontent.com/mihonapp/mihon/main/domain/src/main/java/tachiyomi/domain/chapter/service/ChapterRecognition.kt) — the chapter-number parsing algorithm
- Mihon source: [`TrackChapter.kt`](https://raw.githubusercontent.com/mihonapp/mihon/main/app/src/main/java/eu/kanade/domain/track/interactor/TrackChapter.kt) — the monotonic guard, the retry store
- Mihon source: [`Track.kt`](https://raw.githubusercontent.com/mihonapp/mihon/main/domain/src/main/java/tachiyomi/domain/track/model/Track.kt) — the mapping model
- [AnimeThemes API](https://api.animethemes.moe/) — **queried live 2026-07-13**; confirmed AniList *and* MyAnimeList `external_id` filters, `.ogg` audio links, `spoiler`/`nsfw`/`episodes`/`version` fields, `X-Ratelimit-Limit: 90`
- Nyanko's own codebase: `database.py` (`media_mappings`, `external_identities`, `local_files`, `match_corrections`, `episodes.episode_number REAL`), `matcher.py`, `http.py`, `models.py` (`ProgressUpdate.progress: int`), `providers.py`, `scanner.py`, `provider_mappings.py`

**Official docs (HIGH confidence):**
- [Mihon — Reader settings](https://mihon.app/docs/guides/reader-settings)
- [Mihon — Tracking](https://mihon.app/docs/guides/tracking) — "Tracking is one-way: Mihon → Tracker"; manual linking; "after reading the last page of a chapter"
- [Mihon — Downloads FAQ](https://mihon.app/docs/faq/downloads) — no parallel downloads per source; folder structure
- [Mihon — Local source](https://mihon.app/docs/guides/local-source/) — CBZ + ComicInfo.xml + cover layout
- [Extension source API contract (CONTRIBUTING.md)](https://github.com/yuzono/tachiyomi-extensions/blob/master/CONTRIBUTING.md) — `SManga`/`SChapter`/`Page` fields, source id stability, versioning
- [Kavita — Comic/Manga reader](https://wiki.kavitareader.com/guides/readers/comic-manga/) — desktop reader baseline
- [Komga — Read progress](https://komga.org/docs/guides/read-progress/)

**Issue reports (MEDIUM confidence — user-reported, but they corroborate the code):**
- [mihon#1793 — "Tracker updates wrong chapter"](https://github.com/mihonapp/mihon/issues/1793) — the monotonic-guard bug
- [mihon#1575 — decimal chapters (76.1/76.2) don't sync](https://github.com/mihonapp/mihon/issues/1575) — the floor() surprise
- [mihon#236 — sync read *page* progress with trackers](https://github.com/mihonapp/mihon/issues/236) — open, because trackers can't store it
- [mihon#2920 — parallel downloads](https://github.com/mihonapp/mihon/issues/2920) — refused deliberately
- [Kavita#3531 — chapters not marked complete in webtoon mode](https://github.com/Kareadita/Kavita/issues/3531) — why % thresholds are a trap

**Licensing (MEDIUM confidence):**
- unrar license permits decompression-only use free of charge; RAR *compression* is proprietary. `node-unrar-js` (Emscripten/WASM) avoids shipping an external binary; Python `rarfile` does not.

---
*Feature research for: manga reader + source engine + downloads + progress sync, inside an existing tracker*
*Researched: 2026-07-13*
