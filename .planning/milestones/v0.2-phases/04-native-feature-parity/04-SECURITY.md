---
phase: 04-native-feature-parity
audited: 2026-07-11
asvs_level: 1
block_on: high
threats_total: 11
threats_closed: 11
threats_open: 0
unregistered_flags: 0
status: secured
---

# Phase 4: Native feature parity — Security Audit

**Verdict:** SECURED. Every declared mitigation was located in implemented code. No blocking gap.

Register source: `<threat_model>` blocks of 04-01-PLAN.md (T-04-01..03), 04-02-PLAN.md (T-04-04..07),
04-03-PLAN.md (T-04-SC, T-04-08..11). Verification depth: ASVS L1 (mitigation present in the cited
file), with the L2 boundary check applied opportunistically where a single grep would have been weak
evidence (preload surface, openExternal/openPath guards, prefs write path).

## Threat Verification

| Threat ID | Category | Severity | Disposition | Status | Evidence |
|-----------|----------|----------|-------------|--------|----------|
| T-04-01 | Elevation of Privilege | low | mitigate | CLOSED | `electron/main/ipc.ts:73-82` — all three `window:*` handlers resolve the target via `BrowserWindow.fromWebContents(e.sender)`; no window id, no payload of any kind is read. A compromised renderer (main window or splash) can only act on its own window. |
| T-04-02 | Tampering | medium | mitigate | CLOSED | `electron/preload/index.ts:24-26` — exactly `minimizeWindow` / `toggleMaximizeWindow` / `closeWindow`, each a fixed named channel. Whole-file check: `exposeInMainWorld("nyanko", …)` exposes only named methods; no `ipcRenderer` object, no generic `invoke(channel, …)`, no `on(channel)` passthrough (`onDetectionPaused` is a fixed-channel subscription returning an unsubscribe). |
| T-04-03 | Information disclosure | low | accept | CLOSED (accepted) | Accepted risk logged below. `electron/main/index.ts:40` — `icon: join(__dirname, "../../build/icon.png")`, a build-time constant; `electron/main/tray.ts:69` reuses the same constant. Never renderer-supplied. |
| T-04-04 | Tampering | high | mitigate | CLOSED | `electron/main/window-prefs.ts:49-54` — `saveWindowPrefs(dir, input)` writes `join(dir, "window_prefs.json")`, filename fixed. `dir` is never a parameter of the IPC surface: `ipc.ts:89` calls `updateWindowPrefs(prefs)`, which uses the module-level `cacheDir` seeded once at `index.ts:119` from `app.getPath("userData")`. The renderer supplies no path segment at any point → no traversal. See Observation 1 for a hardening note on the pre-seed window. |
| T-04-05 | Tampering | medium | mitigate | CLOSED | `electron/main/window-prefs.ts:29-36` — `coercePrefs` returns a fresh object literal with exactly `Boolean(o.close_to_tray)`, `Boolean(o.minimize_to_tray)`, `Boolean(o.start_minimized)`; unknown keys are structurally unreachable. Applied on both edges: `saveWindowPrefs` (write) and `loadWindowPrefs` (read of an on-disk file). `window-prefs.test.ts:31-40` asserts `__proto__`/`hacker` keys are dropped — `npm run test:prefs` 4/4. |
| T-04-06 | Spoofing / SSRF | medium | mitigate | CLOSED | `electron/main/tray.ts:21-32` — `resolveApiUrl()` builds `http://127.0.0.1:${port}` from a literal host; `port` comes from `userData/port`, is `parseInt`-ed and gated on `Number.isInteger(port) && port > 0`, falling back to `8765`. `tray.ts:49-51` — the only fetch: POST to `${resolveApiUrl()}/api/detection/${paused ? "pause" : "resume"}` (path from a boolean, not a string), with `AbortSignal.timeout(5000)`. No renderer input reaches the URL: the toggle is a tray menu click, not an IPC channel. |
| T-04-07 | Tampering | medium | mitigate | CLOSED | `electron/preload/index.ts:29-30` — only `getWindowPrefs` / `setWindowPrefs`, fixed channels `window-prefs:get` / `window-prefs:set`. Same whole-file finding as T-04-02: no raw `ipcRenderer` reaches the renderer world. |
| T-04-SC | Tampering (supply chain) | high | mitigate | CLOSED | Blocking human checkpoint was executed and approved before install (04-03-SUMMARY.md "Checkpoint Resolved", and confirmed by the operator in-session). Spelling verified post-install: `apps/desktop/package.json:18` = `"@xhayper/discord-rpc": "^1.3.4"` — exact approved scope/spelling, no typosquat variant. `package-lock.json:2954-2957` resolves it to `https://registry.npmjs.org/@xhayper/discord-rpc/-/discord-rpc-1.3.4.tgz` with an `sha512` integrity hash. Only one `xhayper` entry exists in the lockfile (no shadow/duplicate resolution). |
| T-04-08 | Denial of Service | medium | mitigate | CLOSED | `electron/main/discord.ts:30-47` — `connected()` wraps `new Client` + `login()` in try/catch and returns `null` on failure. `discord.ts:71-77` — `setActivity` in try/catch; on error the client slot is dropped. `discord.ts:80-87` — `clearActivity` in try/catch. `discord.ts:38` — `c.on("error", () => {})` attached before `login()`: this closes the real DoS path (an unhandled EventEmitter `error` when Discord dies mid-session throws in the main process), which the Rust original did not have. No top-level connect exists — the build passes with Discord closed. |
| T-04-09 | Tampering | low | accept | CLOSED (accepted) | Accepted risk logged below. `electron/main/discord.ts:11-17` — id is `process.env.NYANKO_DISCORD_CLIENT_ID \|\| "1521045260342525962"` plus the `UNCONFIGURED` sentinel; the renderer payload is narrowed at `discord.ts:56-60` to `details`/`state` (typeof string) and `start_timestamp` (typeof number) — no client-id path from the renderer. |
| T-04-10 | Tampering | medium | mitigate | CLOSED | `electron/preload/index.ts:33-34, 37-38` — `setDiscordActivity` / `clearDiscordActivity` / `getAutostart` / `setAutostart`, all fixed named channels. `ipc.ts:102-104` re-coerces the autostart flag with `Boolean(enabled)` and hardcodes `args: ["--minimized"]` — the renderer cannot inject launch arguments into the login item. |
| T-04-11 | Elevation of Privilege | medium | mitigate | CLOSED | Phase-3 guards re-read, not assumed: `ipc.ts:41-44` — `openExternal` still rejects anything not matching `/^https?:\/\//i`. `ipc.ts:47-50` — `openPath` still returns `""` for any string containing `://`. `ipc.ts:51-54` — `revealItemInDir` keeps the same `://` rejection. `ipc.ts:29-36` — `readAppDataFile` still enforces the `{port, instance_token}` whitelist. The Phase-4 additions are appended below the Phase-3 block (Task-2 `ipc.ts` diff: 9 insertions, 0 deletions), so no guard was weakened while the boundary was extended. |

**Closed: 11/11. Open (blocking): 0. Open (non-blocking): 0.**

## Accepted Risks Log

| Threat ID | Severity | Risk | Why accepted | Boundary that holds |
|-----------|----------|------|--------------|---------------------|
| T-04-03 | low | The app icon path (`build/icon.png`) is read from disk at window/tray construction. | The path is a build-time constant compiled into the main bundle, resolved relative to `__dirname`. It is not reachable from the renderer, from IPC, or from any config file. Worst case is a missing-icon cosmetic failure (already tracked as a Phase-5 packaging item in 04-VERIFICATION.md), not disclosure. | main-process constant; no renderer input path exists. |
| T-04-09 | low | The Discord client id is a compile-time constant with an env override (`NYANKO_DISCORD_CLIENT_ID`). | Same id as 0.1.15 (D-02 parity). A Discord application id is public by design (it is broadcast in every presence payload). The env override is a local-operator affordance, equivalent in trust to editing the binary. The renderer contributes only `details`/`state`/`start_timestamp`, each type-narrowed in the main process. | `discord.ts:15-17` (env/const only) + payload narrowing at `discord.ts:56-60`. |

## Unregistered Flags

None. No `## Threat Flags` section appears in 04-01/02/03-SUMMARY.md, and no new attack surface was
found in the implementation that lacks a register entry: the delta over Phase 3 is exactly the 9 new
IPC channels (`window:minimize`, `window:toggle-maximize`, `window:close`, `window-prefs:get`,
`window-prefs:set`, `discord:set-activity`, `discord:clear-activity`, `autostart:get`,
`autostart:set`), one new outbound HTTP call (tray → local sidecar), one new fs write
(`window_prefs.json`), one new dependency, and one new OS integration (login item) — all eleven of
which map to a registered threat.

## Observations (hardening, not register gaps)

1. **`updateWindowPrefs` before `seedWindowPrefs` would write relative to the CWD.**
   `window-prefs.ts:60` initializes `cacheDir = ""`. `registerIpc` (index.ts:148) runs on
   `whenReady`, while `seedWindowPrefs` (index.ts:119) runs later inside `runStartup`, after the
   sidecar readiness gate. The splash window (`splash.ts:62-71`) loads the *same* hardened preload,
   so during that window a `window-prefs:set` invocation would resolve `join("", "window_prefs.json")`
   → `process.cwd()`.
   Not a T-04-04 failure: the path still comes from no renderer input, the filename is fixed, and
   there is no traversal. The splash is app-authored inline HTML from a `data:` URL with no remote
   content or user input, so no adversary can reach the call. Cheapest hardening if it is ever worth
   it: make `updateWindowPrefs` a no-op (or throw) while `cacheDir === ""`.

2. **Post-UAT drag-region fix (commit 234e576) has no security bearing — confirmed, not assumed.**
   `styles.css:213` puts `-webkit-app-region: drag` on `.titlebar` only (a 34px sticky bar) and
   `styles.css:215` puts `no-drag` on `.titlebar-buttons`. A drag region swallows mouse events, so
   the audit question was whether a `drag`/`no-drag` region could be used to swallow or hijack clicks
   on security-relevant UI. It cannot here: the drag region is scoped to the titlebar element itself
   (it does not overlay app content — `position: sticky` inside the normal flow, not a full-viewport
   layer), and the three window-control buttons sit inside the `no-drag` subtree, so they still
   receive clicks (`App.tsx` Titlebar → `native.minimizeWindow/toggleMaximizeWindow/closeWindow`).
   No security-relevant control is covered by a drag region. The commit's other half removed dead
   `data-tauri-drag-region` attributes — attribute deletion, no behavior change under Electron.

## Boundary Posture (unchanged, re-checked)

`index.ts:42-48` — `contextIsolation: true`, `nodeIntegration: false`, `sandbox: true`,
`webSecurity: true` on the main window; `splash.ts:62-71` applies the same webPreferences and the
same preload. Phase 4 added no privileged window and weakened no flag.

---

_Audited: 2026-07-11 · ASVS L1 · block_on: high_
