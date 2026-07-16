---
gsd_state_version: 1.0
milestone: v0.3
milestone_name: «Nyanko lee manga»
status: in_progress
stopped_at: Fase 03 ejecutada (7/7). Los 3 Critical cerrados: RD-09 verde (147 MB), CR-01 y CR-03+WR-03 (455 passed). Pendiente: UAT manual de los tres modos
last_updated: "2026-07-16T08:32:45.489Z"
progress:
  total_phases: 9
  completed_phases: 3
  total_plans: 14
  completed_plans: 14
  percent: 33
current_phase: 03
current_phase_name: page-pipe-lectura-local-la-piedra-angular
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-07-13)

**Core value:** Nyanko deja de ser solo un tracker y pasa a ser **donde consumes**: el manga se lee
dentro de la app, y el tracking ocurre solo — el mismo trato que la detección de reproducción ya le da
al anime.
**Current focus:** Phase 03 — page-pipe-lectura-local-la-piedra-angular

## Current Position

Fase 02 — **CERRADA** (verify: passed, 12/12 verdades; code review: 4 blockers cerrados). Suite: 407 passed.
Fase 03 — **EJECUTADA (7/7 planes)**, no cerrada todavía. Code review: 3 Critical, 6 Warning, 2 Info
(`03-REVIEW.md`). Dos de los tres Critical ya cerrados vía `/gsd-quick`:

- **RD-09 medido y en verde**: 619-621 MB → **147-161 MB** (pico ~243) contra el techo de 500.
  La causa no era la ventana de decodificación (siempre fue correcta) sino CSS: los 4 vecinos de
  preload se maquetaban a 2000x3000. `MAX_LIVE_PAGES`=5 y `TECHO_RSS_MB`=500 sin tocar.
- **CR-01 cerrado**: los títulos con `!` ya no son ilegibles. Suite: **452 passed**.
- **CR-03 cerrado** (+ **WR-03** en el mismo commit-set): el cache de capítulos vive entre peticiones y
  un 429 sigue saliendo 429 con el cache caliente. Suite: **455 passed**.

Los **3 Critical del review están cerrados**. Pendiente para cerrar la fase: el **UAT manual de los tres
modos** (el harness solo cubre paginado).

Siguiente comando: `/gsd-verify-work 3` tras el UAT manual.

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

**Last session:** 2026-07-16T08:11:32.645Z
**Stopped at:** Fase 03 planificada (7 planes) y verificada por el plan-checker. Lista para ejecutar.

Fases 1 y 2 hechas y con sus gates en verde. Siguiente: `/gsd-execute-phase 3`.
Los planes los **ejecuta Codex** según `.planning/CODEX-RULES.md` (Codex escribe código y tests; el
orquestador corre la suite, commitea y cierra los artefactos de `.planning/`). Se planificó **sin**
`/gsd-ui-phase` por decisión explícita, aunque el ROADMAP marque `UI hint: yes`.
Las fases 7 y 8 llevan `--research-phase` cuando les toque.

### Warnings de la Fase 2 que entran como contexto de la Fase 3

Al cablear el engine dejan de ser latentes (ver `02-VERIFICATION.md`):

- **WR-06** — el registry se construye una sola vez en `lifespan`: una carpeta de biblioteca añadida
  en caliente es invisible para `LocalArchiveSource` hasta reiniciar.

- ~~**WR-03** — el fallback a caché traga `SourceRateLimitError`~~ **CERRADO** (quick 260716-9cd), en el
  mismo commit-set que CR-03. El fallback filtra por `source_error_action(error) == "esperar"` — la
  taxonomía que ya existía, no un `isinstance` nuevo. `SourceParseError` (`actualizar_la_fuente`) sigue
  sirviendo caché.

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

### Blockers

- ~~RD-09 REPROBADO: 621 MB vs techo 500 MB~~ **CERRADO** (quick 260716-6ba, 2026-07-16). Causa raiz: no era la ventana de decodificacion (`decodeWindow` siempre fue correcta), era CSS — `.reader-page--preload img` llevaba `max-width:none; max-height:none` y las reglas de ajuste solo apuntaban a `--visible`, asi que los 4 vecinos se maquetaban a 2000x3000 fuera del lienzo (`left:-100000px` mueve, no saca del layout ni del paint). Ahora paginado monta solo el grupo visible y calienta los vecinos por HTTP sin DOM. Medido: **147-161 MB (pico ~243)** vs techo 500, `test:reader-rss` sale 0. `MAX_LIVE_PAGES`=5 y `TECHO_RSS_MB`=500 SIN TOCAR — el numero baja porque el reader retiene menos, no porque se aflojara el gate.
- ~~CR-01: los titulos con `!` (`Oh My Goddess!`, `Yotsuba&!`) eran ilegibles~~ **CERRADO** (quick 260716-8fb). `page_bytes()` partia por el PRIMER `!`; ahora la frontera se DERIVA de los datos con un patron `(\.cbr|\.cbz|\.rar|\.zip)!` a `re.IGNORECASE | re.ASCII` (sin `.lower()`: `'İ'.lower()` son DOS caracteres y desplazaba el corte). Test de regresion commiteado EN ROJO antes del arreglo (`ea84237`), verificado: 5 fallan sin el fix, 6 pasan con el. Suite: **452 passed**.
- ~~CR-03: el cache de capitulos de `SourceEngine` esta MUERTO en produccion~~ **CERRADO** (quick 260716-9cd, 2026-07-16). `_source_engine()` construia un engine nuevo por request; ahora el engine se DERIVA de la identidad del registry al leer y se memoiza en `app.state.source_engine` (mismo patron que `progress.effective_chapter`: los 3 sitios de `build_source_registry` quedan intactos y un rebuild tira el cache por construccion, asi que WR-06 no empeora). **WR-03 se cerro en el MISMO commit-set**: arreglar CR-03 era el instante exacto en que el `except SourceError:` a secas dejaba de ser latente y empezaba a tragarse los 429 — entregarlos por separado habria reproducido a mano el modo de fallo B-1 de 0.2. Tests RED ejecutados, no razonados (`DID NOT RAISE`, `assert 502 == 200`, y el guardian de la costura demostrado a mano: `assert 200 == 429` revirtiendo la guarda). Suite: **455 passed**.
### UAT manual (2026-07-16) — 5 hallazgos, ninguno regresion del trabajo de hoy

La fase 03 NO cierra: RD-02 pide los tres modos de lectura y el UAT los encontro rotos.

1. **CBR** — NO ES BUG. Decision de LICENCIA ya escrita en REQUIREMENTS.md «Future Requirements»
   (clausula de unRAR vs libarchive/archive.dll; pide presupuesto de THIRD-PARTY-NOTICES y «no se
   cuela dentro de una fase del reader»). RD-01 dice «CBZ / ZIP / carpeta de imagenes». El 415
   «conviertelo a CBZ» ES el comportamiento especificado. **Reafirmado por el usuario 2026-07-16.**
2. **Anadir carpeta de manga dispara el escaneo de anime** — hay UNA tabla `library_folders
   (id, path, recursive)` sin columna de tipo, consumida por `iter_video_files` (anime) Y
   `build_source_registry` (manga). Decision del usuario: columna `kind` (anime/manga/ambas) +
   migracion; las existentes quedan como 'ambas'.
3. **Ajuste «alto» corta la pagina** en paginado LTR/RTL (y en doble pagina). SIN diagnostico: la
   cadena de alturas cuadra sobre el papel y la hipotesis del `.titlebar + .reader` quedo DESCARTADA
   (si son hermanos adyacentes). Necesita depuracion en vivo.
4. **Vertical + ajuste ancho: saltos bruscos al scrollear HACIA ARRIBA.** Diagnostico firme:
   `.reader-vertical-slot` reserva `min-height:100vh` pero una pagina real a ancho mide ~1800px,
   asi que el slot crece ~900px al montar el <img>; y `.reader-vertical` lleva `overflow-anchor: none`,
   que desactiva el anclaje de scroll del navegador que existe justo para compensar eso. Encaja con
   que sea especifico de ancho (a alto la img mide 100vh = el min-height) y de hacia arriba.
5. **No se ve la numeracion de pagina** — existe (`ReaderView.tsx:441`, `{paginaActual} / {total}`)
   pero vive DENTRO del <header> de controles, que se alterna con un clic. Acoplamiento de diseno.

- PENDIENTE: UAT manual de los tres modos con un capitulo real — el harness solo cubre paginado. Falta: rtl/ltr pasan pagina y las flechas respetan el sentido; vertical mantiene el scroll continuo sin huecos; doble pagina en rtl muestra DOS paginas.

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 260716-6ba | Arreglar la retencion de memoria del reader: preload a resolucion intrinseca (RD-09 CR-02) | 2026-07-16 | 3c9c4b3 | [260716-6ba-arreglar-la-retencion-de-memoria-del-rea](./quick/260716-6ba-arreglar-la-retencion-de-memoria-del-rea/) |
| 260716-8fb | Derivar la frontera archivo/miembro de los datos: los titulos con `!` eran ilegibles (CR-01) | 2026-07-16 | 7c7dbb8 | [260716-8fb-escapar-el-separador-de-miembro-de-archi](./quick/260716-8fb-escapar-el-separador-de-miembro-de-archi/) |
| 260716-9cd | Resucitar el cache del SourceEngine (CR-03) sin activar WR-03: un 429 sigue saliendo 429 | 2026-07-16 | ab1cb34 | [260716-9cd-resucitar-el-cache-del-sourceengine-sin-](./quick/260716-9cd-resucitar-el-cache-del-sourceengine-sin-/) |
| 260716-amb | Carpetas de biblioteca con tipo (`kind`): anadir manga ya no dispara el escaneo de anime (UAT #2) | 2026-07-16 | 1faab19 | [260716-amb-carpetas-de-biblioteca-con-tipo-anadir-m](./quick/260716-amb-carpetas-de-biblioteca-con-tipo-anadir-m/) |
| 260716-9cd | Resucitar el cache del SourceEngine sin perder el back-pressure (CR-03 + WR-03) | 2026-07-16 | b4d60a8, ab1cb34 | [260716-9cd-resucitar-el-cache-del-sourceengine-sin-](./quick/260716-9cd-resucitar-el-cache-del-sourceengine-sin-/) |
