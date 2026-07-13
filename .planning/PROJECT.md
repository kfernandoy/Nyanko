# Nyanko

## What This Is

Nyanko es una app de escritorio (Windows) para trackear anime/manga: sincroniza
con AniList/MAL/Kitsu, escanea biblioteca local, detecta reproducción en curso,
sugiere torrents y trae una extensión companion de navegador. Es una app
gratuita orientada a comunidad. El shell de escritorio es **Electron**
(electron-vite: main + preload + renderer React/Vite) con un backend Python
(FastAPI) empaquetado como sidecar PyInstaller.

## Current State

**Shipped: v0.2 (2026-07-13)** — engine-swap Tauri → Electron, completo y verificado.
Canal vivo: **v0.2.3** en GitHub Releases (auto-update por electron-updater; los usuarios
0.1.15 llegan por el puente minisign/`latest.json`).

- 5 fases, 15 planes, 12/12 requisitos, audit de milestone `passed`.
- El auto-update y la migración desde Tauri se probaron **sobre instalaciones reales**, no por
  inspección de código.
- Deuda abierta a 0.3: W-3 (tray ↔ UI unidireccional), D-I-03 (rate limit de AniList a 90 cuando
  AniList dice 30), `docs/extra/RELEASING.md` sin trackear.

## Core Value

El tracking funciona **idéntico** después de cambiar el motor: misma biblioteca, mismos datos, misma
detección. Ese era el core value de 0.2 y **se cumplió**.

> ⚠️ Para 0.3 hay que redefinirlo: el core value actual es de migración, no de producto. Lo decide
> `/gsd-new-milestone` antes de planificar nada.

## Requirements

### Validated

<!-- 0.1.x — ya enviado y en uso. No se re-implementa; se preserva. -->

- ✓ Tracking multi-proveedor (AniList/MAL/Kitsu) — 0.1.x
- ✓ Escaneo de biblioteca local + asociación de series — 0.1.x
- ✓ Detección de reproducción + confirmación/undo — 0.1.x
- ✓ Feed de torrents con matching contra biblioteca — 0.1.x (0.1.14/0.1.15)
- ✓ Extensión companion (Chromium/Firefox) — 0.1.x
- ✓ Backend Python FastAPI empaquetado como sidecar (PyInstaller onedir) — 0.1.x
- ✓ Auto-update firmado + instalador NSIS (ES/EN) — 0.1.x (vía Tauri)

<!-- 0.2 — engine-swap Tauri → Electron. -->

- ✓ `apps/desktop` corre como app electron-vite (main/preload/renderer) — v0.2 (SHELL-01)
- ✓ Frontera nativa única (`src/native.ts`, 20 ops) reemplaza todos los `@tauri-apps/*` — v0.2 (NATIVE-01)
- ✓ El repo buildea sin Rust; `src-tauri` borrado — v0.2 (SHELL-02)
- ✓ Sidecar Python lanzado/gestionado desde el main de Electron (readiness gate + kill idempotente) — v0.2 (NATIVE-02)
- ✓ Paridad de features nativas: tray, window prefs, titlebar, Discord RPC, single-instance, autostart, notificaciones, dialog, opener — v0.2 (NATIVE-03..06)
- ✓ Data dir compatible (`%APPDATA%\app.nyanko.desktop`) con assert de arranque — v0.2 (DATA-01)
- ✓ Empaquetado electron-builder NSIS + auto-update electron-updater — v0.2 (PKG-01, PKG-02)
- ✓ Logging/diagnóstico (electron-log) desde la primera versión Electron — v0.2 (OBS-01)

### Active

<!-- 0.3 — sin milestone definido todavía. Correr /gsd-new-milestone. -->

Trabajo de 0.3 **ya commiteado sin roadmap detrás** (empezó a filtrarse mientras se cerraba 0.2):

- [x] Manga como ciudadano de primera en `edit_entry` (endpoints MAL propios)
- [x] Discovery ↔ biblioteca (filtro de items ya en biblioteca, alta directa desde búsqueda)
- [x] Ajustes movidos a modal con nav semántica y subtabs
- [x] Actividad de ediciones locales en el timeline

Candidatos heredados de 0.2 (ver `milestones/v0.2-REQUIREMENTS.md`):

- [ ] Firma pública externa + página "Verify" (minisign/cosign)
- [ ] Rediseño de la pantalla de extensión (descargas por navegador, guía, estado)
- [ ] Adapters comunitarios con API versionada
- [ ] Navegador embebido / webviews para sitios externos
- [ ] Code-signing del instalador Windows

Deuda de 0.2 a saldar:

- [ ] W-3: el tray no se entera si pausas la detección desde la UI
- [ ] D-I-03: `RateLimitedClient(requests_per_minute=90)` vs `X-RateLimit-Limit: 30` de AniList
- [ ] `docs/extra/RELEASING.md` sin trackear (`docs/extra/` gitignorado)

### Out of Scope

- Migrar el backend Python a Node — el sidecar existe y funciona; solo cambió el shell.
- Soporte multiplataforma nuevo (macOS/Linux) — Windows sigue siendo el target.

## Context

- Monorepo `apps/{backend,desktop,extension}`. El shell es Electron; backend, extension y el renderer
  React quedaron intactos salvo la capa nativa.
- `src-tauri/` borrado del árbol; vive en git y en el backup
  `nyanko-pre-electron-backup-20260709.tar.gz` (446 líneas de Rust: sidecar, tray, discord,
  window_prefs), usado solo como referencia de comportamiento.
- **Corrección de un supuesto que resultó falso:** este documento afirmaba «distribución efectiva: un
  solo usuario (el autor), no se necesita puente de auto-update Tauri→Electron». **Sí se necesitó.**
  La 0.1.15 (Tauri) solo entiende `latest.json` firmado con minisign, así que sin puente el parque
  instalado se quedaba varado en silencio. Se construyó (`scripts/publish-bridge.mjs`, 05-04) y se
  ejercitó sobre una instalación real. Está encadenado a `dist:publish` para que no se pueda olvidar.
- Historial de bugs relevante: arranque lento por readiness del sidecar/puerto, data dir divergente
  (6 DBs), URLs de assets con el puerto dentro. Los tres cerrados; los gates que los previenen
  (readiness doble, assert de `userData`, rutas relativas) son load-bearing — no los quites.

## Constraints

- **Compatibility**: `userData` debe quedar en `%APPDATA%\app.nyanko.desktop` (identifier Tauri) o la
  biblioteca de prod existente queda huérfana. Hay un assert que crashea el arranque si se rompe.
- **Versionado**: el updater exige **semver estricto** — nada de sufijos `a`/`b`/`c`; los parches van
  `0.2.N`. Regla por versión: 0.2.x fixes / 0.3.0+ features.
- **Tech stack**: electron-vite + electron-builder (NSIS) + electron-updater + TypeScript; sidecar
  Python PyInstaller onedir.
- **Security**: `contextIsolation:true`, `nodeIntegration:false`, `sandbox:true`, `webSecurity:true`.
- **Platform**: Windows es el target primario.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Electron sobre seguir en Tauri | Ecosistema desktop maduro (plugins, adapters, comunidad) para la expansión long-term del companion | ✓ Good — migración completa sin pérdida de datos; el renderer React no se tocó |
| electron-vite (no Electron a mano) | HMR main/preload/renderer + integración builder sin glue artesanal | ✓ Good |
| Mantener backend Python como sidecar | Ya existe y funciona; migrarlo a Node sería reescritura innecesaria | ✓ Good — el sidecar cruzó la migración sin un solo cambio |
| `src/native.ts` como frontera única | Aísla la superficie nativa; clave para adapters/tray/updater futuros | ✓ Good — el self-check bidireccional es lo que impidió que los 10 stubs de la Fase 3 se colaran a producción |
| userData fijo a `app.nyanko.desktop` | Preserva la biblioteca existente sin migración | ✓ Good — verificado por md5 e `integrity_check` sobre la instalación real |
| Diferir firma pública / UI extensión / adapters a 0.3 | Mantener 0.2 aburrida y estable | ✓ Good |
| Preload en CommonJS, no ESM | Un preload sandboxed no puede ser ESM (Electron lo rechaza) | ✓ Good — descubierto en la Fase 1, no en producción |
| Puente minisign para el parque 0.1.15 | El supuesto «un solo usuario, sin puente» era falso: Tauri solo entiende `latest.json` firmado | ⚠️ Revisit — funciona y está encadenado a `dist:publish`, pero es un mecanismo que solo existe para el salto 0.1→0.2; borrable cuando no quede parque Tauri |
| `customCheckAppRunning` reconstruida como aditiva (B-1) | No es un hook aditivo: es la rama `!else` del check de electron-builder — definirla lo desactivaba | ✓ Good — pero la lección es la que importa: el fallo vivía en la **costura** entre dos fases individualmente correctas, y solo un audit cruzado podía verlo |

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
*Last updated: 2026-07-13 after v0.2 milestone (Tauri → Electron)*
