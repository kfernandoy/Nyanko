# Nyanko

## What This Is

Nyanko es una app de escritorio (Windows) para trackear anime/manga: sincroniza
con AniList/MAL/Kitsu, escanea biblioteca local, detecta reproducción en curso,
sugiere torrents y trae una extensión companion de navegador. Es una app
gratuita orientada a comunidad. Hoy el shell de escritorio es Tauri 2 (frontend
React/Vite + Rust) con un backend Python (FastAPI) empaquetado como sidecar.

## Core Value

El tracking tiene que seguir funcionando idéntico después de cambiar el motor:
misma biblioteca, mismos datos, misma detección — solo cambia el shell de Tauri
a Electron.

## Requirements

### Validated

<!-- Ya envriado y en uso en 0.1.15 (Tauri). No se re-implementa; se preserva. -->

- ✓ Tracking multi-proveedor (AniList/MAL/Kitsu) — 0.1.x
- ✓ Escaneo de biblioteca local + asociación de series — 0.1.x
- ✓ Detección de reproducción + confirmación/undo — 0.1.x
- ✓ Feed de torrents con matching contra biblioteca — 0.1.x (0.1.14/0.1.15)
- ✓ Extensión companion (Chromium/Firefox) — 0.1.x
- ✓ Backend Python FastAPI empaquetado como sidecar (PyInstaller onedir) — 0.1.x
- ✓ Auto-update firmado + instalador NSIS (ES/EN) — 0.1.x (vía Tauri)

### Active

<!-- Milestone 0.2: engine-swap Tauri → Electron. Diseño en
docs/specs/2026-07-09-tauri-to-electron-migration-design.md -->

- [ ] `apps/desktop` corre como app electron-vite (main/preload/renderer)
- [ ] Frontera nativa única (`src/native.ts`) reemplaza todos los `@tauri-apps/*`
- [ ] Sidecar Python lanzado/gestionado desde el main de Electron
- [ ] Paridad de features nativas: tray, window prefs, Discord RPC,
      single-instance, autostart, notificaciones, dialog, opener
- [ ] Data dir compatible (`%APPDATA%\app.nyanko.desktop`) con assert de arranque
- [ ] Empaquetado electron-builder NSIS + auto-update electron-updater
- [ ] Logging/diagnóstico (electron-log) desde la primera versión Electron

### Out of Scope

<!-- Diferido a 0.3+ para mantener la 0.2 como migración pura. -->

- Firma pública externa + página "Verify" (minisign/cosign) — integridad ya
  cubierta por SHA512 de electron-updater; confianza comunitaria es 0.3
- Rediseño de la pantalla de extensión (descargas/guía/estado) — 0.2 preserva el
  flujo actual
- Adapters comunitarios con API versionada — 0.3+
- Navegador embebido / webviews para sitios externos — 0.3+
- Code-signing del instalador Windows — se agrega después
- Migrar el backend Python a Node — el sidecar existe y funciona; solo cambia el
  shell

## Context

- Monorepo `apps/{backend,desktop,extension}`. Solo `apps/desktop` (el shell)
  cambia; backend, extension y el renderer React quedan intactos salvo la capa
  `@tauri-apps/*`.
- `src-tauri/` ya fue borrado del árbol; su contenido vive en el backup
  `nyanko-pre-electron-backup-20260709.tar.gz` y en git, usado solo como
  referencia para replicar comportamiento (446 líneas de Rust: sidecar, tray,
  discord, window_prefs).
- Distribución efectiva: un solo usuario (el autor). No se necesita puente de
  auto-update Tauri→Electron ni compat con usuarios externos.
- Historial de bugs relevante: arranque lento por readiness del sidecar/puerto y
  data dir divergente — por eso el gate de readiness y el data dir fijo son
  críticos en la migración.

## Constraints

- **Compatibility**: `userData` debe quedar en `%APPDATA%\app.nyanko.desktop`
  (identifier Tauri) o la biblioteca de prod existente queda huérfana.
- **Scope**: 0.2 es engine-swap puro — nada de features nuevas (regla dura por
  versión: 0.2.0 migración / 0.2.x fixes / 0.3.0+ features).
- **Tech stack**: electron-vite + electron-builder (NSIS) + electron-updater +
  TypeScript; sidecar Python PyInstaller onedir sin cambios.
- **Security**: `contextIsolation:true`, `nodeIntegration:false`, `sandbox:true`,
  `webSecurity:true` desde el día 1.
- **Platform**: Windows es el target primario (igual que hoy).

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Electron sobre seguir en Tauri | Ecosistema desktop maduro (plugins, adapters, comunidad) para la expansión long-term del companion | — Pending |
| electron-vite (no Electron a mano) | HMR main/preload/renderer + integración builder sin glue artesanal | — Pending |
| Mantener backend Python como sidecar | Ya existe y funciona; migrarlo a Node sería reescritura innecesaria | — Pending |
| `src/native.ts` como frontera única | Aísla la superficie nativa; clave para adapters/tray/updater futuros | — Pending |
| userData fijo a `app.nyanko.desktop` | Preserva la biblioteca existente sin migración | — Pending |
| Diferir firma pública / UI extensión / adapters a 0.3 | Mantener 0.2 aburrida y estable | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-07-10 after initialization*
