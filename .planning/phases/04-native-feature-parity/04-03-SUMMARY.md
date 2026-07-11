---
phase: 04-native-feature-parity
plan: 03
subsystem: desktop-shell
tags: [electron, native, discord-rpc, single-instance, autostart, ipc]
requires:
  - "native.ts boundary + NATIVE_OPS self-check (Phase 3)"
  - "ipc.ts registerIpc registry + preload nyanko bridge (Phase 2/3)"
  - "mainWindow module ref + --minimized ready-to-show handling (Plan 02)"
provides:
  - "Discord Rich Presence set/clear (lazy connect, silent no-op when Discord is closed)"
  - "discord:set-activity / discord:clear-activity IPC channels"
  - "autostart:get / autostart:set IPC channels (login item with --minimized)"
  - "single-instance lock + second-instance focus of the live window"
  - "nyanko bridge methods setDiscordActivity/clearDiscordActivity/getAutostart/setAutostart"
  - "zero remaining Phase-4 stubs on the native boundary"
affects:
  - apps/desktop/electron/main/discord.ts
  - apps/desktop/electron/main/index.ts
  - apps/desktop/electron/main/ipc.ts
  - apps/desktop/electron/preload/index.ts
  - apps/desktop/src/native.ts
  - apps/desktop/src/vite-env.d.ts
  - apps/desktop/package.json
tech-stack:
  added:
    - "@xhayper/discord-rpc@1.3.4 (human-approved supply-chain gate T-04-SC)"
  patterns:
    - "module-level lazily-connected client slot (Electron analog of Rust Mutex<Option<DiscordIpcClient>>)"
    - "connect+setActivity wrapped in try/catch, drop client on error so the next call reconnects"
    - "single-instance: requestSingleInstanceLock + one second-instance focus handler (no custom IPC broker)"
    - "autostart via native app.setLoginItemSettings — no autostart library"
key-files:
  created:
    - apps/desktop/electron/main/discord.ts
  modified:
    - apps/desktop/electron/main/index.ts
    - apps/desktop/electron/main/ipc.ts
    - apps/desktop/electron/preload/index.ts
    - apps/desktop/src/native.ts
    - apps/desktop/src/vite-env.d.ts
    - apps/desktop/package.json
decisions:
  - "T-04-SC gate: user verified @xhayper/discord-rpc on npmjs.com and answered 'approved' before install; installed at exactly that scope/spelling (1.3.4)"
  - "D-02/D-03 parity: client id 1521045260342525962 with NYANKO_DISCORD_CLIENT_ID override, UNCONFIGURED sentinel kept, lazy connect, silent swallow, drop-on-error"
  - "Added a no-op 'error' listener on the RPC client: an unhandled EventEmitter 'error' when Discord closes mid-session would crash the main process (T-04-08 hardening beyond the Rust original)"
  - "@xhayper/discord-rpc stays externalized by electron-vite (same path as electron-log) — no bundling change, no config touched"
  - "second-instance uses show() + restore() + focus() (Electron equivalent of the Rust show/unminimize/set_focus)"
metrics:
  duration: ~18m
  completed: 2026-07-11
status: complete
---

# Phase 4 Plan 03: Discord Rich Presence + Single-Instance + Autostart Summary

Delivered NATIVE-05 (Discord Rich Presence that connects lazily and is a silent no-op when Discord is closed) and NATIVE-06 (single-instance focus, autostart registered with `--minimized`, plus verification that the Phase-3 notifications/opener/dialog handlers are intact) — closing the last Phase-4 stubs on the `native.ts` boundary.

## Checkpoint Resolved

**Task 0 — T-04-SC package-legitimacy gate (blocking-human): APPROVED by the user.**
The user verified `@xhayper/discord-rpc` on npmjs.com (correct `@xhayper` scope, a Discord RPC client, actively maintained, not a typosquat of the archived `discord-rpc`), confirmed the exact spelling, and answered **"approved"**. Only then was the package installed — resolving as `@xhayper/discord-rpc@1.3.4` with the exact approved scope/spelling. No code was written before the approval.

## What Was Built

**Task 1 — Discord Rich Presence (commit a011bf1)**
- `electron/main/discord.ts`: module-level lazily-created client slot (the Electron analog of the Rust `Mutex<Option<DiscordIpcClient>>`). Client id = `process.env.NYANKO_DISCORD_CLIENT_ID || "1521045260342525962"`, keeping the `REPLACE_WITH_YOUR_DISCORD_CLIENT_ID` sentinel from `discord.rs` (unconfigured → no-op).
- `setDiscordActivity`: connects on first call; sets `details`/`state` only when non-empty (Discord rejects empty strings) and `startTimestamp` only when supplied. Connect + `setActivity` are wrapped in try/catch and **swallowed silently** (D-03); on a set failure the client is dropped so the next call reconnects — exactly `*slot = None` in the Rust.
- `clearDiscordActivity`: clears presence only if a client exists, ignoring errors.
- IPC: `discord:set-activity` / `discord:clear-activity`. Preload: named typed `setDiscordActivity`/`clearDiscordActivity` bridge methods (T-04-10 — never raw `ipcRenderer`).
- `native.ts` bodies filled with the wired-op + web-fallback no-op pattern. `NATIVE_OPS` unchanged; `App.tsx`/`discord.ts` renderer re-exports untouched.
- The renderer payload is coerced in the main process (`details`/`state` to strings, `start_timestamp` to number) — the client id never comes from the renderer (T-04-09).

**Task 2 — Single-instance + autostart + Phase-3 verification (commit b886367)**
- `index.ts`: `app.requestSingleInstanceLock()` before `whenReady`. The loser quits immediately; the live instance handles `second-instance` with `show()` + `restore()` (if minimized) + `focus()` — the Electron equivalent of the Rust `show/unminimize/set_focus`, which also rescues the window from the tray.
- `ipc.ts`: `autostart:get` → `app.getLoginItemSettings().openAtLogin`; `autostart:set` → `app.setLoginItemSettings({ openAtLogin: Boolean(enabled), args: ["--minimized"] })`. The `--minimized` flag is already consumed by the Plan-02 `ready-to-show` path (window starts hidden in the tray).
- Preload: named typed `getAutostart`/`setAutostart`. `native.ts` bodies filled — **no Phase-4 stub remains** (only `checkForUpdates`, Phase 5, still throws).
- **Verified (not rebuilt)** that the Phase-3 handlers are intact and their validation is not weakened: `openExternal` still enforces `^https?://`, `openPath`/`revealItemInDir` still reject any `://` scheme, `openFolderDialog` and `notify` unchanged. The task's diff on `ipc.ts` is 9 lines, **all additions** — mechanically proving nothing in the Phase-3 block was altered.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical functionality] No-op `error` listener on the RPC client**
- **Found during:** Task 1
- **Issue:** `@xhayper/discord-rpc`'s `Client` is an `EventEmitter`. If Discord closes mid-session, the transport emits `error`; an `error` event with no listener **throws and crashes the Electron main process**. The Rust original had no equivalent hazard (no EventEmitter semantics), so mirroring it 1:1 would have left a crash path that directly violates the plan's own must-have ("when Discord is not running, set/clear activity is a silent no-op — no crash") and threat T-04-08.
- **Fix:** `c.on("error", () => {})` attached at construction, before `login()`.
- **Files modified:** apps/desktop/electron/main/discord.ts
- **Commit:** a011bf1

**2. [Rule 3 - Blocking] Bridge types added to `vite-env.d.ts`**
- **Found during:** Tasks 1 and 2
- **Issue:** `vite-env.d.ts` is the canonical `window.nyanko` type declaration; routing the native bodies through it fails `tsc --noEmit` unless the four new methods are declared. Same deviation Plan 01 recorded — the plan's `files_modified` list omits this file both times.
- **Fix:** Added `setDiscordActivity`/`clearDiscordActivity`/`getAutostart`/`setAutostart` to the `Window.nyanko` interface.
- **Files modified:** apps/desktop/src/vite-env.d.ts
- **Commits:** a011bf1, b886367

### Notes (no deviation)

- `@xhayper/discord-rpc` is left **externalized** by electron-vite (the main bundle emits `import { Client } from "@xhayper/discord-rpc"`), exactly like the existing `electron-log` dependency. No bundling/config change was needed, and Phase-5 packaging already has to ship hoisted production deps for `electron-log`, so this adds no new packaging surface.
- No architectural changes; no auth gates.

## Verification Results

- `npm run test:native` → 2 pass / 0 fail (`NATIVE_OPS` ↔ `native` symmetry intact; `NATIVE_OPS` unchanged).
- `npm run test:prefs` → 4 pass / 0 fail (Plan-02 suite still green).
- `npm run check` (tsc --noEmit) → exit 0.
- `npm run build` (electron-vite, **with Discord closed**) → exit 0 — proving there is no top-level connect that could crash.
- Acceptance greps: `@xhayper/discord-rpc` in package.json = 1 (installed, 1.3.4); client id / env override in `discord.ts` = 2; `discord:*` in preload = 2; `requestSingleInstanceLock|second-instance` in index.ts = 3; `autostart:*` in ipc.ts = 2 with `setLoginItemSettings` + `--minimized` present; `getAutostart|setAutostart` in preload = 2; **`throw new Error` in native.ts = 1** (only the Phase-5 updater stub).
- `openExternal` `^https?://` guard confirmed present at ipc.ts:42; `ipc.ts` diff for Task 2 = 9 insertions, 0 deletions.

Manual verification is carried to phase verify (needs a running session): Discord open → presence appears; Discord closed → no crash; second launch → the live window focuses; toggle autostart → login item registered with `--minimized`.

## Known Stubs

None introduced. Every Phase-4 native op is now real. `native.checkForUpdates` remains an intentional throw-stub (Phase 5, PKG-02) — out of scope.

## Self-Check: PASSED

- FOUND: apps/desktop/electron/main/discord.ts
- FOUND: @xhayper/discord-rpc@1.3.4 in apps/desktop/package.json + node_modules
- FOUND commit: a011bf1 (Task 1 — Discord Rich Presence)
- FOUND commit: b886367 (Task 2 — single-instance + autostart)
