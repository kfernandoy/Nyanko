# Roadmap: Nyanko

## Milestones

- ✅ **v0.2 Tauri → Electron** — Fases 1-5 (shipped 2026-07-13) — [archivo](milestones/v0.2-ROADMAP.md)
- 📋 **v0.3** — sin planificar (`/gsd-new-milestone`)

## Phases

<details>
<summary>✅ v0.2 Tauri → Electron (Fases 1-5) — SHIPPED 2026-07-13</summary>

Engine-swap del shell de escritorio: `src-tauri` (Rust) → electron-vite (main + preload + renderer),
sin tocar el renderer React, el backend Python sidecar ni la extensión. Regla dura: paridad con
0.1.15, cero features nuevas.

- [x] Fase 1: Electron shell scaffold + data-dir lock (2/2 plans) — 2026-07-10
- [x] Fase 2: Main core — sidecar lifecycle + logging (2/2 plans) — 2026-07-10
- [x] Fase 3: Native boundary + Tauri removal (2/2 plans) — 2026-07-11
- [x] Fase 4: Native feature parity (3/3 plans) — 2026-07-11
- [x] Fase 5: Packaging + auto-update (6/6 plans) — 2026-07-12

Detalle completo (goals, success criteria, waves): [milestones/v0.2-ROADMAP.md](milestones/v0.2-ROADMAP.md)

</details>

### 📋 v0.3 — por definir

El trabajo de 0.3 ya empezó a filtrarse en el árbol (manga first-class, discovery ↔ biblioteca,
ajustes en modal, actividad local) sin roadmap detrás. Antes de seguir: `/gsd-new-milestone`.

Candidatos heredados de 0.2 (`v0.2-REQUIREMENTS.md` → *v2 / Deferred*):

- Firma pública externa + página "Verify" (minisign/cosign)
- Rediseño de la pantalla de extensión
- Adapters comunitarios con API versionada
- Navegador embebido / webviews
- Code-signing del instalador Windows

Deuda abierta de 0.2 (ver MILESTONES.md): W-3 (tray ↔ UI en una dirección), D-I-03 (rate limit de
AniList mal configurado), `RELEASING.md` sin trackear.

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Electron shell scaffold + data-dir lock | v0.2 | 2/2 | Complete | 2026-07-10 |
| 2. Main core — sidecar lifecycle + logging | v0.2 | 2/2 | Complete | 2026-07-10 |
| 3. Native boundary + Tauri removal | v0.2 | 2/2 | Complete | 2026-07-11 |
| 4. Native feature parity | v0.2 | 3/3 | Complete | 2026-07-11 |
| 5. Packaging + auto-update | v0.2 | 6/6 | Complete | 2026-07-12 |
