---
gsd_state_version: 1.0
milestone: v0.3
milestone_name: «Nyanko lee manga»
current_phase: 03
current_phase_name: page-pipe-lectura-local-la-piedra-angular
status: ready_to_execute
stopped_at: Fase 03 planificada y verificada — lista para ejecutar
last_updated: "2026-07-14T04:49:03.451Z"
last_activity: 2026-07-14
last_activity_desc: Fase 03 planificada (7 planes) y verificada por el plan-checker
progress:
  total_phases: 9
  completed_phases: 2
  total_plans: 7
  completed_plans: 7
  percent: 22
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-07-13)

**Core value:** Nyanko deja de ser solo un tracker y pasa a ser **donde consumes**: el manga se lee
dentro de la app, y el tracking ocurre solo — el mismo trato que la detección de reproducción ya le da
al anime.
**Current focus:** Phase 03 — page pipe + lectura local (la piedra angular)

## Current Position

Fase 02 — **CERRADA** (verify: passed, 12/12 verdades; code review: 4 blockers cerrados). Suite: 407 passed.
Fase 03 — **PLANIFICADA Y VERIFICADA**: 7 planes en 6 olas, plan-checker en verde (3 blockers
cerrados en la revisión 1/3). CONTEXT con 18 decisiones bloqueadas.

Siguiente comando: `/gsd-execute-phase 3` (los planes los ejecuta Codex — ver `.planning/CODEX-RULES.md`)

| Plan | Ola | Qué entrega |
|------|-----|-------------|
| 03-01 | 1 | Contrato v2: `page_bytes` + `SOURCE_API_VERSION` 1→2. CBZ/ZIP/ComicInfo en `LocalArchiveSource` |
| 03-02 | 2 | Esquema v9 (`reader_prefs`, `reader_progress`, `reading_events`) + guardia FND-05 |
| 03-03 | 2 | Ruta `/assets/pages/{page_id:path}` — antes del mount (D-04), sin paths (D-05) |
| 03-04 | 3 | API `/api/manga/*` + WR-06 (registry estático) |
| 03-05 | 4 | Cliente + `MangaLibraryView` |
| 03-06 | 5 | `ReaderView`: 3 modos, navegación, encadenado, ventana de decodificación |
| 03-07 | 6 | RD-09 **medido** (RSS real del renderer) + CSP (Seam G) |

**El orquestador corre estos gates, Codex no puede:** la suite de pytest (su sandbox deniega el TEMP
del sistema) y `scripts/reader-rss.mjs` (no arranca Electron en su jaula).

## Progress

```
Fases: [##.......] 2/9
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

**Resume file:** .planning/phases/03-page-pipe-lectura-local-la-piedra-angular/03-CONTEXT.md

**Last session:** 2026-07-14T04:49:03.435Z
**Stopped at:** Phase 3 context gathered

Fases 1 y 2 hechas y con sus gates en verde. Fase 3 discutida. Siguiente: `/gsd-plan-phase 3`.
Los planes los **ejecuta Codex** según `.planning/CODEX-RULES.md` (Codex escribe código y tests; el
orquestador corre la suite, commitea y cierra los artefactos de `.planning/`). El ROADMAP marca
`UI hint: yes` para la Fase 3: `/gsd-ui-phase 3` antes de planificar si se quiere contrato visual.
Las fases 7 y 8 llevan `--research-phase` cuando les toque.

### Warnings de la Fase 2 que entran como contexto de la Fase 3

Al cablear el engine dejan de ser latentes (ver `02-VERIFICATION.md`):

- **WR-06** — el registry se construye una sola vez en `lifespan`: una carpeta de biblioteca añadida
  en caliente es invisible para `LocalArchiveSource` hasta reiniciar.

- **WR-03** — el fallback a caché traga `SourceRateLimitError`: devolver caché ante un 429 es
  back-pressure perdida (`except SourceError:` a secas en `engine.py:89`).

- **WR-01** — `SourceEngine` no se re-exporta en `sources/__init__.py` (4 líneas).
- **WR-08** — los `RateLimitedClient` por fuente nunca se cierran en el shutdown.

## Performance Metrics

| Phase | Plan | Duration | Notes |
|-------|------|----------|-------|
| Phase 01 P01 | 50min | 3 tasks | 6 files |
| Phase 01 P02 | ~50 min | 3 tasks | 7 files |
| Phase 01 P03 | ~25 min | 2 tasks | 2 files |
| Phase 01 P04 | 35m | 2 tasks | 6 files |

## Decisions

- [Phase 01]: Limitador: el número del constructor (90/50/60) es valor inicial y TECHO; el presupuesto real lo anuncia X-RateLimit-Limit, acotado a [1, techo] para que una cabecera hostil no lo desactive — FND-01: hornear el presupuesto es lo que nos mantuvo pegándole a AniList a 90 req/min mucho después de que bajara a 30
- [Phase 01]: Limitador: el semáforo pasa a ser tope de peticiones EN VUELO (max_concurrency=8); el ritmo lo lleva un reloj de salidas por event loop, durmiendo fuera del semáforo — FND-02/FND-03: dormir con el semáforo retenido no limitaba nada, y los primitivos de asyncio en __init__ se ataban al loop del import (MutationWorker usa asyncio.run() en otro hilo)
- [Phase 01]: Schema v8: columna aditiva chapter_progress REAL en vez de rebuild de library_entries — SQLite no tiene ALTER COLUMN TYPE; el rebuild sobre 2.774 filas vivas devolveria 10.0 donde la API hoy devuelve 10, y un ADD COLUMN no puede alterar los recuentos por tabla
- [Phase 01]: progress (INTEGER) es autoritativo; chapter_progress se reconcilia AL LEER — chapter_progress solo vale si floor(chapter_progress) == progress. progress tiene cuatro escritores que no lo tocaran: un invariante mantenido en cuatro sitios se rompe, uno derivado al leer (progress.effective_chapter) no
- [Phase 01]: La ventana transitoria de effective_chapter queda ACEPTADA, no es un bug pendiente — Sync del tracker con valor viejo mientras la mutacion esta encolada: transitoria y autocurativa. Evitarla exigiria el diseno rechazado. Escrita en progress-model.md para que la Fase 5 no la parchee
- [Phase 01]: next_progress falla cerrado y progress_before graba el valor DEL TRACKER — Sin valor del tracker devuelve None. progress_before se captura antes de update_remote_library_entry o acabaria siendo progress_after; un 0 de relleno pondria a cero el AniList real via undo_playback
- [Phase 01]: Guardia FND-05 por introspeccion del esquema (sqlite_master + PRAGMA table_info): cero listas de columnas que mantener — Una lista de columnas escrita a mano es una lista que un dia no se actualiza; la guardia cubre el esquema v8 y lo que traiga la Fase 3 por construccion
- [Phase 01]: assert_no_persisted_urls es un helper importable, no logica enterrada en un test — Es un control sobre DATOS: sobre tablas vacias pasa en vacio. Las Fases 3/7/8 deben llamarlo tras SUS escrituras
- [Phase 01]: La regla dura de la lista blanca comprueba el sufijo 'path', no '_path' — local_files.path y library_folders.path no acaban en _path: la regla del plan no habria cubierto las unicas dos columnas de ruta local que existen
- [Phase 02]: El presupuesto se concede de UNO EN UNO y en la SALIDA (`_grant_slot` desde `_release_slot`), no drenando el heap — repartir el heap entero hacía que cada waiter ya despachado fuera dueño de su hueco, así que la prioridad de lectura solo reordenaba dentro de la ventana de 1 ms: cosmética justo en el caso real (descargas en curso + lectura interactiva después). Tenía test verde encima; el test nuevo falla contra el dispatcher viejo
- [Phase 02]: Un mecanismo con kwarg + heap + test verde puede no hacer NADA — la lección de Seam F: el verifier lo pilló ejecutando el limitador, no leyendo el review. Los tests de ritmo se escriben esperando a que algo haya SALIDO de verdad, no metiendo todo en la misma ráfaga
- [Phase 1]: FND-05: la guardia de URLs persistidas tiene dos capas — la lista blanca exime del prefijo http, pero NADA exime de guardar una URL al propio sidecar (//127.0.0.1, //localhost, //[::1]), esté donde esté dentro del valor
