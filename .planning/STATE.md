---
gsd_state_version: 1.0
milestone: v0.2
milestone_name: "Tauri → Electron"
current_phase: null
current_phase_name: null
status: milestone_complete
stopped_at: "v0.2 cerrado y archivado (verified_closeout). Siguiente: /gsd-new-milestone para definir 0.3"
last_updated: "2026-07-13T05:30:00.000Z"
last_activity: 2026-07-13
last_activity_desc: "Milestone v0.2 (Tauri → Electron) cerrado: B-1 probado en runtime, fase 5 re-verificada 11/11, audit passed, archivado y etiquetado"
progress:
  total_phases: 5
  completed_phases: 5
  total_plans: 15
  completed_plans: 15
  percent: 100
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-07-13)

**Core value:** ⚠️ El de 0.2 («el tracking funciona idéntico tras cambiar el motor») **se cumplió y
caducó** — era un core value de migración, no de producto. Redefinirlo en `/gsd-new-milestone`.
**Current focus:** ninguno — milestone cerrado, 0.3 sin definir.

## Current Position

**v0.2 (Tauri → Electron) CERRADO 2026-07-13.** 5/5 fases, 15/15 planes, 12/12 requisitos,
audit `passed`, `verified_closeout`. Archivado en `.planning/milestones/`.

El engine-swap está vivo en producción: canal **v0.2.3**, auto-update por electron-updater
verificado sobre instalaciones reales, y el parque 0.1.15 migrado por el puente minisign.

## Cómo se cerró (importa, porque casi se cierra mal)

El milestone estuvo a punto de archivarse con un blocker vivo. El audit cruzado encontró **B-1**: el
arreglo de la Fase 5 al problema de bloqueo de ficheros de la Fase 2 había desactivado en silencio la
protección de bloqueo de ficheros del propio electron-builder (`customCheckAppRunning` es la rama
`!else` de su check, no un hook aditivo). Las dos fases eran, por separado, correctas — y las dos
habían pasado su verificación. En máquina rápida el auto-update gana la carrera, así que **ningún
gate por fase podía verlo**.

Se arregló, y luego se **probó de verdad**: instalador reconstruido, Nyanko abierta, doble click sin
`/S` → avisa y la cierra antes de extraer. El mismo run cerró de paso el selector ES/EN y el EULA,
que la Fase 5 había aceptado a ciegas.

**Lección para 0.3:** una fase verificada no es una fase segura. Los fallos viven en las costuras.

## Deuda abierta (a 0.3)

| Ítem | Qué es | Coste |
|------|--------|-------|
| W-3 | El tray no se entera si pausas la detección desde la UI (estado unidireccional) | Cosmético; se autocorrige al siguiente click |
| D-I-03 | `RateLimitedClient(requests_per_minute=90)` vs `X-RateLimit-Limit: 30` real de AniList | No muerde hoy (backfill secuencial); una ráfaga comería 429s |
| RELEASING.md | Existe en disco pero `docs/extra/` está gitignorado | El runbook de release vive solo en la máquina del autor |
| Releases borrados | v0.2.1 y v0.2.2 se borraron a propósito tras probar su salto | La evidencia del salto 0.2.0→0.2.1 no es reproducible; vive en `05-06-SUMMARY.md` |

## Trabajo de 0.3 ya en el árbol, sin roadmap detrás

Se commiteó mientras se cerraba 0.2 (manga first-class, discovery ↔ biblioteca, ajustes en modal,
actividad local). **No está planificado.** `/gsd-new-milestone` tiene que absorberlo o revertirlo,
no ignorarlo.
