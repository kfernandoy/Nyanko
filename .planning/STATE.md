---
gsd_state_version: 1.0
milestone: v0.3
milestone_name: Nyanko lee manga
status: ready
last_updated: "2026-07-13T00:00:00.000Z"
last_activity: 2026-07-13
progress:
  total_phases: 9
  completed_phases: 0
  total_plans: 0
  completed_plans: 0
  percent: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-07-13)

**Core value:** Nyanko deja de ser solo un tracker y pasa a ser **donde consumes**: el manga se lee
dentro de la app, y el tracking ocurre solo — el mismo trato que la detección de reproducción ya le da
al anime.
**Current focus:** Fase 1 — Fundaciones (limitador, esquema y modelo de progreso).

## Current Position

Phase: 1 — Fundaciones — limitador, esquema y modelo de progreso (siguiente)
Plan: —
Status: Ready — roadmap escrito, 48/48 requisitos mapeados
Last activity: 2026-07-13 — ROADMAP.md de v0.3 creado (9 fases)

Siguiente comando: `/gsd-plan-phase 1`

## Progress

```
Fases: [.........] 0/9
```

| Fase | Qué entrega | Research pass |
|------|-------------|---------------|
| 1 | Fundaciones: limitador, esquema v8, modelo de progreso | no |
| 2 | Motor de fuentes: contrato, presupuesto, taxonomía de errores | no |
| 3 | Page pipe + lectura local (piedra angular) | no |
| 4 | Identidad y vínculo fuente ↔ tracker | no |
| 5 | Sync de progreso (la tesis del milestone) | no |
| 6 | Distribución de extensiones: repo, instalación, trust gate | no |
| 7 | Fuentes online (2-3 propias en `nyanko-extensions`) | **sí** |
| 8 | Cola de descargas | **ligero** |
| 9 | AnimeThemes + deuda de 0.2 + auditoría de costuras | no |

## Accumulated Context

### Decisiones que fijan el diseño (no se retrofittean)

| # | Decisión | Consecuencia en el roadmap |
|---|----------|----------------------------|
| D-1 | Nyanko envía **cero** fuentes (modelo Mihon) | Fase 6: instalación limpia = catálogo vacío |
| D-2 | Las fuentes propias viven en `nyanko-extensions`, repo aparte | El feed del updater se queda en GitHub Releases; **no hay tarea de migración de feed** en este milestone. `nyanko-extensions` nunca se fusiona con el repo de la app, y el índice nunca se sirve desde él |
| D-3 | El bundle es **código** (módulo Python, sha256 en el índice) | Ejecución remota de código → el **trust gate** (SRC-03) es requisito de seguridad, no pulido |
| D-4 | Portar una extensión de Mihon es reescribirla a mano | Fase 7 escribe 2-3 fuentes desde cero; no existe «portar keiyoushi» |

### La lección de 0.2 que da forma a las fases

Una fase verificada **no** es una fase segura: los fallos viven en las **costuras**. En 0.2, B-1
combinó dos fases individualmente correctas, ambas con su gate en verde, en un resultado roto en
silencio. Solo el audit cruzado lo vio. Por eso: (a) las costuras se meten **dentro** de una fase
donde se puede (el presupuesto compartido en la Fase 2, la CSP en la 3, el aviso del updater en la 8),
y (b) DBT-03 presupuesta la auditoría cruzada explícita antes de cerrar el milestone.

### Trampas ya conocidas (citadas, no hipotéticas)

- El limitador son **tres** bugs; arreglar solo el 90→30 arma los otros dos. → Fase 1.
- Este proyecto **ya perdió todas las portadas** persistiendo el puerto efímero dentro de una URL. El
  reader es una superficie diez veces mayor. → Fase 1 (test de guardia) + Fase 3 (URLs relativas).
- En producción el renderer es `file://` (origen `null`); en dev tiene origen real. Un reader perfecto
  durante todo el desarrollo devuelve imágenes rotas el día que se empaqueta. → Fase 7, verificado en
  build empaquetado.
- `killSidecar()` es `taskkill /T /F`: cero oportunidad de vaciar buffers. → Fase 8.

### Deuda de 0.2 — dónde acabó

| Ítem | Destino |
|------|---------|
| D-I-03 (rate limit) | **Fase 1** — promovido de limpieza a prerrequisito |
| W-3 (tray ↔ UI) | Fase 9 (DBT-01) |
| `RELEASING.md` sin trackear | Fase 9 (DBT-02) |
| Releases v0.2.1/v0.2.2 borrados (404) | Aceptado; la evidencia vive en `05-06-SUMMARY.md`. Es también el precedente que justifica D-2 |

### Fuera del roadmap (vía `/gsd-quick`, en un 0.2.x)

Cuatro arreglos de UI pequeños y aislados (menú del avatar, Ctrl+E / selección de texto, opciones sin
cuenta vinculada, iconos de proveedores). No bloquean la 0.3.

## Session Continuity

Roadmap de v0.3 creado el 2026-07-13. Nada ejecutado todavía. El siguiente paso es
`/gsd-plan-phase 1`; las fases 7 y 8 llevan `--research-phase` cuando les toque.
