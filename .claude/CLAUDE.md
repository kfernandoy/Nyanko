<!-- GSD:project-start source:PROJECT.md -->

## Project

**Nyanko**

Nyanko es una app de escritorio (Windows) para trackear anime/manga: sincroniza
con AniList/MAL/Kitsu, escanea biblioteca local, detecta reproducción en curso,
sugiere torrents y trae una extensión companion de navegador. Es una app
gratuita orientada a comunidad. Hoy el shell de escritorio es Tauri 2 (frontend
React/Vite + Rust) con un backend Python (FastAPI) empaquetado como sidecar.

**Core Value:** El tracking tiene que seguir funcionando idéntico después de cambiar el motor:
misma biblioteca, mismos datos, misma detección — solo cambia el shell de Tauri
a Electron.

### Constraints

- **Compatibility**: `userData` debe quedar en `%APPDATA%\app.nyanko.desktop`
  (identifier Tauri) o la biblioteca de prod existente queda huérfana.

- **Scope**: 0.2 es engine-swap puro — nada de features nuevas (regla dura por
  versión: 0.2.0 migración / 0.2.x fixes / 0.3.0+ features).

- **Tech stack**: electron-vite + electron-builder (NSIS) + electron-updater +
  TypeScript; sidecar Python PyInstaller onedir sin cambios.

- **Security**: `contextIsolation:true`, `nodeIntegration:false`, `sandbox:true`,
  `webSecurity:true` desde el día 1.

- **Platform**: Windows es el target primario (igual que hoy).

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
