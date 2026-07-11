# Phase 5: Packaging + auto-update - Pattern Map

**Mapped:** 2026-07-11
**Files analyzed:** 11 (3 new, 6 modified, 2 restored-from-history)
**Analogs found:** 9 / 11

## Blocking findings (read before planning)

1. **`EULA.txt` NO longer exists in the tree.** It was deleted with the Rust crate in
   `a50659c` (74 lines, ES + EN). D-03 requires it. It must be **restored from git history**:
   `git show a50659c^:apps/desktop/src-tauri/EULA.txt > apps/desktop/build/EULA.txt`.
   electron-builder expects it at `build/license_es.txt` / `build/license_en.txt` (per-language)
   or a single `nsis.license` path. Since the Tauri EULA is a single bilingual file, the lazy
   route is `nsis.license: build/EULA.txt` (one file, both languages inside — same content the
   user already accepted in 0.1.15).

2. **`build:icons` is BROKEN — CONTEXT.md is wrong that it is "reusable as-is".**
   `apps/desktop/scripts/generate-icons.mjs:10-23` reads `src-tauri/app-icon.svg` (deleted in
   `a50659c`) and shells out to `npm run tauri ... icon` (CLI gone). Same for the Python twin
   `scripts/generate_icons.py:11`. Running `npm run build:icons` today **fails**.
   The only live icon asset is `apps/desktop/build/icon.png` (verified **256×256**), which is
   exactly what electron-builder needs — it auto-derives `icon.ico` from a ≥256px PNG in
   `buildResources`. **Laziest fix: drop `build:icons` from the build chain entirely** (the SVG
   is recoverable from `a50659c^:apps/desktop/src-tauri/app-icon.svg` if regeneration is ever
   needed again). Do not "fix" the script for a one-off asset that is already committed.

3. **`electron-builder` and `electron-updater` are NOT installed.** No config file of any kind
   exists (`ls apps/desktop/electron-builder*` → empty). Both are net-new dependencies.

4. **`build:sidecar` works and produces exactly the D-07 layout** —
   `apps/backend/dist/nyanko-api/{nyanko-api.exe, _internal/}` (verified on disk). But
   `build_sidecar.py:84-98` *also* copies the exe + `_internal` into
   `apps/desktop/src-tauri/binaries/` (`binary_dir.mkdir(parents=True)` will **resurrect the
   deleted src-tauri directory**), and its `--icon` at line 81 points at the deleted
   `src-tauri/icons/icon.ico` — guarded by `if icon.exists()`, so it silently ships an
   exe with the default PyInstaller icon. Dead Tauri tail; safe to leave, cheap to delete.

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `apps/desktop/electron-builder.yml` (new) | config | batch/build | `a50659c^:apps/desktop/src-tauri/tauri.conf.json` §`bundle` | exact (spec) |
| `apps/desktop/build/installer.nsh` (new) | config/hook | event-driven | `a50659c^:apps/desktop/src-tauri/installer-hooks.nsh` | exact (spec) |
| `apps/desktop/build/EULA.txt` (restore) | asset | — | `a50659c^:apps/desktop/src-tauri/EULA.txt` | exact (restore verbatim) |
| `apps/desktop/electron/main/updater.ts` (new) | service | event-driven | `electron/main/sidecar.ts` (module shape) + `index.ts:157-167` (kill-before-quit) | role-match |
| `apps/desktop/electron/main/index.ts` (mod) | entrypoint | — | itself (`sidecar.ts:35-39` for icon resolution) | exact |
| `apps/desktop/electron/main/tray.ts` (mod) | provider | — | `sidecar.ts:35-39` | exact |
| `apps/desktop/package.json` (mod) | config | — | itself | exact |
| `package.json` (root, mod) | config | batch | itself (`build` script, line 15) | exact |
| `scripts/publish-bridge.mjs` (new, D-01) | utility | file-I/O + batch | **no in-tree analog** — procedural precedent: `docs/extra/RELEASING.md:41-58` | none |
| `docs/extra/RELEASING.md` (mod) | doc | — | itself | exact |
| `apps/backend/scripts/build_sidecar.py` (optional mod) | build script | file-I/O | itself | exact |

---

## Pattern Assignments

### `apps/desktop/electron-builder.yml` (config, new)

**Analog:** `a50659c^:apps/desktop/src-tauri/tauri.conf.json` — the authoritative spec for the
behavior being replicated. Quoted verbatim (planner cannot run git):

```json
{
  "productName": "Nyanko",
  "version": "0.1.15",
  "identifier": "app.nyanko.desktop",
  "plugins": {
    "updater": {
      "endpoints": [
        "https://github.com/kfernandoy/Nyanko/releases/latest/download/latest.json"
      ],
      "pubkey": "dW50cnVzdGVkIGNvbW1lbnQ6IG1pbmlzaWduIHB1YmxpYyBrZXk6IEJBQ0FCNjk0NzAyOEY2RDQKUldUVTlpaHdsTGJLdW9vN3A3MHVBaGtzNVloMlcrSnVOckNWbVQyVXRjV2N3c0JSdURYbVM4YUEK"
    }
  },
  "bundle": {
    "active": true,
    "targets": ["nsis"],
    "externalBin": ["binaries/nyanko-api"],
    "resources": {
      "binaries/_internal": "_internal",
      "../../extension/dist/chromium": "extension/chromium",
      "../../extension/dist/firefox": "extension/firefox"
    },
    "createUpdaterArtifacts": true,
    "licenseFile": "EULA.txt",
    "windows": {
      "nsis": {
        "languages": ["Spanish", "English"],
        "displayLanguageSelector": true,
        "installerHooks": "./installer-hooks.nsh"
      }
    },
    "icon": ["icons/32x32.png", "icons/128x128.png", "icons/128x128@2x.png", "icons/icon.ico", "icons/icon.icns"]
  }
}
```

**Field-by-field translation the new config must follow:**

| Tauri (spec) | electron-builder equivalent | Notes |
|---|---|---|
| `identifier: app.nyanko.desktop` | `appId: app.nyanko.desktop` | **Load-bearing** — same id as the Tauri build (DATA-01 / add-remove-programs identity). |
| `productName: Nyanko` | `productName: Nyanko` | Drives the install dir name. |
| `targets: ["nsis"]` | `win.target: nsis` | |
| `nsis.languages: [Spanish, English]` + `displayLanguageSelector` | `nsis.installerLanguages: [es_ES, en_US]` + `nsis.displayLanguageSelector: true` | D-03. Also set `nsis.multiLanguageInstaller: true`. |
| `licenseFile: EULA.txt` | `nsis.license: build/EULA.txt` | File must be restored first (see finding 1). |
| `installerHooks: ./installer-hooks.nsh` | `nsis.include: build/installer.nsh` | D-05. `include` is the macro-injection hook (not `script`, which *replaces* the whole installer). |
| (Tauri NSIS is per-user by default) | `nsis.oneClick: false` + `nsis.perMachine: false` + `nsis.allowToChangeInstallationDirectory: true` | D-03: assisted, per-user, no UAC. |
| `externalBin` + `resources[binaries/_internal]` | `extraResources` (see below) | D-06/D-07 — the shape changes, the destination does not. |
| `createUpdaterArtifacts: true` | `publish: {provider: github, owner: kfernandoy, repo: Nyanko}` | electron-builder emits `latest.yml` + SHA512 by construction (D-08). |
| `plugins.updater.endpoint/pubkey` | — | Dead for Electron. The minisign pubkey/endpoint live on ONLY inside the 0.1.15 binaries already in the field; the bridge script (D-01) feeds them one last `latest.json`. |

**`extraResources` (D-06/D-07) — the layout is dictated by `resolveSidecarExe()`, not chosen:**

```yaml
extraResources:
  - from: ../../apps/backend/dist/nyanko-api
    to: nyanko-api                          # → resources/nyanko-api/{nyanko-api.exe,_internal/}
  - from: ../../apps/extension/dist/chromium
    to: nyanko-api/extension/chromium       # NOT resources/extension/ — see main.py below
  - from: ../../apps/extension/dist/firefox
    to: nyanko-api/extension/firefox
  - from: build/icon.png
    to: icon.png                            # Claude's Discretion: packaged tray/window icon
```

(Paths are relative to the electron-builder project dir — `apps/desktop` — adjust if the config
is placed at the repo root instead.)

**Why `nyanko-api/extension/` and not `extension/`** — `apps/backend/nyanko_api/main.py:2910-2929`:

```python
@app.get("/api/extension/bundle")
def extension_bundle(...)-> dict[str, str | None]:
    if getattr(sys, "frozen", False):
        dist = Path(sys.executable).parent / "extension"
    else:
        dist = Path(__file__).resolve().parents[3] / "apps" / "extension" / "dist"
    return {
        name: str(dist / name) if (dist / name).is_dir() else None
        for name in ("chromium", "firefox")
    }
```

`sys.executable` is `resources/nyanko-api/nyanko-api.exe`, so `.parent / "extension"` is
`resources/nyanko-api/extension/`. Put the bundles anywhere else and the endpoint returns
`{"chromium": null, "firefox": null}` — the "open extension folder" button dies silently in prod.
The sidecar is not touched (0.2 = engine-swap only).

---

### `apps/desktop/build/installer.nsh` (config/hook, new)

**Analog:** `a50659c^:apps/desktop/src-tauri/installer-hooks.nsh` — **the entire file**, verbatim:

```nsis
; El sidecar nyanko-api.exe sobrevive al updater (es un proceso aparte que Tauri/NSIS
; no cierra) y mantiene bloqueados _internal\* y el propio exe → el copiado del
; instalador fallaba y había que matar el proceso a mano. Lo cerramos antes de instalar.
!macro NSIS_HOOK_PREINSTALL
  nsExec::Exec 'taskkill /F /IM nyanko-api.exe /T'
!macroend
```

**Convention the new file must follow:** electron-builder's include uses **different macro
names** than Tauri's. The preinstall equivalent is `customInit` / `preInit`, but the correct
hook for "kill the locking process before files are copied" is:

```nsis
!macro customInit
  nsExec::Exec 'taskkill /F /IM nyanko-api.exe /T'
!macroend
```

Keep the original comment (translated or as-is) — it explains *why* the hook exists, and that
rationale is the only thing preventing a future reader from deleting it as dead weight.

**D-02 (Tauri silent uninstall) goes in this same file, behind the empirical gate.** If the
verification proves `uninstall.exe /S` preserves `%APPDATA%\app.nyanko.desktop`, the hook adds a
`ReadRegStr` of Tauri's uninstall key + `ExecWait '"$R0" /S'`. If it proves otherwise, this file
stays exactly as above and the install-over path is configured in `electron-builder.yml`
(`nsis.guid` / install dir matching Tauri's) instead. **Do not write the uninstall branch before
the test runs** — losing a user's library is the worst outcome available in this phase.

---

### `apps/desktop/electron/main/updater.ts` (service, new)

**Analog A — module shape:** `apps/desktop/electron/main/sidecar.ts`. Every main-process module
in this codebase splits into *pure, Electron-free helpers* (unit-testable under plain Node) and
*thin wrappers* that touch Electron/IO. `sidecar.ts:5-12`:

```ts
// NATIVE-02: ciclo de vida del sidecar Python (nyanko-api.exe) en prod.
// Mismo split que compat-paths.ts: helpers PUROS (Electron-free) como exports
// nombrados para que sidecar.test.ts los ejerza bajo Node plano, y wrappers
// finos con spawn/taskkill/net (no testeados) aparte.

// ── Helpers puros (self-checkables) ──
```

An updater has almost no pure logic — so it is legitimately all "thin wrapper", no `.test.ts`
sibling. Do **not** invent a pure layer to satisfy the convention. (Contrast: `tray.ts` also has
no test, and says so explicitly at line 19: `// ponytail: ... sin test dedicado (YAGNI)`.)

**Analog B — the kill-before-quit contract:** `apps/desktop/electron/main/index.ts:155-167`.
This is the function the updater must *call*, not reimplement:

```ts
// D-08: matar el sidecar en cada salida antes de cerrar. Se difiere el quit hasta
// que killSidecar (graceful → taskkill /T /F del árbol) termine — si no, el loop
// muere antes del taskkill y queda un nyanko-api.exe huérfano. El updater de
// Phase 5 llama esta MISMA killSidecar antes de quitAndInstall.
let sidecarKilled = false;
app.on("before-quit", (e) => {
  isQuitting = true;
  if (sidecarKilled) return;
  e.preventDefault();
  sidecarKilled = true;
  void killSidecar().finally(() => app.quit());
});
```

`killSidecar()` is exported from `sidecar.ts:132` and is **idempotent** (`if (!proc || ... ) {
child = null; return; }`). Two viable wirings, in laziness order:

1. **Do nothing special.** `autoUpdater.quitAndInstall(true)` internally triggers `before-quit`,
   which already awaits `killSidecar()` before `app.quit()`. Verify this empirically — if the
   `e.preventDefault()` in `before-quit` interferes with electron-updater's own quit sequence,
   fall back to (2).
2. **Explicit await:** `await killSidecar(); autoUpdater.quitAndInstall(true);` — safe because
   `killSidecar()` is idempotent, so the `before-quit` path re-running it is a no-op.

Either way the NSIS `taskkill` hook stays: it covers orphans from a *crashed* app that
`killSidecar()` never got to reap. The two mechanisms are complementary (D-05).

**Analog C — deferred import of `logging`:** `sidecar.ts:83-87`:

```ts
// Import diferido: logging.ts carga electron/electron-log, que no existen bajo
// Node plano. Diferirlo mantiene los helpers puros importables por el self-check
// (sidecar.test.ts) sin bootear Electron; solo el spawn real (prod) lo necesita.
const { pipeSidecarOutput } = await import("./logging");
```

`electron-log` is already a dependency; `autoUpdater.logger = log` is the standard wiring. The
updater has no pure-helper self-check to protect, so a **top-level** `import` of `logging` is
fine here — the deferred-import dance is only needed by modules with Node-plain tests.

**Guard the dev path.** Same discriminator used everywhere in main (`isDevMode(app.isPackaged)`,
`sidecar.ts:23`): do not run `checkForUpdates()` when `!app.isPackaged` — electron-updater throws
without a packaged `app-update.yml`.

---

### `apps/desktop/electron/main/index.ts` + `tray.ts` (icon resolution fix)

**The two broken sites** — `index.ts:38-40`:

```ts
// D-07: icono de marca ÚNICO (build/icon.png 256x256) reutilizado por la bandeja
// (Plan 02) y el empaquetado de Fase 5. build/ vive fuera de out/main, de ahí ../../.
icon: join(__dirname, "../../build/icon.png"),
```

and `tray.ts:69`:

```ts
const icon = nativeImage.createFromPath(join(__dirname, "../../build/icon.png"));
```

Both resolve relative to `out/main/` → `apps/desktop/build/icon.png`. `build/` is
electron-builder's `buildResources` dir: **it is not copied into the asar**, so both paths are
dangling in the NSIS build (tray renders with no icon; no error, no log).

**Canonical analog — `sidecar.ts:33-39`.** Reuse this exact shape; do not invent a second
resolution mechanism:

```ts
// T-02-INJ: ruta ABSOLUTA del exe. Override explícito (NYANKO_SIDECAR_EXE) o el
// layout extraResources de Phase 5. Nunca un nombre PATH-resuelto.
export function resolveSidecarExe(): string {
  const override = process.env.NYANKO_SIDECAR_EXE;
  if (override) return override;
  return join(process.resourcesPath, "nyanko-api", "nyanko-api.exe");
}
```

The icon equivalent (with `extraResources` copying `build/icon.png` → `resources/icon.png`):

```ts
export function resolveIconPath(): string {
  return app.isPackaged
    ? join(process.resourcesPath, "icon.png")
    : join(__dirname, "../../build/icon.png");
}
```

**Where to put it:** both `index.ts` and `tray.ts` need it, so it must be a shared export.
`compat-paths.ts` is the existing "single source of truth for paths" module (its header, line 3:
*"Fuente única de verdad de rutas heredadas. ELECTRON-FREE a propósito"*) — but it is
deliberately Electron-free (its `.test.ts` runs under plain Node), and `app.isPackaged` breaks
that. Two acceptable options, planner picks one:
- Export `resolveIconPath()` from **`sidecar.ts`** next to `resolveSidecarExe()` — zero new files,
  but the module name lies slightly.
- Keep `compat-paths.ts` pure by adding a **pure** `iconPath(isPackaged, resourcesPath, dirname)`
  there and a one-line caller in each site — matches the existing pure/wrapper split exactly.

Note `sidecar.ts` uses `process.resourcesPath` **without** an `app.isPackaged` check because it
is only ever called on the prod path (`index.ts:109-116` gates it). The icon is needed on *both*
paths, hence the `app.isPackaged` branch. This is the deviation to be aware of.

---

### `apps/desktop/package.json` (config, modify)

**Current state** (lines 3-16): `"version": "0.1.15"`, `"main": "out/main/index.js"`, scripts
`dev`/`build`/`preview`/`check` + four `test:*` entries. No `build` block, no electron-builder,
no electron-updater in `devDependencies`/`dependencies`.

Changes:
- `"version": "0.2.0"` (strict semver — no `a`/`b`/`c` suffixes, they break the updater's parser).
- `dependencies`: `+ electron-updater` (runtime — must be *outside* the asar-excluded devDeps).
- `devDependencies`: `+ electron-builder`.
- Scripts: `"dist": "electron-vite build && electron-builder --publish always"` (or
  `--publish never` for local test builds). Keep `build` as the plain `electron-vite build`.
- `electron-builder.yml` sits next to this file (or point at it with `"build": {...}` inline —
  a separate `.yml` keeps `package.json` readable; either is idiomatic).

---

### `package.json` (root, modify)

**Current `build` chain** — line 15, still calls the removed Tauri CLI:

```json
"build": "npm run build:icons && npm run build:extension && npm run build:sidecar && npm run tauri --workspace @nyanko/desktop -- build",
```

with the reusable pieces at lines 11-13:

```json
"build:sidecar": "apps\\backend\\.venv\\Scripts\\python.exe apps/backend/scripts/build_sidecar.py",
"build:icons": "node apps/desktop/scripts/generate-icons.mjs",
"build:extension": "npm run build --workspace @nyanko/extension",
```

Rewire to:

```json
"build": "npm run build:extension && npm run build:sidecar && npm run dist --workspace @nyanko/desktop",
```

`build:icons` is **dropped** (finding 2 — it is broken and its output is already committed).
`build:extension` and `build:sidecar` are reused verbatim; both write to the exact directories
`extraResources` reads (`apps/extension/dist/{chromium,firefox}`,
`apps/backend/dist/nyanko-api/`). Note `dev:desktop` (line 10) also still says `npm run tauri`
— out of this phase's scope but it is the same dead-CLI class of bug; flag it, do not fix it
here unless free.

---

### `scripts/publish-bridge.mjs` (utility, new — **no in-tree analog**)

Nothing in the tree signs or publishes anything; the Tauri flow did it by hand. The closest
**procedural** precedent is `docs/extra/RELEASING.md:41-58`, which is the manual version of
exactly what this script automates:

```markdown
3. **Escribir `latest.json`** (la firma es el CONTENIDO del `.sig`, no una ruta):

   {
     "version": "x.y.z",
     "notes": "Resumen corto de los cambios.",
     "pub_date": "2026-07-05T00:00:00Z",
     "platforms": {
       "windows-x86_64": {
         "signature": "<contenido de Nyanko_x.y.z_x64-setup.exe.sig>",
         "url": "https://github.com/kfernandoy/Nyanko/releases/download/vx.y.z/Nyanko_x.y.z_x64-setup.exe"
       }
     }
   }
4. **Crear el release en GitHub** con tag `vx.y.z` y adjuntar: el `.exe`, el `.sig` y `latest.json`.
```

and the key/signing facts at `RELEASING.md:10-11, 23-27`:

```markdown
- Clave privada del updater: `C:\Users\kfern\.tauri\nyanko-updater.key` (sin contraseña).
```
```bash
# Git Bash (firma sin prompt: bash sí pasa la env var vacía)
export TAURI_SIGNING_PRIVATE_KEY="$USERPROFILE\\.tauri\\nyanko-updater.key" TAURI_SIGNING_PRIVATE_KEY_PASSWORD=""
```

**Contract of the bridge script (D-01, one-shot):** after `electron-builder --publish always`
has uploaded `Nyanko-Setup-0.2.0.exe` + `latest.yml` to the GitHub release:
1. minisign-sign the electron-builder NSIS `.exe` with the **same** key
   (`$USERPROFILE/.tauri/nyanko-updater.key`, empty password) → produces the `.sig` blob.
   The pubkey baked into every 0.1.15 binary in the field is the base64 above — the signature
   must verify against it or **every existing user is stranded forever**.
2. Emit `latest.json` in the Tauri schema above, with `signature` = the **contents** of the
   `.sig` file (not a path) and `url` = the electron-builder asset's download URL.
3. Upload `latest.json` (+ the `.sig`) to the same release. Plain `fetch` against the GitHub
   API with `GH_TOKEN` — the `gh` CLI is **not installed** (D-08).

Signing tooling: the Tauri CLI is gone, so `npx tauri signer sign` is no longer available. Use
the `minisign` binary directly, or the pure-JS `@tauri-apps/cli` signer if it can be invoked
without the Rust toolchain — **verify the produced `.sig` against the embedded pubkey before
publishing**, e.g. `minisign -V -P <pubkey> -m Nyanko-Setup-0.2.0.exe`. This is not optional:
a bad signature is indistinguishable from a good one until it silently fails on every client.

Language convention for the script + release notes: **English** (repo convention since
2026-07-06); code comments stay in Spanish.

---

### `apps/backend/scripts/build_sidecar.py` (optional cleanup)

`build_sidecar.py:78-98` still targets Tauri. Lines 80-83:

```python
    if platform.system() == "Windows":
        command.append("--noconsole")
        icon = desktop_root / "src-tauri" / "icons" / "icon.ico"
        if icon.exists():
            command.extend(["--icon", str(icon)])
```

and lines 94-98:

```python
    shutil.copy2(built, output_file)          # → desktop/src-tauri/binaries/nyanko-api-x86_64-pc-windows-msvc.exe
    internal_dir = bundle_dir / "_internal"
    output_internal_dir = binary_dir / "_internal"
    ...
    shutil.copytree(internal_dir, output_internal_dir)
```

`binary_dir` is `apps/desktop/src-tauri/binaries` and is `mkdir(parents=True)`-ed at line 30 —
so every sidecar build **recreates the deleted `src-tauri/` directory**. The PyInstaller output
that `extraResources` actually consumes (`apps/backend/dist/nyanko-api/`) is produced *before*
this copy and is unaffected. Deleting the `rust_target_triple()` helper, `binary_dir`, and the
copy tail is a pure-subtraction diff. Low priority; do it only if the phase touches this file.

---

## Shared Patterns

### Prod/dev discrimination
**Source:** `apps/desktop/electron/main/sidecar.ts:21-25`
**Apply to:** updater gating, icon resolution
```ts
// D-10: dev = !app.isPackaged. Booleano puro para que el self-check lo maneje
// sin Electron. En dev el spawn se omite (backend a mano) — decisión en index.ts.
export function isDevMode(isPackaged: boolean): boolean {
  return !isPackaged;
}
```
With the escape hatch documented at `index.ts:105-109`: an env var override forces the prod path
under `electron-vite preview` (where `app.isPackaged` is `false`). If the updater needs the same
treatment for testing, follow that shape (`NYANKO_*` env var), not a new flag system.

### Resource resolution under packaging
**Source:** `apps/desktop/electron/main/sidecar.ts:35-39` (quoted in full above)
**Apply to:** icon (index.ts, tray.ts), any future packaged asset
`process.resourcesPath` + `join()`, absolute always, never a relative/PATH-resolved name.

### Comments explain WHY, in Spanish, keyed to decision IDs
**Source:** every main-process file — e.g. `index.ts:19-21`, `sidecar.ts:128-131`,
`installer-hooks.nsh` (the whole comment header is the rationale)
**Apply to:** all new files. Each non-obvious line cites the decision it implements (`D-05:`,
`DATA-01:`, `T-02-INJ:`). New code should cite this phase's D-01…D-08. Deliberate
simplifications get a `ponytail:` comment (`tray.ts:19-20`).

### One runnable check for non-trivial logic
**Source:** `sidecar.test.ts` / `compat-paths.test.ts`, run via
`node --import tsx --test electron/main/<x>.test.ts` (`apps/desktop/package.json:12-15`)
**Apply to:** only if a new *pure* helper appears (e.g. a `latest.json` builder in the bridge
script — that one is worth an assert). The updater wrapper and the `.nsh` have no pure logic to
test; their check is the empirical D-02 install test and a real NSIS run.

---

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `scripts/publish-bridge.mjs` | utility | file-I/O + batch | Nothing in the repo signs or uploads anything — the Tauri release was 100% manual. Closest precedent is the *procedure* in `docs/extra/RELEASING.md:41-58`, quoted above. |
| `apps/desktop/build/installer.nsh` (D-02 uninstall branch only) | config/hook | event-driven | The `taskkill` half has an exact analog; the Tauri-uninstall half has none and **must not be written before the empirical `%APPDATA%` test** (D-02). |

---

## Metadata

**Analog search scope:** `apps/desktop/electron/main/`, `apps/desktop/scripts/`,
`apps/backend/scripts/`, `apps/backend/nyanko_api/main.py`, root + desktop `package.json`,
`docs/extra/RELEASING.md`, and git history at `a50659c^` (`src-tauri/tauri.conf.json`,
`installer-hooks.nsh`, `EULA.txt`, `app-icon.svg`).
**Files scanned:** 14
**Pattern extraction date:** 2026-07-11
