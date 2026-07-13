# Pitfalls Research

**Domain:** Manga reader (local + scraped online sources) + download queue + tracker progress sync, inside a sandboxed Electron shell with a Python FastAPI sidecar
**Researched:** 2026-07-13
**Confidence:** HIGH for everything grounded in this repo's code (cited by file:line); HIGH for the legal precedent (primary sources); MEDIUM for source-site behaviour (varies per site, by design).

> Ten of the twelve critical pitfalls below are **already latent in code that exists today**. This is not a
> generic list. Every claim about Nyanko is cited to a file and line. Read the Seam Risks section last and
> treat it as the most important one — it is the direct application of the v0.2 retrospective lesson
> ("a verified phase is not a safe phase — the failures live in the seams").

---

## Executive summary — the five things that will actually hurt

1. **D-I-03 is two bugs, not one.** The wrong number (90 vs 30) is the harmless half. The dangerous half is
   that `RateLimitedClient` shares one `asyncio.Semaphore` across two event loops in two threads, and it has
   only survived because the semaphore *never contends today*. Fixing the number **makes contention more
   likely** and can surface the real bug. See Pitfall 1.
2. **The renderer is `file://` in production** (`index.ts:83` → `win.loadFile`). Origin is `null`. With
   `webSecurity:true` the renderer **cannot** fetch a manga CDN, and `<img>` tags cannot send the `Referer`
   that manga CDNs require. Every page byte must flow through the sidecar. This is forced, not chosen. See Pitfall 2.
3. **That forced page-proxy reopens the cover-image scar exactly.** Any persisted page URL with a port in it
   re-creates the bug that once cost the entire library its covers. See Pitfall 3.
4. **`library_entries.progress` is `INTEGER`** (`database.py:159`). Manga chapter 10.5 has nowhere to go. See Pitfall 6.
5. **The legal exposure is not theoretical, and the takedown surface is the auto-updater itself.** A DMCA
   against the GitHub repo doesn't just remove the download — it **bricks auto-update for every installed
   user, silently**, because the updater feed *is* GitHub Releases. See Pitfall 12.

---

## Critical Pitfalls

### Pitfall 1: D-I-03 is a cross-event-loop concurrency bug wearing a rate-limit costume

**What goes wrong:**
The known debt is stated as "`requests_per_minute=90` but AniList says 30". That framing under-describes it.
Three separate defects live in `apps/backend/nyanko_api/http.py`:

- **(a) Wrong number.** `anilist.py:482` → `RateLimitedClient(requests_per_minute=90)`.
- **(b) It is not a rate limiter — it is a concurrency limiter.** `http.py:117-127`: the code acquires the
  semaphore, issues the request, then `await asyncio.sleep(self._interval)` **while still holding it**. With
  `requests_per_minute=90` the semaphore admits **90 simultaneous in-flight requests**. The `_interval`
  (0.667 s) only spaces out *release*, not *admission*. A burst of 20 page-fetches + a progress mutation all
  fire at once, immediately, with zero pacing.
- **(c) The semaphore is shared across event loops — this is the real bug.** `http.py:87` creates a single
  `asyncio.Semaphore` in `__init__`, on a module-level singleton (`anilist.py:482`). But this process runs
  **two event loops in two threads**: uvicorn's loop serving FastAPI, and `asyncio.run(_send_mutation(...))`
  inside a daemon thread (`main.py:1283`). The author already recognised this hazard for the HTTP client and
  fixed it — `http.py:103` keeps `_clients` keyed **per event loop**, with a comment explaining exactly why.
  **The semaphore was not given the same treatment.** An `asyncio.Semaphore` under contention creates waiter
  Futures bound to the acquiring loop; a `release()` from the *other* thread's loop calls `set_result()` on a
  foreign loop's Future → `RuntimeError: ... attached to a different loop`, or a silent permanent hang.

**Why it hasn't bitten:** with `value=90` and a strictly sequential backfill, `acquire()` **never blocks**, so
no waiter Future is ever created, so the cross-loop path is never taken. The bug is invisible precisely
because the limit is too high.

**The trap:** the "obvious fix" — change `90` to `30` — *increases* contention, makes `acquire()` block for the
first time, and can turn a dormant correctness bug into a live one. **Fixing (a) without fixing (b) and (c)
makes things worse.**

**How to avoid:**
- Fix all three together, in one plan, before any burst-producing feature exists.
- Do not hardcode `30`. AniList's own docs say **90/min is the normal limit and 30/min is a *temporary*
  degraded state**. Hardcode either number and you are wrong on some future date. **Read `X-RateLimit-Limit`
  from the response and adapt the budget at runtime**; `Retry-After` is already honoured (`http.py:51`) — extend
  that to also *lower the steady-state budget* when the header says so.
- Make the limiter a real token bucket keyed **per event loop** (same pattern already used for `_clients`), or
  move all outbound provider traffic onto a single owning loop so there is only ever one.
- Release the semaphore **before** the interval sleep, or drop the semaphore entirely and pace on the bucket.

**Warning signs:**
- `RuntimeError: Task got Future attached to a different loop` in `sidecar.log`.
- Progress sync that silently stops working after a reading session (a hung waiter never releases).
- 429s from AniList appearing for the first time right after the reader ships.
- A burst that "works on my machine" — the fast machine never contends.

**Phase to address:** **Foundations / rate-limit phase — FIRST, before the reader, the download queue, or sync.**
This is a prerequisite, not a debt item to sweep up at the end. Every other phase in this milestone produces bursts.

---

### Pitfall 2: The renderer is `file://` — it physically cannot load manga pages directly

**What goes wrong:**
The natural reader implementation is `<img src="https://cdn.some-manga-site/ch1/p01.jpg">` or a `fetch()` in the
renderer. Both fail in production, for two different reasons, and **both work in dev**, which is how this ships broken.

- In prod, `index.ts:83` calls `win.loadFile(...)` → the renderer origin is **`file://` (opaque / `null`)**.
- `fetch()` from a `null` origin to `https://` with `webSecurity:true` → **blocked by CORS**, always. No CDN
  will echo `Access-Control-Allow-Origin: null`.
- `<img>` tags are *not* CORS-restricted, so they appear to work — but a `file://` page sends **no useful
  `Referer`**. Manga CDNs almost universally run hotlink protection: **no `Referer` (or a wrong one) → `403`**.
  This is the single most common manga-scraper failure mode, and it is well documented across the ecosystem
  (HakuNeko carries dedicated `createConnectorURI` machinery purely to attach the right `Referer`).
- In dev, the renderer is served from `http://localhost:5173` (`index.ts:79-81`, `ELECTRON_RENDERER_URL`), a
  *real* origin that sends a *real* `Referer`. **Dev is a different security context from prod.** A reader that
  works perfectly for the whole implementation phase can return a wall of broken images the day it is packaged.

**Why it happens:** developers reach for the lowest-friction option (`<img src>`), it works locally, and the
`file://`-vs-`http://` origin difference is invisible until packaging.

**How to avoid:**
- **Decide the rule up front: no renderer-originated request ever leaves the machine.** Every page, thumbnail
  and cover flows **renderer → sidecar → source**. The sidecar has no CORS and can set `Referer`, `User-Agent`
  and cookies per-source. This is forced by the security constraints — and it is also the correct design,
  because it is the only place a per-source HTTP policy can be enforced (see Pitfall 4).
- The `Referer` is **per-source policy data**, not a global constant. Bake it into the adapter contract
  (`referer`, `user_agent`, `headers` as first-class adapter fields), because each site wants a different one.
- **Add a CSP.** There is currently **no `Content-Security-Policy` anywhere** — not in `index.html`, not via
  `onHeadersReceived` (verified: zero matches in `apps/desktop/electron/`). Today that is survivable because the
  renderer only talks to `127.0.0.1`. A reader that renders third-party-derived content without a CSP is a much
  bigger surface. Add `default-src 'self'; img-src 'self' http://127.0.0.1:* blob: data:; connect-src 'self' http://127.0.0.1:*`
  and let it *enforce* the "sidecar-only" rule rather than relying on discipline.
- **Never relax `webSecurity`.** It will be the first suggestion when the images 403. It is a hard constraint.
  The 403 is telling you the architecture is wrong, not that the flag is wrong.

**Warning signs:**
- Anyone proposes `webSecurity:false`, `session.defaultSession.webRequest.onBeforeSendHeaders` to spoof
  `Referer` for the renderer, or `--disable-web-security`.
- Images work in `npm run dev` and 403 in `electron-vite preview` / the packaged build.
- A plan that says "load page images in the reader component" without naming the sidecar.

**Phase to address:** **Source adapter engine phase** (defines the per-source header policy) + **Online reader
phase** (the page-proxy endpoint). Verification must run against a **packaged** build, not dev.

---

### Pitfall 3: Persisting a page URL with the sidecar's port in it — the cover-image scar, verbatim

**What goes wrong:**
This project has already lost every cover image in the library to exactly this bug. The reader is a *far* larger
surface for it: chapter page lists, download manifests, cache indexes, and thumbnail records are all URL-shaped
data that someone will want to persist.

The sidecar binds an **ephemeral port**. Once the page proxy exists, page URLs look like
`http://127.0.0.1:{port}/api/manga/page?...`. Persist that string — into a `downloads` row, a cached chapter
manifest, a `pages` JSON blob — and on the next launch the port is different and **every page 404s forever**.
An offline-downloaded chapter that renders a wall of broken images is *worse* than the cover bug, because the
user believes the bytes are safely on their disk.

**Why it happens:** the URL is right there in hand at fetch time; storing the resolved string is one less join.
It works all session. It breaks on restart, and the person who wrote it has moved on.

**How to avoid:**
- **The rule already exists in this codebase — reuse it, don't re-derive it.** `api.ts:204` stores
  paths **relative** (`/assets/...`) and re-prefixes with the *live* `apiUrl` at read time.
  `database.py:400-411` (`_migrate_asset_urls_to_relative`) is the migration that cleaned up the last
  occurrence, and its comment is a tombstone for this exact bug. Page/thumb references must be **relative paths
  or opaque IDs**, resolved to a URL only at render time.
- Downloaded chapters should be stored as **paths relative to the downloads root**, and the root resolved from
  `userData` at runtime — never an absolute path either, because the install location can move across an update.
- Add a **guard test** in the same spirit as the existing `userData` assert: a check that fails if any persisted
  column matches `LIKE 'http%'`. This class of bug has now happened once; the cheapest insurance is a test that
  makes it impossible to happen twice.
- Same rule for `blob:` URLs — they are origin-scoped *and* session-scoped, so persisting one is doubly wrong.

**Warning signs:**
- A DB column, JSON blob, or manifest containing `127.0.0.1` or `http://`.
- A downloaded chapter that reads fine now and 404s after a restart.
- Any code that concatenates `apiUrl` *before* a write instead of *after* a read.

**Phase to address:** **Schema/data-model phase** (define the storage contract as relative-only + the guard
test) — enforced in the **Online reader** and **Download queue** phases.

---

### Pitfall 4: The reader bursts; the source bans you — and the adapter has no HTTP policy to stop it

**What goes wrong:**
A chapter is 20-40 pages. A naive reader opens a chapter and fires **all 20 page requests at once**, plus
prefetches the next chapter. A batch download of 50 chapters does that 50 times. From the source's perspective
this is indistinguishable from an attack. Consequences, in the order they arrive:

1. `429`s / soft throttling.
2. Cloudflare interstitial → every request now returns HTML where the adapter expected an image.
3. IP ban (the user's home IP, not yours).
4. User-Agent ban — you get banned as *a class*, so **every Nyanko user is banned at once** from a single
   hardcoded UA. This is the one that turns one user's impatience into an outage for the whole install base.

**Why it happens:** the rate-limit discipline that exists for AniList/MAL/Kitsu (`RateLimitedClient`) has no
equivalent on the source side, because sources didn't exist before this milestone. The adapter gets written as
"fetch this URL", and concurrency is decided by whoever calls it.

**How to avoid:**
- **Rate limiting belongs to the adapter contract, not the caller.** Each source declares its own budget
  (`requests_per_minute`, `max_concurrency`, `referer`, `user_agent`). The engine *enforces* it — a caller
  cannot opt out. If the reader and the download queue can each independently hammer a source, you have built
  the bug.
- **One shared budget per source across all consumers.** Reader prefetch and download queue must draw from the
  **same** bucket. Two correct-in-isolation limiters that don't know about each other = 2× the intended rate.
  (This is Seam F.)
- Reuse `RateLimitedClient` **only after** Pitfall 1 is fixed — otherwise you are propagating the concurrency
  bug into a new, burstier caller.
- Cap reader prefetch hard (±2-3 pages, not "the whole chapter").
- **Do not ship a fake browser UA.** Beyond the ban-as-a-class risk, it is a bad-faith signal. A stable,
  honest, per-source-overridable UA is more defensible and more debuggable.
- Detect the Cloudflare interstitial explicitly (HTTP 403/503 + `cf-mitigated` / challenge HTML) and surface it
  as a distinct, actionable error — not as "parse failed".

**Warning signs:**
- Adapter code that takes a URL and returns bytes with no budget parameter.
- `asyncio.gather(*[fetch(p) for p in pages])` anywhere.
- The download queue and reader each having their own semaphore.
- The first user report of "images stopped loading" that resolves itself in 24h (= IP ban expiring).

**Phase to address:** **Source adapter engine phase** — the budget is part of the versioned adapter API from
day one. Retrofitting it after the download queue exists means changing every adapter.

---

### Pitfall 5: When a source dies, the user gets a blank reader instead of an explanation

**What goes wrong:**
Scraped sources **will** break — not *if*. The site changes a class name, adds Cloudflare, moves its CDN, or
goes offline entirely. The naive failure path is: selector returns `[]` → chapter list is empty → reader opens
on nothing → user sees a black screen and concludes **Nyanko** is broken. Worse: an empty parse result that is
cached as "this chapter has 0 pages", or a `null` chapter count that is written to the tracker as progress.

The subtle version is more dangerous: the site returns a Cloudflare challenge page (HTTP 200, HTML body), the
adapter's selector finds nothing, and the code treats "0 pages found" as a **valid empty result** rather than a
failure. Silent-empty is the enemy.

**Why it happens:** parsers are written against a live site on a good day. The unhappy paths (challenge page,
redirect to login, HTML shape changed, CDN 403) all produce "no matches" and get collapsed into one silent
empty list.

**How to avoid:**
- **`0 results` is an error, never a success.** An adapter that parses a chapter and finds zero pages must
  **raise**, not return `[]`. Same for a series with zero chapters. Make the distinction explicit in the adapter
  contract: `ParseError` / `SourceUnavailable` / `Blocked` / `NotFound` are different types with different UX.
- **Never cache a failure as data.** A failed fetch must not overwrite a previously-good cached chapter list.
  The user who has read up to ch. 40 should not lose their chapter list because the site had a bad afternoon.
- **Fail gracefully with attribution.** The error must name the *source*, not the app: "MangaSourceX is not
  responding (it may have changed or be blocked). Your downloaded chapters still work." — degrade to the local
  library rather than to a blank screen. This is the single highest-leverage UX decision in the milestone,
  because it is the difference between "this source is down" and "Nyanko is broken".
- **A dead source must not block the app.** Source health is per-source; one bad adapter cannot take down the
  library view, the local reader, or sync.
- **Version the adapter API** (already the plan) *and* record which adapter version produced a cached result, so
  a stale cache from a dead adapter can be invalidated wholesale.
- Ship a per-source **self-test** ("Test source" button / a `GET /api/sources/{id}/health`) that fetches one
  known series and validates the parse. This turns "a user says it's broken" into "the app already knows".

**Warning signs:**
- `return []` on a parse miss.
- `try/except: pass` around a fetch.
- A cache write that isn't gated on a *successful* parse.
- The reader's empty state and the reader's error state are the same component.

**Phase to address:** **Source adapter engine phase** (error taxonomy + no-silent-empty rule in the contract);
**Online reader phase** (the degradation UX).

---

### Pitfall 6: `progress` is an `INTEGER` and manga chapters are not

**What goes wrong:**
`database.py:159` — `library_entries.progress INTEGER NOT NULL DEFAULT 0`. Same at `database.py:169` for
`remote_library_entries.progress`. Meanwhile `episodes.episode_number` is `REAL` (`database.py:117`) — the
schema *already knows* fractional numbering exists, but the progress columns don't.

Manga chapter numbering is **routinely fractional**: `10.5`, `65.1`, extras, omakes, side stories. Also common:
chapters numbered per-volume and restarting; sources that number by *position* rather than by the chapter's
printed number; chapters that exist on the source and not on the tracker (and vice versa).

If the reader finishes chapter 10.5 and writes `int(10.5)` → `10`, then:
- The user's progress **goes backwards** if they were already at 11.
- Or 10.5 and 10 both round to 10, and the chapter is **double-counted** as read.
- Or a re-read of ch. 1 writes `progress = 1`, **destroying** a progress of 200.

That last one is data loss on the user's real, synced AniList list, and it is durable — `pending_mutations`
(`database.py:256`) will faithfully **retry** it.

**Why it happens:** the anime path got away with integers because episode numbering is (mostly) integral, and
the schema was built for anime. The manga reader inherits the columns without anyone re-asking the question.

**How to avoid:**
- **Decide the progress model before the reader writes a single row.** Two coherent options:
  - Store `progress` as `REAL` (migration; `remote_library_entries` too) and let the *provider adapter* decide
    how to round when pushing (AniList/MAL/Kitsu all take integers for chapters read).
  - Or keep the tracker-facing progress integral, and store the **source-side read position separately** (which
    is what you actually need anyway for "resume where I left off").
  These are not equivalent — pick deliberately and write it down.
- **Progress must be monotonic by default.** A sync must never *lower* the tracker's progress unless the user
  explicitly asked. Guard it: `new_progress = max(current, computed)` unless an explicit override flag is set.
  This one rule single-handedly kills the re-read data-loss scenario.
- **Re-reads are a distinct intent.** Finishing ch. 1 of a manga the user has already completed is not
  "progress = 1". Detect `status == COMPLETED` / `progress > chapter` and **do not auto-sync** — ask, or no-op.
- The **source's chapter number is not the tracker's chapter number.** Never assume the *n*th chapter in the
  source's list is chapter *n*. Use the parsed chapter number, and be explicit about what happens when it can't
  be parsed (answer: don't sync).

**Warning signs:**
- `int(chapter_number)` or `round()` anywhere near a sync path.
- A sync that writes `progress` without comparing to the current value.
- Any test fixture where every chapter is a whole number (the bug is invisible in that fixture).
- A user reporting their AniList progress went *down*.

**Phase to address:** **Schema/data-model phase** (the column type + the monotonic rule) — **must precede** the
progress-sync phase. Changing this after the reader ships means migrating rows users have already written.

---

### Pitfall 7: The source ↔ tracker identity mapping is wrong and progress lands on the wrong series

**This is the worst failure in the milestone. Treat it as a data-corruption risk, not a UX nicety.**

**What goes wrong:**
A source's series ("Kanojo mo Kanojo") must be bound to a tracker's media entry (AniList id `123456`). There is
**no shared identifier**. The only bridge is the title, and manga titles are a minefield: romaji vs. English vs.
native, season/part suffixes, colour editions, spin-offs with near-identical names, "official" vs. fan
translations, and the same title reused by different works.

The existing matcher (`matcher.py` + `normalizer.py`) is **title-similarity based**. That is entirely correct
for its current job — *suggesting* a match to a human who confirms it (the anime detection flow has
`match_corrections` and a confirm/undo step). It is **catastrophic** as the silent input to an automatic write.

The failure: user reads ch. 12 of series A → fuzzy match binds it to series B → the app **silently sets
progress on series B** in the user's real AniList list. `pending_mutations` retries it durably. The user's list
is now corrupt, they have no idea why, and there is **no undo** because nobody knew anything happened. Repeat
across a reading session and you have shredded a list that took years to build.

**Why it happens:** the mapping "mostly works" in testing (developers test with popular series that match
cleanly), and auto-sync is the milestone's headline feature so it gets built to fire eagerly. The 5% mismatch
rate is invisible in a demo and devastating in a library of 2,761 entries.

**How to avoid:**
- **The binding is explicit, stored, and user-confirmable — never computed at sync time.** A `source_bindings`
  row (`source_id`, `source_series_key`, `media_id`, `confidence`, `confirmed_at`) is the *only* thing a sync
  may read. A fuzzy match may **propose** a binding; it may never **be** one.
- **Auto-sync refuses to fire on an unconfirmed or low-confidence binding.** Fail closed. An unsynced chapter is
  an annoyance; a chapter synced to the wrong series is data loss. The asymmetry is total, and the design must
  reflect it.
- `external_identities` (`database.py:123`) has `UNIQUE(provider_id, external_id)` — it maps *tracker* ids to
  media. A **source** is not a tracker and its series key is not an `external_id`. Do not overload this table;
  a source binding is a different relation with different trust semantics (a tracker id is authoritative, a
  source binding is a *guess until confirmed*). Overloading it launders a guess into a fact.
- **Reuse the pattern that already works.** Anime playback detection already does exactly this: detect →
  propose → user confirms → undo available (`match_corrections`, `conflicts`, the confirm/undo flow). The
  manga reader should mirror it rather than invent an eager path. The milestone goal says the reader should feel
  like playback detection — this is where that principle has teeth.
- **Make every sync reversible.** `playback_events` already records `progress_before` / `progress_after`
  (`database.py:322-323`). A chapter sync must record the same, so a wrong write can be *undone*, not just
  regretted. Without `progress_before` there is no recovery — the old value is simply gone.
- Log every auto-sync to the activity timeline (which already exists, per PROJECT.md pre-0.3) so it is
  **visible**. Silent writes to a user's list are the thing that turns a bug into a betrayal.

**Warning signs:**
- A sync path that calls the matcher/normalizer at write time.
- A binding stored without a `confidence` or a `confirmed` flag.
- No `progress_before` recorded on a chapter sync.
- Test fixtures that only use series with unambiguous titles.
- A binding that is created implicitly as a side effect of opening a chapter.

**Phase to address:** **Identity/binding phase — a phase of its own, before progress sync.** It is tempting to
fold it into the sync phase as "step 1". Don't: that is precisely how it ends up eager and implicit. The sync
phase should be able to assume a *trusted* binding exists, and be allowed to refuse when it doesn't.

---

### Pitfall 8: The auto-updater hard-kills the sidecar mid-download

**What goes wrong:**
The download queue will live in the sidecar (it's the process with the HTTP stack, the source adapters, and the
DB). The updater kills the sidecar **before** installing — `updater.ts:70` → `await killSidecar()`, then
`autoUpdater.quitAndInstall(...)`.

And `killSidecar()` (`sidecar.ts:132-148`) is **not graceful**:
- `proc.kill()` on **Windows** is `TerminateProcess` — Node cannot deliver a POSIX signal. There is no
  `SIGTERM` handler the Python side could ever run. It is a hard kill from the first attempt.
- Then, after 4 s, `taskkill /PID {pid} /T /F` — a forced kill of the whole tree.

So the sidecar gets **zero opportunity to flush**. A chapter being written to disk when the user clicks "update"
is truncated mid-file. The DB row saying "chapter 12: downloading" survives; the file does not, or exists at
half size. On relaunch the app either (a) thinks the chapter is downloaded and shows a corrupt/blank chapter, or
(b) leaves a permanently "downloading" row that never completes and never retries.

The comment at `sidecar.ts:130` is explicit that this is a *deliberately* forced kill ("backend congelado, sin
/api/shutdown") — it exists because the file-lock problem (D-05) demanded it. **You cannot make it graceful
without reopening the file-locking bug that B-1 was about.** Design around it.

**How to avoid:**
- **The file is never the source of truth; the DB row is.** Download to `chapter.cbz.part`, `fsync`, then
  **atomically rename** to the final name, and only then mark the row `complete`. A `.part` file is
  self-identifying garbage that a startup sweep deletes. This makes a hard kill *safe by construction* — the
  same trick that makes SQLite survive power loss.
- **Reconcile on startup**, always. Any row in state `downloading` at boot was interrupted: reset it to
  `pending` (resumable) and delete its `.part`. Never trust in-flight state across a process boundary.
- **Verify the archive after download** (open the zip, check the central directory, count entries against the
  expected page count) *before* marking complete. A truncated CBZ that is marked complete is a permanent bad
  chapter the user must manually delete — and they can't, because the app says it's fine.
- **The updater should know about the queue.** `autoUpdater.autoDownload = false` (`updater.ts:16`) already
  means the install is a deliberate, user-confirmed moment — you have a natural place to intervene. Either warn
  ("3 chapters are downloading — they'll resume after the update") or pause the queue and drain briefly before
  killing. **Warn-and-resume is the lazy correct answer**; draining is a trap (an unbounded wait before an
  update is worse than a resumable interruption).
- Same reconciliation covers **app crash**, **user kills it from Task Manager**, and **machine power loss** —
  one mechanism, four bugs. Don't build an updater-specific special case.
- **Disk-full** is the untested sibling: `ENOSPC` mid-write must mark the row `failed` with a distinct reason
  and **not** retry in a tight loop (a full disk + an eager retry = a pegged CPU and a log file that fills the
  remaining bytes). Check free space before starting a batch.

**Warning signs:**
- A `downloads` row whose terminal state is set before the file is closed/renamed.
- No startup sweep for `.part` files or `downloading` rows.
- A download queue that resumes by re-reading files from disk rather than from the DB.
- Any plan that proposes adding `/api/shutdown` to make the kill graceful — this re-opens D-05/B-1.

**Phase to address:** **Download queue phase** (atomic write + startup reconciliation + archive verification).
The updater-warning UX is a small add to the same phase — **do not defer it to a "polish" phase**, because that
is exactly the seam where it gets lost (Seam B).

---

### Pitfall 9: The renderer balloons to 2 GB because nothing revokes the bitmaps

**What goes wrong:**
The canonical Electron image-viewer failure. A manga page is a ~200 KB JPEG on disk but a **~24 MB decoded
bitmap** in memory (2000×3000×4 bytes). A long-strip reader that mounts 40 pages, or a paged reader that
prefetches aggressively and never evicts, holds *dozens* of those. Add:
- `URL.createObjectURL(blob)` called per page and **never** `revokeObjectURL`'d → the blob is pinned for the
  lifetime of the document, forever, even after the `<img>` is unmounted.
- An unbounded JS `Map` cache of pages "so navigation is fast".
- React keeping unmounted-but-referenced nodes alive.

Result: RSS climbs monotonically across a reading session and never comes back down. The user reads 10 chapters
and the app is at 2 GB. It doesn't crash on the dev machine (32 GB RAM); it crashes for the user.

**Why it happens:** it is invisible in testing. Nobody reads 200 pages during a dev loop, and the memory is
reclaimed when you close the window. It requires a *long session* to appear — exactly what real users do and
developers don't.

**How to avoid:**
- **Bounded decode window.** Keep at most N pages (±2-3 around the current) as live `<img>`/bitmap. Everything
  else is unmounted. This is a *cap*, not a heuristic — enforce it in code.
- **Every `createObjectURL` has a matching `revokeObjectURL`** in the eviction path / `useEffect` cleanup. If
  you can't point at the revoke, you have a leak. Better: **avoid blob URLs entirely** — point `<img src>` at
  the sidecar's page endpoint (a normal HTTP URL) and let **Chromium own the decode and the eviction**. It has a
  real image cache and it is much better at this than hand-rolled code. This is the lazy *and* correct option,
  and it falls out of the architecture that Pitfall 2 already forces.
- Use `loading="lazy"` + `decoding="async"`; if you use `createImageBitmap`, you **must** call `.close()`.
- **Measure, don't feel.** The phase gate is a number: read 50+ pages, watch RSS in Task Manager, require it to
  come back down after leaving the reader. "It feels fine" is not a gate. A 2 GB RSS is a *user*-visible bug on
  a machine with 8 GB.
- Cap the *disk* cache too. An unbounded page cache in `userData` will quietly eat the user's SSD. The existing
  `CACHE_RESOURCE_LIMITS` (`database.py:276`) is the precedent — pages need the same treatment.

**Warning signs:**
- `createObjectURL` without a nearby `revokeObjectURL`.
- A `Map`/`useRef` page cache with no eviction.
- RSS that only goes up.
- Prefetch depth expressed as "the whole chapter".

**Phase to address:** **Online/local reader phase** (both — the local reader loading a 40-page CBZ has the same
problem). RSS ceiling belongs in the phase's UAT criteria as an explicit number.

---

### Pitfall 10: Schema migration against a live installed base with no escape hatch

**What goes wrong:**
`Database.initialize()` (`database.py:296`) is **not a versioned migration runner**. It:
- runs `executescript(SCHEMA)` (all `CREATE TABLE IF NOT EXISTS`) **on every boot**,
- runs a long list of `_add_column(...)` guards **on every boot**,
- runs **full-table backfills** (`_backfill_normalized_titles`, `_backfill_media_types`,
  `_migrate_asset_urls_to_relative`) **on every boot**,
- and then `INSERT OR IGNORE INTO schema_migrations VALUES (7)` — which **gates nothing**. It is a record, not
  a guard.

Three distinct hazards for this milestone:

1. **Startup latency regression.** Every backfill you add for manga runs on *every* launch, over the user's
   whole library (2,761 `library_entries`, 25,727 `episodes` on the author's own install). This project has
   *already* been bitten by slow startup (see the "prod startup slow" history). A new unguarded backfill over a
   large manga library re-opens it. New backfills must be **idempotent AND gated** — either by
   `CANONICAL_SCHEMA_VERSION` or by a cheap "is there anything to do?" check that short-circuits.
2. **No downgrade guard.** Auto-update is live, and users can and do reinstall an older build. A user on 0.3
   who lands back on 0.2.3 gets **old code against a new schema**. SQLite tolerates *extra* columns, so this
   fails *silently and partially* rather than loudly — the worst kind. Any new column that is `NOT NULL` without
   a default, or any new invariant the old code doesn't maintain, is a corruption vector.
3. **There is no "wipe and reinstall".** These are real libraries. `_requires_canonical_migration()` +
   `_backup_before_migration()` (`database.py:298-299`) already exist — **use them**. Bump
   `CANONICAL_SCHEMA_VERSION` (currently `7`) so the backup actually fires before the manga migration touches
   anything.

**How to avoid:**
- **Bump `CANONICAL_SCHEMA_VERSION` to 8** so `_backup_before_migration()` runs. This is the escape hatch, and
  it's already built. Not bumping it is a one-line omission that costs you the only rollback you have.
- New tables (`sources`, `source_bindings`, `downloads`, `read_progress`) are additive — low risk. The
  **dangerous** change is the one to an *existing* column: `library_entries.progress` INTEGER → REAL
  (Pitfall 6). That one needs the backup, and it needs to be exercised **against a copy of a real 2,761-entry DB**,
  not a fixture.
- **Write the downgrade note explicitly**, even if the answer is "we don't support it": if 0.3's columns break
  0.2.3, say so in the release notes, because a user *will* try it.
- Verify with the same rigour v0.2 used: `integrity_check`, row counts table-by-table, before/after, on a real
  DB. That standard is already established — meet it.

**Warning signs:**
- A new `_backfill_*` added without a short-circuit.
- `CANONICAL_SCHEMA_VERSION` still `7` when the migration ships.
- Migration tested only against a fresh/empty DB.
- Startup time regressing on a large library (measure it — the baseline is known: ~4 s / 0.43 s).

**Phase to address:** **Schema/data-model phase** (first). Verification against a **copy of the author's real
production DB** is a hard requirement of that phase's exit criteria.

---

### Pitfall 11: AnimeThemes audio — the small feature that leaks memory and state

**What goes wrong:**
The one "easy" feature. Its failure modes are real but cheap to prevent:
- An `<audio>` element per card. Mount 50 cards → 50 audio elements → 50 media pipelines. Chromium will
  throttle/fail past a limit, and RSS climbs.
- The user navigates away and the **audio keeps playing** (the element is unmounted but the media session isn't
  stopped, or a detached element retains a decoder).
- **Two cards play at once** (no global "only one playing" invariant).
- The AnimeThemes URL is **persisted** into the DB — same class as Pitfall 3, and their CDN URLs rotate.
- AnimeThemes is a **third-party origin**: fetching it from the renderer hits the same `file://`/CORS wall as
  Pitfall 2. It must go through the sidecar (or be an `<audio src>` to a sidecar-proxied URL).
- It gets bolted onto the card **without a rate limit**, so scrolling the library fires an AnimeThemes lookup
  per card.

**How to avoid:**
- **One** `<audio>` element, owned globally (a single player, cards just target it). This is fewer lines than
  the per-card version *and* it makes "only one plays" true by construction.
- Cache the *lookup result* (the theme metadata), not a resolved CDN URL. Resolve at play time.
- Look up themes **lazily and rate-limited** — on card open, not on library render.
- Stop playback on unmount/navigation. Explicitly.

**Warning signs:** `<audio>` inside a card component; an AnimeThemes URL in a DB column; a lookup in a list-render path.

**Phase to address:** **AnimeThemes phase** (last — it depends on nothing else and is the safest thing to cut
if the milestone runs long).

---

### Pitfall 12: Shipping first-party scrapers in a signed, auto-updating binary — the honest version

**The user has decided to ship first-party sources. This section is not an argument against that. It is what he
is signing up for, stated plainly, plus the mitigations that make the decision survivable.**

**What the precedent actually is — this is not hypothetical:**

- **Tachiyomi was killed by it.** In January 2024, contributors received a cease-and-desist from **Kakao
  Entertainment** (via P.CoK, its anti-piracy division). The demand: destroy the project and ensure deletion of
  all forks. Tachiyomi **ceased all development**. Note the target: **the contributors, personally** — not a
  faceless org.
- **Tachiyomi's concession was to stop doing the exact thing Nyanko plans to do.** Its settlement behaviour was
  to **remove the preloaded extension list** — versions after Jan 6-8 2024 shipped with **no bundled sources**.
  The thing that got negotiated away was *bundling*.
- **Sony DMCA'd ~200 Aniyomi extensions** (June 2024), taking out a fork's source repo wholesale.
- **Mihon ships no sources, and that is deliberate legal architecture, not a packaging preference.** It is the
  load-bearing separation: Mihon is a *reader*; someone else, elsewhere, provides sources. Mihon is *still*
  fielding threat-by-association as of its November 2025 notice.

**Nyanko's position, stated without softening, is strictly worse than the project that got killed:**

| | Tachiyomi (killed) | Mihon (survives) | **Nyanko as planned** |
|---|---|---|---|
| Sources bundled in the app | Preloaded list (removed under C&D) | **No** | **Yes, first-party** |
| Who wrote the scrapers | Community, separate repo | Third parties | **The author** |
| Distribution | Unsigned APK | Unsigned APK | **Code-signed, auto-updating desktop binary** |
| Attribution | Pseudonymous contributors | Pseudonymous | **A named GitHub account, an author** |

Every axis moves the wrong way. "First-party scrapers, written by a named person, bundled in a signed binary
that auto-updates" is the maximum-exposure configuration. There is no version of this analysis where that isn't true.

**The consequence nobody plans for — the takedown surface is the auto-updater:**
`updater.ts:22-27` — the update feed comes from `app-update.yml`, generated from the `publish:` block, pointing
at **GitHub Releases**. So a DMCA takedown of the repo is not merely "the download link breaks":

- **The update feed dies.** Every installed user's app silently stops finding updates. No error the user
  understands, no migration path, **no way to reach them** — you cannot ship a fix to an app whose only channel
  you just lost.
- There is **no fallback feed**. Not a hypothetical: this project has *already* seen releases vanish and 404
  (v0.2.1/v0.2.2 were deleted; their tags remain, their releases 404 — MILESTONES.md).
- The installed base is **stranded on the version that got taken down** — the one with the scrapers in it.

**The options, with their consequences:**

| Option | Exposure | Cost | Notes |
|---|---|---|---|
| **A. Ship first-party sources bundled** (the decision) | **Highest.** The Tachiyomi configuration, plus signing and a name. | Zero extra work | Accept knowingly, and build the mitigations below |
| **B. Ship the engine, zero bundled sources; user adds a source URL at runtime** | **Much lower.** The Mihon posture. The app is a reader; it ships no infringing code. | Small: sources load from a URL instead of a bundle | Preserves the whole feature. The *user* chooses the source. This is the one that materially changes the legal picture |
| **C. Ship only legal sources** (official/free-legal catalogs) | Minimal | Small catalog; may not satisfy the product goal | Combines well with B |
| **D. Local-only reader now; online sources later** | None now | Defers the headline feature | Not what the milestone is for |

**The mitigations to build even if you choose A** (these are cheap, and they are what turns a fatal event into a
survivable one):

1. **Decouple the update feed from the takedown surface.** If the sources and the app ship from the same GitHub
   repo, one notice takes both. Host `latest.yml` + the installer somewhere that is not the same target — a
   separate repo, or any static host. This is a small config change **now** and impossible **later** (you can't
   push a new feed URL to an app whose feed is dead). **This is the single highest-value item in this document
   relative to its cost.**
2. **Make sources loadable at runtime, not baked into the binary.** Even shipping them first-party, if an
   adapter is *data* (fetched/updatable independently) rather than *compiled in*, you can **remove a source
   without shipping a new binary** — and, critically, you can comply with a takedown in an afternoon instead of
   a release cycle. This also happens to be the better engineering (Pitfall 5: dead sources need to be
   replaceable fast). **The architecture that is legally survivable and the architecture that is technically
   correct are the same architecture here.**
3. **Keep the reader source-agnostic.** The local-archive reader is legally uninteresting. If sources are a
   clean plug-in boundary, worst case you pull them and Nyanko is still a manga reader.

**Warning signs:** the roadmap treats sources as a compile-time list; the release pipeline has exactly one host;
nobody has written down what happens the day a notice arrives.

**Phase to address:** **Source adapter engine phase** — the runtime-loadable boundary is an *architectural*
decision that cannot be retrofitted. **The feed decoupling belongs in the first phase that touches release
config, and it is the cheapest insurance in this milestone.**

---

## Seam Risks — where per-phase gates pass and the combination fails

> The v0.2 retrospective: *"a verified phase is not a safe phase — the failures live in the seams."* B-1 was two
> individually-correct phases combining into a silently-broken result that every per-phase gate passed. These
> are this milestone's B-1 candidates. **Each one passes both of its phases' gates in isolation.**

| # | Seam | Phase A (passes) | Phase B (passes) | What the combination does |
|---|---|---|---|---|
| **A** | **Rate limiter × reader bursts × MutationWorker thread** | Rate-limit fix: "90 → 30, tests pass" | Reader: "chapters load, tests pass" | The semaphore **contends for the first time**, across two event loops (`main.py:1283` vs. uvicorn's). Cross-loop `Future.set_result` → `RuntimeError` or a silent hang that kills progress sync. **Neither phase's gate can see this** — it needs contention *and* two loops *and* a burst. Fixing the number is what *arms* it. |
| **B** | **Download queue × auto-updater** | Download queue: downloads work, resume works | Updater: already shipped, proven in v0.2 | `killSidecar()` = `taskkill /T /F` (`sidecar.ts:144`) mid-write → truncated archive marked complete. The updater phase **already passed months ago** and nobody re-runs it against a queue that didn't exist then. |
| **C** | **Source adapter × persisted URLs × port change** | Adapter: returns correct page URLs | Download/cache: persists chapter manifests | The cover-image bug, verbatim, at a bigger blast radius. Both phases pass because **within one session the port never changes**. Only a restart reveals it — and phase gates don't restart the sidecar. |
| **D** | **Identity mapping × auto-sync × `pending_mutations` retry** | Mapping: "matches the right series in our test set" | Sync: "correctly pushes progress to AniList" | A **correct sync of a wrong mapping**, retried durably onto the user's real list, with no `progress_before` to undo it. Both phases are individually, verifiably correct. The corruption lives *entirely* in the seam. |
| **E** | **Schema migration × auto-update × downgrade** | Migration: upgrade verified on a real DB copy | Updater: proven | Nobody tests **0.3 → 0.2.3 downgrade**, or a user who skips 0.3.0 and lands on 0.3.2 from 0.2.3. `initialize()` re-runs everything every boot and **gates nothing** on version. |
| **F** | **Reader prefetch × page proxy × source rate limit** | Reader: prefetches ±5 pages, fast | Download queue: rate-limited, polite | Two independent, individually-correct limiters against **one source** = 2× the intended rate → the ban lands on the *user's* IP, or on Nyanko's UA for *everyone*. Each phase's gate measures only its own traffic. |
| **G** | **CSP × page proxy × AnimeThemes** | Reader: images load | AnimeThemes: audio plays | Adding a CSP late breaks both; adding it never leaves third-party-derived content unconstrained. Each phase "works"; the *security posture* is what silently degrades, and no phase owns it. |

**Recommendation to the roadmapper:** these seams are **not** coverable by per-phase gates — that is the
definition of a seam. Two structural answers, and the milestone should adopt both:

1. **Order phases so the seam is inside a phase, not between two.** Specifically: the **rate-limit fix must land
   before any burst-producing phase** (Seam A), the **schema decisions before anything writes rows** (Seams D, E),
   and the **source-budget must be owned by the adapter engine, not its callers** (Seam F).
2. **Budget an explicit cross-phase audit before the milestone closes** — v0.2's cross-audit is the *only* thing
   that caught B-1, and it caught it *after* every phase had passed. That audit is not optional overhead; it is
   the control that works. Its checklist is the table above.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Hardcode `requests_per_minute=30` for AniList | One-line "fix" of D-I-03 | Wrong again when AniList restores 90/min; leaves the concurrency + cross-loop bugs armed | **Never** — read `X-RateLimit-Limit` |
| Fuzzy-match source→tracker at sync time | No binding UI to build | Corrupts users' real lists, durably, with no undo | **Never** |
| `<img src="https://cdn...">` direct from renderer | Simplest possible reader | 403s in prod (works in dev); invites `webSecurity:false` | **Never** |
| Persist the resolved page URL | One less join | Re-creates the cover-image bug | **Never** |
| Sources compiled into the binary | Slightly simpler build | Cannot remove a source without a release; can't respond to a takedown quickly; a dead source needs a full release cycle to fix | Only if runtime loading is genuinely infeasible |
| Single release host (repo == feed == sources) | It's what exists | A takedown **bricks auto-update for everyone**, permanently | Only until the first online source ships |
| Prefetch the whole chapter | Feels instant | 2 GB RSS; source ban | Only for a **local** archive already on disk |
| Mark a download complete before `fsync`+rename | Simpler queue code | Corrupt archives on every update, crash, and power loss | **Never** — this is 5 lines |
| Skip `CANONICAL_SCHEMA_VERSION` bump | Nothing to think about | No pre-migration backup — you lose the only rollback you have | **Never** |
| Store manga progress as INTEGER | No migration needed | Silent truncation of ch. 10.5; progress can go *backwards* | **Never** — decide before first write |

---

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| **AniList** | Hardcode a rate limit; assume the documented 90/min | 30/min is a **temporary degraded** state; read `X-RateLimit-Limit` per response and adapt. `Retry-After` is already honoured (`http.py:51`) — extend it to lower the steady-state budget too |
| **AniList / MAL / Kitsu** | Push progress from a fuzzy match | Push only from a **confirmed binding**; `max(current, new)` unless explicitly overridden; record `progress_before` for undo |
| **MAL** (`requests_per_minute=60`) / **Kitsu** (`50`) | Assume they're fine because they haven't broken | They share the *same* `RateLimitedClient` bug (concurrency limiter + shared semaphore). Fixing it fixes all three |
| **Manga source HTML** | Selector returns `[]` → treated as a valid empty chapter | `0 results` = **error**, never data. Never cache a failure over a good result |
| **Manga image CDN** | Fetch without `Referer` | Per-source `Referer`/`User-Agent` in the adapter contract; all fetches via the sidecar (the renderer *cannot* do this — `file://`) |
| **Cloudflare** | Challenge HTML parsed as a manga page | Detect the challenge explicitly (403/503 + challenge markers) → distinct `Blocked` error → actionable UX |
| **AnimeThemes** | An `<audio>` per card; persist the CDN URL | One global player; cache metadata, resolve the URL at play time |
| **GitHub Releases (updater feed)** | Assume it will always be there | It is a **takedown surface**. Decouple the feed host from the sources — before the first source ships |

---

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Unbounded decoded-bitmap cache | RSS only goes up; app at 2 GB | Bounded window (±2-3 pages); let Chromium own the decode | ~50-100 pages in one session |
| `createObjectURL` never revoked | Memory never returns after leaving the reader | Revoke on eviction — or avoid blob URLs entirely | Any long session |
| Prefetch whole chapter / whole queue | Source 429s, then bans | Per-source shared budget, enforced by the engine | First 40-page chapter, or first batch download |
| Unguarded backfill on every boot | Startup regresses (baseline ~4 s / 0.43 s) | Short-circuit the backfill; gate on schema version | A large manga library |
| Unbounded page cache on disk | User's SSD quietly fills | Cap it, like `CACHE_RESOURCE_LIMITS` (`database.py:276`) | Weeks of reading |
| Sync fired per page turn | 429s; tracker throttles | Sync **on chapter completion only**, debounced, via `pending_mutations` | A single reading session |

---

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| `webSecurity:false` to "fix" image 403s | Detonates the whole security model; renders third-party content with full privileges | **Hard constraint.** Route images through the sidecar. The 403 means the architecture is wrong, not the flag |
| No CSP (**current state** — zero matches in `apps/desktop/electron/`) | Third-party-derived content in the renderer with no content restrictions | Add a CSP *with* the reader: `img-src 'self' http://127.0.0.1:* blob: data:; connect-src 'self' http://127.0.0.1:*` |
| Rendering scraped HTML/SVG | XSS from a compromised or malicious source | Never inject source HTML. Adapters return **structured data** (URLs, numbers, titles) — never markup |
| Source adapter as executable code with full sidecar privileges | An adapter is a scraper with your file system and your DB | 0.3 ships first-party only (per PROJECT.md). **This is the reason third-party adapters are correctly out of scope** — do not let "runtime-loadable" (Pitfall 12) quietly become "any URL can supply code" without the sandbox that decision requires |
| Trusting source-supplied page URLs | SSRF / local file access via a crafted URL | Validate scheme (`https:` only) and reject `file:`/`localhost`/private ranges before fetching |
| Spoofing a browser User-Agent | Ban-as-a-class for every user; bad-faith signal | Honest, per-source-overridable UA |

---

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Dead source → blank reader | User concludes **Nyanko** is broken | Name the source, offer the local/downloaded fallback |
| Silent auto-sync | User's list changes with no visible cause; if wrong, feels like a betrayal | Log every sync to the activity timeline (it exists); make it undoable (`progress_before`) |
| Sync fires on a re-read | Progress of 200 overwritten with 1 | Detect COMPLETED/`progress > chapter` → ask, or no-op |
| Download interrupted → shows as complete | User opens a corrupt chapter offline, with no recourse | Verify the archive before marking complete; `.part` + atomic rename |
| Update kills in-flight downloads with no warning | User loses a 50-chapter batch silently | Warn at the (already user-confirmed) install prompt; resume after restart |
| Binding UI buried | Users never confirm → either no sync, or (worse) eager wrong sync | Make confirmation part of the reading flow, like playback confirm/undo |

---

## "Looks Done But Isn't" Checklist

- [ ] **Rate limiting:** number fixed, but the semaphore is still shared across event loops and still held during the interval sleep — verify **all three** parts of Pitfall 1, under real contention
- [ ] **Online reader:** works in `npm run dev` (origin `http://localhost`) — verify in a **packaged** build (origin `file://`), which is a different security context
- [ ] **Page URLs:** work all session — verify after a **sidecar restart on a different port**
- [ ] **Download queue:** resumes after a clean quit — verify after `taskkill /F` **mid-write**, and after a real auto-update
- [ ] **Downloaded chapter:** row says complete — verify the **archive actually opens** and has the expected page count
- [ ] **Progress sync:** pushes correctly — verify it **refuses** on an unconfirmed binding, **never lowers** progress, and handles **ch. 10.5**
- [ ] **Migration:** runs on a fresh DB — verify on a **copy of the real 2,761-entry production DB**, with `integrity_check` + row counts, and verify `CANONICAL_SCHEMA_VERSION` was bumped
- [ ] **Memory:** reader feels fine — verify **RSS after 50+ pages**, and that it **comes back down**
- [ ] **Source failure:** handled — verify a **Cloudflare challenge page** (HTTP 200, HTML body) is an error, not an empty chapter
- [ ] **Release:** publishes — verify the **update feed is not on the same takedown surface as the sources**

---

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Progress synced to the wrong series | **HIGH — possibly unrecoverable** | Only recoverable if `progress_before` was recorded. Otherwise the user's data is gone and they don't know it. **This is why Pitfall 7 is prevention-only** |
| Persisted URLs with the port in them | LOW (a migration exists) | Copy `_migrate_asset_urls_to_relative` (`database.py:400`) — but only *after* every user has already lost their downloads once |
| Corrupt downloaded archives | MEDIUM | Startup sweep deletes `.part`; re-verify archives; re-queue failures. Painful only if rows were marked complete without verification |
| Migration corrupts a real DB | MEDIUM **if** `_backup_before_migration()` fired; **CATASTROPHIC** if `CANONICAL_SCHEMA_VERSION` wasn't bumped | Restore from the pre-migration backup. There is **no other escape hatch** |
| Source dies | LOW **if** adapters are runtime-loadable; **HIGH** if compiled in (full release cycle) | Ship a new adapter |
| DMCA takedown | **CATASTROPHIC if the feed shares the surface** (installed base stranded, silently, unreachable); LOW if decoupled | Pull sources, ship a new build over the surviving feed |
| AniList 429 storm | LOW | `Retry-After` is already honoured; the fix is the limiter |

---

## Pitfall-to-Phase Mapping

Phase names are indicative — the roadmapper should map them onto the real phases. **The ordering constraints are
not.**

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| 1. Rate limiter (3 bugs) | **Rate-limit/foundations — FIRST** | Burst 50 concurrent requests **from both event loops**; no `RuntimeError`, no hang, no 429 |
| 6. Decimal/monotonic progress | **Schema — before any write** | Ch. 10.5 round-trips; a re-read cannot lower progress |
| 3. Relative URLs only | **Schema** (contract + guard test) | Restart the sidecar on a new port; every page still loads |
| 10. Migration + backup | **Schema** | `CANONICAL_SCHEMA_VERSION` bumped; `integrity_check` + row counts on a **real DB copy** |
| 12. Runtime-loadable adapters; **decoupled update feed** | **Adapter engine** + **first release-config phase** | A source can be removed **without shipping a binary**; the feed host ≠ the sources host |
| 4. Per-source budget | **Adapter engine** | Reader + download queue against one source ≤ the declared budget (**combined**) |
| 5. No silent-empty; error taxonomy | **Adapter engine** | A Cloudflare challenge page raises `Blocked`, not `[]` |
| 2. Sidecar-only fetches + CSP | **Adapter engine** + **online reader** | Verified in a **packaged** build (`file://`), not dev |
| 9. Bounded memory | **Reader (local + online)** | RSS after 50+ pages; returns to baseline on exit |
| 8. Atomic downloads + updater seam | **Download queue** | `taskkill /F` mid-write → clean resume; real auto-update mid-download |
| 7. Identity binding | **Binding — its own phase, before sync** | Sync **refuses** on an unconfirmed binding; every sync is undoable |
| 11. AnimeThemes | **AnimeThemes (last)** | One player; no persisted CDN URL |
| **All seams (A-G)** | **Cross-phase audit before close** | The seam table above **is** the checklist |

**Hard ordering constraints:**
1. **Rate-limit fix → before** the reader, the download queue, and sync (Seam A). It is currently listed as
   "0.2 debt". **It is a prerequisite, not a debt item.** Sweeping it up at the end is the single most likely
   way this milestone ships a B-1.
2. **Schema decisions → before** anything writes a row (Pitfalls 3, 6, 10).
3. **Adapter engine (with its budget + error taxonomy + runtime-loadability) → before** the online reader and
   the download queue.
4. **Binding → before** progress sync.
5. **Feed decoupling → before** the first online source ships. It is a config change now and **impossible later**.

---

## Sources

- **This repository** (highest confidence — cited inline by file:line): `apps/backend/nyanko_api/http.py`
  (`RateLimitedClient`, the shared semaphore, the interval-held-under-lock), `anilist.py:482`,
  `main.py:1283` (`asyncio.run` in a daemon thread), `database.py` (schema, `initialize()`,
  `_migrate_asset_urls_to_relative`, `CANONICAL_SCHEMA_VERSION`, `pending_mutations`, `external_identities`),
  `apps/desktop/electron/main/sidecar.ts` (`killSidecar` → `taskkill /T /F`),
  `apps/desktop/electron/main/updater.ts` (kill-before-install; feed from `app-update.yml`),
  `apps/desktop/electron/main/index.ts:83` (`loadFile` → `file://`), `apps/desktop/src/api.ts:204`
  (relative-asset re-prefixing).
- **Project history:** `.planning/PROJECT.md`, `.planning/MILESTONES.md` (the B-1 seam lesson; the 6-DB and
  port-in-URL scars; deleted releases 404ing).
- [AniList API — Rate Limiting](https://docs.anilist.co/guide/rate-limiting) — 90/min documented; **30/min is a
  temporary degraded state**. Confirms hardcoding either number is wrong.
- [Tachiyomi ceases development after Kakao cease-and-desist](https://animecorner.me/tachiyomi-team-stops-app-development-after-cease-and-desist-by-kakao-entertainment/)
- [TorrentFreak — Tachiyomi: how threats motivate pirates](https://torrentfreak.com/tachiyomi-manga-reader-how-threats-can-motivate-pirates-boost-engagement-240113/) —
  the concession was **removing the preloaded extension list**.
- [TorrentFreak — Sony DMCA nukes 200 Aniyomi extensions](https://torrentfreak.com/sony-dmca-notice-nukes-200-aniyomi-extensions-as-tachiyomi-fork-feels-heat-240617/)
- [Mihon — "Mihon could be under threat" (Nov 2025)](https://mihon.app/news/2025-11-05-potential-threat) —
  ongoing threat-by-association; the no-bundled-sources separation is load-bearing.
- [CBR — Kakao legal threats end Tachiyomi development](https://www.cbr.com/kakao-entertainment-manwha-manga-app-tachiyomi-legal-threats/)
- [HakuNeko PR #4594 — fixing MangaFox Cloudflare CDN (Referer handling)](https://github.com/manga-download/hakuneko/pull/4594) —
  confirms per-source `Referer` is standard practice, not paranoia.
- [Cloudflare Community — hotlink protection returns 403 on images without Referer](https://community.cloudflare.com/t/block-direct-access-to-an-image-but-leave-it-visible-on-the-site/469342)

---
*Pitfalls research for: manga reader + scraped sources + download queue + tracker sync, in sandboxed Electron with a Python sidecar*
*Researched: 2026-07-13*
