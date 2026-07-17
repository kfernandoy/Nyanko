<!-- GSD:project-start source:PROJECT.md -->

## Project

**Nyanko**

Nyanko es una app de escritorio (Windows) para trackear anime/manga: sincroniza
con AniList/MAL/Kitsu, escanea biblioteca local, detecta reproducción en curso,
sugiere torrents y trae una extensión companion de navegador. Es una app
gratuita orientada a comunidad. El shell de escritorio es Electron
(electron-vite: main + preload + renderer React/Vite) con un backend Python
(FastAPI) empaquetado como sidecar PyInstaller.

**Core Value:** Nyanko deja de ser solo un tracker y pasa a ser **donde
consumes**: el manga se lee dentro de la app, y el tracking ocurre solo — el
mismo trato que la detección de reproducción ya le da al anime.

### Constraints

- **Compatibility**: `userData` debe quedar en `%APPDATA%\app.nyanko.desktop`
  (identifier Tauri) o la biblioteca de prod existente queda huérfana. Hay un
  assert que crashea el arranque si se rompe.

- **Versionado**: el updater exige **semver estricto** — nada de sufijos
  `a`/`b`/`c`; los parches van `0.2.N`. Regla por versión: 0.2.x fixes /
  0.3.0+ features.

- **Tech stack**: electron-vite + electron-builder (NSIS) + electron-updater +
  TypeScript; sidecar Python PyInstaller onedir.

- **Security**: `contextIsolation:true`, `nodeIntegration:false`, `sandbox:true`,
  `webSecurity:true`.

- **Platform**: Windows es el target primario.

<!-- GSD:project-end -->

<!-- GSD:stack-start source:STACK.md -->

## Technology Stack

Technology stack not yet documented. Will populate after codebase mapping or first phase.
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->

## Conventions

Conventions not yet established. Will populate as patterns emerge during development.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->

## Architecture

Architecture not yet mapped. Follow existing patterns found in the codebase.
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->

## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, `.github/skills/`, or `.codex/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->

## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:

- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->

<!-- GSD:profile-start -->

## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
