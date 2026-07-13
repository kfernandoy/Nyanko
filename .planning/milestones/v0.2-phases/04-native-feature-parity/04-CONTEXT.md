# Phase 4: Native feature parity - Context

**Gathered:** 2026-07-11
**Status:** Ready for planning

<domain>
## Phase Boundary

Fill the 10 Phase-4 stubs left on the `apps/desktop/src/native.ts` boundary with real
Electron implementations so the native features Tauri provided work identically to
0.1.15 (NATIVE-03/04/05/06): system tray + menu, window preferences + frameless
titlebar, Discord Rich Presence, and single-instance / autostart / notifications /
opener / folder-dialog.

**Principle: paridad, no features.** Every behavior mirrors 0.1.15 — this is an
engine-swap, not a redesign. The updater stub (`native.checkForUpdates`) is OUT of scope
(Phase 5, PKG-02). No renderer UI redesign.

</domain>

<decisions>
## Implementation Decisions

### Discord Rich Presence (NATIVE-05)
- **D-01:** Use the `@xhayper/discord-rpc` Node library (actively-maintained TypeScript
  fork) for RPC. Not the archived official `discord-rpc`.
- **D-02:** Keep the exact behavior contract from the old Rust `discord.rs`: default
  Client ID `1521045260342525962`, overridable via the `NYANKO_DISCORD_CLIENT_ID`
  env var; `setActivity` carries `details`, `state`, and optional `start_timestamp`
  (Timestamps). Connecting is lazy (on first setActivity).
- **D-03:** Silent no-op when Discord isn't running or the client isn't configured —
  a failed local-IPC connect is caught and swallowed (matches 0.1.15 ignore-on-error).
  The existing renderer `discord.ts` re-export and App.tsx signature/timestamp logic
  stay unchanged; only `native.setDiscordActivity`/`clearDiscordActivity` gain real bodies.

### Frameless titlebar + window prefs (NATIVE-04)
- **D-04:** Exact 0.1.15 parity for the titlebar. Reuse the existing React titlebar in
  `App.tsx` + `styles.css` (already uses `-webkit-app-region`) as-is — no visual
  redesign, no UI-SPEC. Only rewire minimize/close to `native.windowControls` (IPC) and
  set `frame: false` on the main BrowserWindow.
- **D-05:** `window_prefs.json` compatibility is fixed by the old Rust `window_prefs.rs`:
  file lives in the app data dir (`%APPDATA%\app.nyanko.desktop\window_prefs.json`),
  schema `{ close_to_tray, minimize_to_tray, start_minimized }` (all default `false`) —
  already matches the `WindowPrefs` type in `native.ts`. Existing prod prefs must load
  without migration. These three prefs govern close→tray, minimize→tray, and
  start-minimized behavior exactly as 0.1.15 did.

### System tray (NATIVE-03)
- **D-06:** Tray menu labels are fixed by the roadmap criteria: Mostrar / Ocultar /
  Pausar-Reanudar detección / Salir. Double-click shows the window. The detection toggle
  does POST to `/api/detection/{pause,resume}` (mirror the old `tray.rs`). The
  pause/resume label reflects current detection state.

### Icon asset
- **D-07:** Use a single app icon for both the main window and the Tray (0.1.15 used the
  app icon for the tray). No `.ico` currently exists in the tree (the `src-tauri/icons/`
  were deleted with the crate) — restore/source one app icon (recover from git history
  `apps/desktop/src-tauri/icons/` at `a50659c^` if present there, or the brand asset).
  This same icon feeds Phase 5 packaging. No dedicated monochrome tray icon.

### Parity reference
- **D-08:** The deleted Rust in git history is the authoritative behavioral spec for
  exact 0.1.15 parity. Downstream agents MUST consult it (see Canonical References) rather
  than re-deriving behavior from renderer calls alone — it carries edge behavior
  (start-minimized timing, tray double-click, close/minimize interception) not obvious
  from the renderer.

### Claude's Discretion
- Single-instance (`app.requestSingleInstanceLock` → focus live window), autostart
  (`app.setLoginItemSettings` with `--minimized` arg), notifications (Electron
  `Notification` / HTML5), opener (`shell.openExternal`/`openPath` — already wired in
  Phase 3), and folder dialog (`dialog.showOpenDialog` — already wired) implementation
  details are Claude's discretion, mirroring the old Rust `lib.rs` behavior.
- IPC channel naming, main-process module organization, and how tray/window state is
  wired to the existing `ipc.ts` registry are Claude's discretion.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Parity source of truth (deleted Rust — read via git)
- `git show a50659c^:apps/desktop/src-tauri/src/window_prefs.rs` — window-prefs schema, file
  path (app_data_dir/window_prefs.json), load/save, and default (all false).
- `git show a50659c^:apps/desktop/src-tauri/src/tray.rs` — tray menu structure, labels,
  double-click behavior, detection pause/resume POST wiring.
- `git show a50659c^:apps/desktop/src-tauri/src/discord.rs` — Discord Client ID
  `1521045260342525962`, `NYANKO_DISCORD_CLIENT_ID` override, activity shape, lazy
  connect, silent no-op on failure.
- `git show a50659c^:apps/desktop/src-tauri/src/lib.rs` — single-instance, autostart
  (`--minimized`), notifications, opener, dialog, window close/minimize interception,
  start-minimized wiring.
- `git show a50659c^:apps/desktop/src-tauri/src/main.rs` — app bootstrap order.
- `git show a50659c^:apps/desktop/src-tauri/tauri.conf.json` — window config (frameless,
  size, min-size, decorations) and icon references to replicate on the Electron BrowserWindow.

### This-repo boundary + constraints
- `apps/desktop/src/native.ts` — the 10 Phase-4 stubs to fill (`ponytail:`-tagged); keep
  `NATIVE_OPS` in sync so `npm run test:native` stays honest.
- `apps/desktop/electron/main/ipc.ts` + `apps/desktop/electron/preload/index.ts` — the
  existing `ipcMain.handle` registry and `window.nyanko` bridge to EXTEND (do not rewrite).
- `apps/desktop/electron/main/index.ts` — BrowserWindow creation; set `frame:false`; do NOT
  weaken `contextIsolation:true`/`nodeIntegration:false`/`sandbox:true`/`webSecurity:true`.
- `.planning/REQUIREMENTS.md` — NATIVE-03/04/05/06 (this phase) + DATA-01 (userData path
  compat, already established).
- `.claude/CLAUDE.md` — constraints: userData=`%APPDATA%\app.nyanko.desktop`, paridad-only
  scope, Windows target, Spanish code convention.
- `docs/specs/2026-07-09-tauri-to-electron-migration-design.md` — overall migration design.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `apps/desktop/src/native.ts`: single native boundary from Phase 3 — 8 ops wired, 10
  stubs to fill this phase. `WindowPrefs` / `DiscordActivity` types already declared.
- `apps/desktop/src/windowPrefs.ts` + `discord.ts`: thin re-exports over `native.*` —
  they need no change; only the underlying `native` stubs gain real bodies.
- Existing frameless titlebar in `App.tsx` + `styles.css` (`-webkit-app-region`) — reuse verbatim.
- `apps/desktop/electron/main/ipc.ts`: `ipcMain.handle` registrar from Phase 2 to extend.

### Established Patterns
- Every native op routes renderer → `native.ts` → `window.nyanko` (contextBridge) →
  `ipcMain.handle`. New tray/window/discord/autostart ops follow the same path; keep the
  bridge to specific typed methods (no raw `ipcRenderer`).
- Self-check `native.test.ts` asserts `native` ↔ `NATIVE_OPS` symmetry — every newly-wired
  op must stay listed in `NATIVE_OPS`.

### Integration Points
- Tray detection toggle → backend `POST /api/detection/{pause,resume}` (same sidecar the
  app already talks to).
- Window prefs read/write → `%APPDATA%\app.nyanko.desktop\window_prefs.json`.
- Discord RPC → local Discord IPC socket via `@xhayper/discord-rpc`.

</code_context>

<specifics>
## Specific Ideas

- Discord Client ID `1521045260342525962`, env override `NYANKO_DISCORD_CLIENT_ID`.
- Autostart launch argument: `--minimized`.
- Tray menu (Spanish): Mostrar / Ocultar / Pausar detección ↔ Reanudar detección / Salir.

</specifics>

<deferred>
## Deferred Ideas

- Titlebar visual restyle/polish — belongs in 0.3+ (features), not this parity phase.
- Dedicated monochrome/template tray icon — deferred; reusing the app icon for now.
- Updater (`native.checkForUpdates`) — Phase 5 (PKG-02), remains a stub this phase.

</deferred>

---

*Phase: 4-native-feature-parity*
*Context gathered: 2026-07-11*
