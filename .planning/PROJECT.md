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

**En curso: v0.3 «Nyanko lee manga»** — definiendo requisitos.

## Core Value

Nyanko deja de ser solo un tracker y pasa a ser **donde consumes**: el manga se lee dentro de la app,
y el tracking ocurre solo — el mismo trato que la detección de reproducción ya le da al anime.

> El core value de 0.2 («el tracking funciona idéntico tras cambiar el motor») se cumplió y caducó:
> era de migración, no de producto. Este lo reemplaza.

## Current Milestone: v0.3 Nyanko lee manga

**Goal:** Convertir Nyanko en el sitio donde el manga se lee, no solo donde se anota — con lectura
local y online, y el progreso subiendo solo al proveedor.

**Target features:**
- Reader de manga: archivos locales y fuentes online, con la experiencia de lectura de Mihon
- Motor de adapters de fuentes versionado (el requisito diferido de 0.2), estrenado con 2-3 fuentes propias
- Descargas offline: cola de descargas; lo descargado se lee como local
- Sync automático de progreso al terminar capítulo (AniList/MAL/Kitsu)
- Openings/endings en las cards vía AnimeThemes, con reproducción desde la card
- Saldar la deuda de 0.2: W-3, D-I-03, RELEASING.md

**Contexto que decide el diseño:** las extensiones de Mihon son APKs de Kotlin/Android — **no hay
atajo de compatibilidad**. El motor de fuentes se construye desde cero. Motor de adapters y descargas
son los dos trozos caros; el resto cuelga de ellos.

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

<!-- Filtrado a main mientras se cerraba 0.2, sin roadmap detrás. Absorbido en 0.3 como ya hecho:
     no se re-implementa, pero la 0.3 construye encima (el reader depende del manga first-class). -->

- ✓ Manga como ciudadano de primera en `edit_entry` (endpoints MAL propios) — pre-0.3
- ✓ Discovery ↔ biblioteca (filtro de items ya en biblioteca, alta directa desde búsqueda) — pre-0.3
- ✓ Ajustes movidos a modal con nav semántica y subtabs — pre-0.3
- ✓ Actividad de ediciones locales en el timeline — pre-0.3

### Active

<!-- 0.3 — requisitos formales en REQUIREMENTS.md tras /gsd-new-milestone. -->

Reader de manga:

- [ ] Lectura de manga desde archivos locales
- [ ] Lectura de manga desde fuentes online
- [ ] Motor de adapters de fuentes con API versionada + 2-3 fuentes propias de arranque
- [ ] Descarga de capítulos para lectura offline (cola de descargas)
- [ ] El progreso de lectura sube solo al proveedor al terminar capítulo

Música:

- [ ] Openings/endings en las cards vía AnimeThemes, reproducibles desde la card

Deuda de 0.2 (toda entra en 0.3):

- [ ] W-3: el tray no se entera si pausas la detección desde la UI
- [ ] D-I-03: `RateLimitedClient(requests_per_minute=90)` vs `X-RateLimit-Limit: 30` de AniList
      — **hoy es latente porque el backfill es secuencial; un reader que hace ráfagas lo despierta**
- [ ] `docs/extra/RELEASING.md` sin trackear (`docs/extra/` gitignorado)

### Fuera del roadmap 0.3 — vía `/gsd-quick`

Arreglos de UI pequeños y aislados. Decisión explícita: no bloquean la 0.3, se envían en un 0.2.x.

- [ ] Avatar: el menú solo se cierra re-clickando el avatar; debería cerrarse al hacer click fuera
- [ ] Bloquear Ctrl+E y la selección de texto con el ratón salvo dentro de las cards
- [ ] Usuario nuevo sin cuenta vinculada ve opciones que solo aplican con cuenta ("cerrar sesión", "pausar sync")
- [ ] Usuario nuevo: mostrar iconos de los proveedores en vez del texto "conecta tu cuenta"

### Future (candidatos heredados de 0.2, no en 0.3)

- Firma pública externa + página "Verify" (minisign/cosign)
- Rediseño de la pantalla de extensión (descargas por navegador, guía, estado)
- Navegador embebido / webviews para sitios externos
- Code-signing del instalador Windows

### Out of Scope

- Migrar el backend Python a Node — el sidecar existe y funciona; solo cambió el shell.
- Soporte multiplataforma nuevo (macOS/Linux) — Windows sigue siendo el target.
- Compatibilidad con extensiones de Mihon — son APKs de Kotlin/Android; no hay forma de cargarlas
  desde Electron. El motor de fuentes se construye desde cero.
- Adapters de terceros instalables en caliente (repositorio, sandbox, permisos) — 0.3 estrena el
  motor con fuentes propias; abrirlo a la comunidad es superficie de seguridad para un milestone aparte.

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
| **0.3:** el reader lee local **y** online, no uno de los dos | Solo local es un visor de archivos; solo online no aprovecha la biblioteca que el usuario ya tiene en disco | Pendiente |
| **0.3:** motor de adapters propio + 2-3 fuentes de arranque | Cablear las fuentes obliga a refactorizar cuando llegue la comunidad. Estrenar el motor con fuentes propias paga el requisito diferido de 0.2 sin abrir la superficie de seguridad de los adapters de terceros | Pendiente |
| **0.3:** el progreso de lectura sube solo al proveedor | Es el paralelo exacto de la detección de reproducción de anime. Sin esto el reader es un lector cualquiera, no el reader *de Nyanko* | Pendiente |
| **0.3:** los arreglos de UI chicos salen del roadmap | Son aislados y no bloquean el reader. Van por `/gsd-quick` en un 0.2.x, para que la 0.3 no cargue con ellos | Pendiente |

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
*Last updated: 2026-07-13 — inicio del milestone v0.3 (Nyanko lee manga)*
