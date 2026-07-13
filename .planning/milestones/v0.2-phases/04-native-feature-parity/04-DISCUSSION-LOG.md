# Phase 4: Native feature parity - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-11
**Phase:** 4-native-feature-parity
**Areas discussed:** Discord RPC library, Frameless titlebar approach, Tray icon asset, Parity reference source

---

## Discord RPC library

| Option | Description | Selected |
|--------|-------------|----------|
| @xhayper/discord-rpc | Maintained TS fork; setActivity shape matches old crate; silent no-op when Discord absent | ✓ |
| discord-rpc (official) | Archived/unmaintained since ~2021 | |
| You research + pick | Defer lib to researcher, lock only behavior contract | |

**User's choice:** @xhayper/discord-rpc
**Notes:** Keep Client ID 1521045260342525962 + NYANKO_DISCORD_CLIENT_ID override; silent no-op preserves 0.1.15 ignore-on-error.

---

## Frameless titlebar approach

| Option | Description | Selected |
|--------|-------------|----------|
| Exact 0.1.15 parity | Reuse existing App.tsx/styles.css titlebar; rewire minimize/close to native.windowControls; frame:false; no UI-SPEC | ✓ |
| Restyle while migrating | Migrate + polish visuals; adds UI-SPEC and scope | |

**User's choice:** Exact 0.1.15 parity
**Notes:** Honors "paridad, no features". No visual redesign this phase.

---

## Tray icon asset

| Option | Description | Selected |
|--------|-------------|----------|
| One app icon for window+tray | Source/restore a single app icon; matches 0.1.15; feeds Phase 5 packaging | ✓ |
| Dedicated monochrome tray icon | Separate template tray icon; nicer but extra asset work, beyond parity | |

**User's choice:** Reuse one app icon for window+tray
**Notes:** No .ico currently in tree (src-tauri/icons deleted); restore from git history or brand asset.

---

## Parity reference source

| Option | Description | Selected |
|--------|-------------|----------|
| Deleted Rust in git history | git a50659c^ (window_prefs.rs/tray.rs/discord.rs/lib.rs) as authoritative behavioral spec | ✓ |
| Renderer calls only | Re-derive from native.* calls + criteria; risks missing edge behavior | |

**User's choice:** Deleted Rust in git history
**Notes:** Cited as canonical refs in CONTEXT.md so agents replicate exact behavior.

## Claude's Discretion

- Single-instance, autostart (--minimized), notifications, opener, folder-dialog implementation details — mirror old Rust lib.rs.
- IPC channel naming and main-process module organization.

## Deferred Ideas

- Titlebar visual restyle — 0.3+.
- Dedicated monochrome tray icon.
- Updater (checkForUpdates) — Phase 5 (PKG-02).
