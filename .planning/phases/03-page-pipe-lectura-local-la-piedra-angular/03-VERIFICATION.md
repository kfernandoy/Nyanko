---
phase: 03-page-pipe-lectura-local-la-piedra-angular
verified: 2026-07-16T21:38:01Z
status: passed
score: 7/7 must-haves verified
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: human_needed
  previous_score: 6/7
  gaps_closed:
    - "ROADMAP criterio 3 / RD-05: se reanuda por la pagina donde se dejo — cerrado con gate MEDIDO en Electron real (`rd-05 / reanudar tras cierre rapido`), con A/B ejecutado por el verificador: sin el flush reabre en la 5 habiendo cerrado en la 7 (exit 1); con el flush reabre en la 7 (exit 0)."
  gaps_remaining: []
  regressions: []
deferred:
  - truth: "CBR / RAR se leen"
    addressed_in: "v0.3.x / v0.4+ (Future Requirements)"
    evidence: "REQUIREMENTS.md §Future Requirements: decision de LICENCIA (clausula de unRAR), no tecnica. RD-01 dice «CBZ / ZIP / carpeta de imagenes». El 415 «conviertelo a CBZ» ES el comportamiento especificado — verificado en codigo (local_archive.py:165-166, 217-218) y por test_cbr_se_rechaza_sin_intentar_abrirlo."
  - truth: "WR-08: los RateLimitedClient por fuente se cierran en el shutdown"
    addressed_in: "Fase 9 (deuda de 0.2)"
    evidence: "Deuda de la Fase 2 (02-VERIFICATION.md), 4 lineas. Confirmado abierto: el lifespan (main.py:1503-1508) para watcher/worker/checker/detector pero no cierra ningun cliente."
---

# Phase 3: Page pipe + lectura local — la piedra angular — Verification Report

**Phase Goal:** «Nyanko lee mi colección de CBZ.» La arquitectura de entrega de páginas se vuelve
verdadera o falsa, probada con cero red, cero rate limits y cero fragilidad de scraping.
**Verified:** 2026-07-16T21:38:01Z
**Status:** passed
**Re-verification:** Sí — tras el cierre de RD-05 (la pasada anterior salió `human_needed`, 6/7)

## Cómo se verificó esto

**Ningún número de este informe sale de un SUMMARY.** Todos los gates se ejecutaron en este proceso:

| Gate | Comando | Resultado medido aquí |
|------|---------|----------------------|
| Suite backend | `pytest -q` (desde `apps/backend`) | **461 passed** en 107.18s |
| Typecheck | `npm run check` | limpio |
| Ventana de decodificación | `npm run test:reader` | **4/4** |
| CSP | `npm run test:csp` | **6/6** |
| Cadena de alturas + vertical + **RD-05** | `npm run build && npm run test:reader-fit` | **12/12**, exit 0 |
| **RD-05 — A/B del verificador** | ídem, con el flush desactivado a mano | **rd-05 en rojo, exit 1** — y los otros 11 casos siguen verdes |
| **RD-09 (RSS real)** | `npm run build && npm run test:reader-rss` | **160.06 MB final, pico 248.81 MB vs techo 500 → exit 0** |

El árbol quedó limpio tras el A/B (`git status --porcelain` vacío, `ReaderView.tsx:209` restaurado) y
se reconstruyó el `out/` con el código bueno antes de medir RD-09.

## Qué cambió desde la pasada anterior

La pasada anterior dejó **una** verdad sin ejercitar: RD-05 (reanudar). Estaba bien dejada: WR-02 era
un defecto vivo en ese camino y la exploración posterior encontró que era **peor** de lo documentado
(tres caminos de pérdida, no dos). Ambas cosas se han cerrado y las he vuelto a medir yo:

- **WR-02 arreglado** (`57ce7ba`, `ReaderView.tsx:201-211`): un segundo efecto cuyo cleanup hace flush
  del par (capítulo, página) pendiente. Sus deps son `[chapter.source_id, listo, total]` — **sin
  `paginaActual`** —, así que su cleanup solo corre al desmontar o al cambiar de capítulo y el debounce
  de 500ms sigue intacto. Verificado leyendo el código, no el parte.
- **RD-05 con gate medido** (`b513769`, `reader-fit.mjs:723-802`).

## Goal Achievement

### Observable Truths (los 7 criterios del ROADMAP)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | CBZ / ZIP / carpeta se leen en orden natural (`2` antes que `10`); `ComicInfo.xml` manda sobre el nombre | ✓ VERIFIED | `_natural_key` (`local_archive.py:56-60`) usado en los **tres** caminos: capítulos (:100), páginas sueltas (:145) y miembros del ZIP (:178) — una sola función de orden. ComicInfo manda: `:109` lee `Number` y `:124-128` solo cae al nombre `if number_text is None`. Tests: `test_archivo_local_iguala_zip_y_carpeta_en_orden_natural`, `test_comic_info_del_cbz_manda_sobre_el_nombre`, `test_comic_info_malformado_degrada_al_nombre`, `test_comic_info_peligroso_o_desmedido_no_se_parsea` |
| 2 | Tres modos (RTL por defecto, LTR, vertical), modo recordado **por serie** y superviviente al reinicio; doble página con offset manual | ✓ VERIFIED | Los 3 modos en `ReaderView.tsx:414` + clases `reader--${mode}`. **RTL por defecto en el ESQUEMA** (`database.py:280`: `mode TEXT NOT NULL DEFAULT 'rtl'`), no duplicado en el cliente (`ReaderView.tsx:87-90`: PUT vacío y decide SQLite). Por serie: PK `(source_name, series_id)`, `test_preferencias_se_aislan_por_serie_y_conservan_actualizaciones_parciales`. `test:reader-fit` **12/12** pinta los 3 modos × 3 ajustes. Doble página + offset: `pagePairs`, `test:reader` 4/4, lomo **0px** medido. ⚠️ Ver WR-03 |
| 3 | Navegación de escritorio completa **+ se reanuda por la página donde se dejó** | ✓ VERIFIED | **Navegación:** teclado (`:279-287`: ←/→ con inversión RTL, AvPág/RePág, Espacio, Inicio/Fin), rueda (`:304`), zonas de click (`:351-361`), F11 (`:261-266`), contador (`:478`, fuera del header tras UAT #5), 3 ajustes, zoom, paneo. El harness RSS ejercita **400 pulsaciones reales** contra Electron real. **Reanudar: MEDIDO, ya no inferido.** `rd-05 / reanudar tras cierre rapido` mide EL VIAJE (pasar página → Escape dentro de los 500ms → reabrir por el camino del usuario): `asentada en 5 \| cerrado de golpe en 7 \| reabre en 7`. **A/B ejecutado por mí**: desactivando el flush, `reabre en 5` y exit 1. Ver «El A/B» abajo |
| 4 | Encadena capítulo con pantalla de transición, y la transición **emite el evento «capítulo terminado»** | ✓ VERIFIED | `abrirTransicion` (`:158-171`) → pantalla (`:382-408`) → `onChapterChange`. El evento solo en `next` y deduplicado (`eventosEmitidos`, `:161-162`). **UAT test 1 PASADO** por el usuario: encadena y `reading_events` gana UNA fila (no dos). Backend: `test_evento_de_lectura_conserva_el_capitulo_decimal_y_media_id_nulo` (el 12.5 cabe: `chapter REAL`), `test_preferencias_progreso_y_evento_hacen_round_trip_sin_persistir_urls`. D-15 cumplido: la fila se escribe y no la lee nadie |
| 5 | RSS del renderer bajo el número escrito, tras 200 páginas de ida y vuelta | ✓ VERIFIED | **Medido por mí:** `160.06 MB final, pico 248.81 MB` contra techo **500** → exit 0. `MAX_LIVE_PAGES`=5 (`DECODE_BEHIND 2 + 1 + DECODE_AHEAD 2`) y `TECHO_RSS_MB`=500 **sin tocar**: el número baja porque el reader retiene menos, no porque se aflojara el gate. `test:reader-fit` imprime `montadas 6,7,8,9,10` — exactamente 5 |
| 6 | Ninguna URL de página persiste con host o puerto; `/assets/…` relativo resuelto por `normalizeAssetUrls`; la guardia FND-05 sigue verde | ✓ VERIFIED | `_page_url` (`main.py:348-351`) devuelve **relativo**. `normalizeAssetUrls` (`api.ts:207-220`) reescribe cualquier string `/assets/`, y `mangaPages` pasa por `request()` → `:254`. La guardia FND-05 se llama tras las escrituras de ESTA fase: 6 sitios en `test_reader_persistence.py` + `test_manga_api.py:300`. **Probado por comportamiento**: el harness RSS carga 200 páginas reales por esta cadena en Electron. Ruta ANTES del mount (`:1517` vs `:1542`, D-04) con `test_la_ruta_de_paginas_esta_antes_del_mount_de_assets`. Traversal cerrado: 8 casos parametrizados (D-05) |
| 7 | Existe una CSP y `webSecurity` sigue en `true` | ✓ VERIFIED | CSP en el HTML **construido** (`out/renderer/index.html`), no solo en el fuente. Producción sin `unsafe-inline` ni `unsafe-eval`. `webSecurity:true` + `contextIsolation:true` + `nodeIntegration:false` + `sandbox:true` en las **dos** ventanas. `test:csp` 6/6. **UAT test 2 PASADO**: portadas, HMR y splash intactos |

**Score:** 7/7 truths verified

### El A/B: por qué me creo el gate de RD-05

Un gate verde solo vale si puede ponerse rojo. No me fié del A/B que me contaron; lo hice yo,
desactivando **una sola línea** (el `setReaderProgress` del cleanup de flush, `ReaderView.tsx:209`) y
reconstruyendo:

| Estado del flush | Salida del caso rd-05 | Exit |
|------------------|----------------------|------|
| **Activo** (código real) | `asentada en 5 \| cerrado de golpe en 7 \| reabre en 7` | **0** |
| **Desactivado** (A/B) | `asentada en 5 \| cerrado de golpe en 7 \| reabre en 5` + `-> el progreso pendiente se perdio al desmontar` | **1** |

Lo que hace válido este A/B no es solo que se ponga rojo, sino que **los otros 11 casos siguen verdes**:
el rojo cae exactamente sobre lo que dice medir y por el motivo correcto. Un rojo por daño colateral
habría valido tan poco como un verde por accidente.

Los números además **cuadran con el código**, que es lo que descarta que salgan de la nada: `medirReanudar`
no resetea la doble página que dejó `recorrerAjustes`, así que los grupos son pares y desde Home dos
AvPág dan 1 → 3 → **5** (`asentada`), y la tercera → **7** (`cerrado de golpe`). Y el gate despacha en
`document` (`:736-739`), que es donde vive el listener (`:292`) — el modo de fallo de despachar en
`window` no está aquí.

### Los tres caminos de WR-02: el gate ejercita UNO. Qué pasa con los otros dos

Se me pidió mirar esto con lupa y es una pregunta correcta. En `App.tsx:1162-1165` el `ReaderView` se
monta **sin `key`**, así que las tres rutas NO son el mismo mecanismo de React:

| Camino | Mecanismo | ¿Medido? | Veredicto |
|--------|-----------|----------|-----------|
| **Escape** (`:286` → `onClose` → `App.tsx:1164` `setReaderChapter(null)` → **desmonta**) | cleanup de desmontaje | **Sí**, con A/B | ✓ |
| **Botón cerrar** (`:417` `onClick={onClose}`) | cleanup de desmontaje | No | ✓ **Es la misma función.** `onClose` es la *misma referencia* que usa Escape, 131 líneas más abajo. No es un camino parecido: es la misma línea de código alcanzada desde otro evento de entrada. Cubierto por identidad |
| **Encadenar capítulo** (`onChapterChange` → `setReaderChapter(next)` → **NO desmonta**, cambia una prop) | cleanup por **cambio de deps** | **No** — el harness solo crea UN capítulo (`Cap 1`, `reader-fit.mjs:91`), así que estructuralmente no puede encadenar | ✓ pero por otro motivo — ver abajo |

**El tercero no está medido, y lo digo.** Pero al trazarlo entero aparece algo que ni el 03-REVIEW ni el
SUMMARY dicen: **en el encadenado el flush es un cinturón que no sujeta nada en ninguna entrada
alcanzable**. La pantalla de transición es un `return` temprano del *render* (`:382`), **no un
desmontaje**: el componente sigue montado y el temporizador de 500ms dispara con normalidad mientras el
usuario lee la tarjeta de transición. Para que el flush fuera load-bearing al encadenar habría que
pulsar «Continuar» **dentro de los 500ms** de llegar a la última página — y «Continuar» es solo ratón
(el handler de teclado no lo activa). O sea: el write del encadenado está a salvo **con y sin** el
flush. Por eso el tercer camino sin medir no deja un agujero en RD-05.

Lo que sí hace trabajo real ahí es el ref `capituloListo` (`:189`, `:202`): sin él, durante la ventana
de carga del capítulo B el efecto del debounce armaría `{B, páginaVieja}` y escribiría la página del
capítulo A en el progreso de B. Está guardado **dos veces** (`capituloListo.current !== chapter.source_id`
y `progreso.capitulo !== capitulo`, `:206`). Correcto por lectura; tampoco medido, y tampoco hace falta
que lo esté: su fallo no afecta a ningún criterio de esta fase.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `apps/backend/nyanko_api/sources/local_archive.py` | CBZ/ZIP/carpeta + ComicInfo + orden natural | ✓ VERIFIED | 337 líneas. CR-01 cerrado de verdad |
| `apps/backend/nyanko_api/sources/contract.py` | `page_bytes` + `SOURCE_API_VERSION` 2 | ✓ VERIFIED | D-16/D-17 |
| `apps/backend/nyanko_api/sources/engine.py` | Cache + taxonomía | ✓ VERIFIED | CR-03 + WR-03(F2) cerrados |
| `apps/backend/nyanko_api/main.py` | Ruta antes del mount + API `/api/manga/*` | ✓ VERIFIED | `:1517` < `:1542` |
| `apps/backend/nyanko_api/database.py` | Esquema v9, RTL por defecto | ✓ VERIFIED | `:277-300` |
| `apps/desktop/src/ReaderView.tsx` | 3 modos, navegación, encadenado, ventana, **flush del progreso** | ✓ VERIFIED | 534 líneas, sin stubs. El flush (`:201-211`) con deps sin `paginaActual`: el debounce sobrevive |
| `apps/desktop/src/readerWindow.ts` | `decodeWindow` / `pagePairs` | ✓ VERIFIED | Separado del componente para ser probable sin DOM |
| `apps/desktop/scripts/reader-fit.mjs` | Gates de layout + **RD-05** | ✓ VERIFIED | 12 casos. El de RD-05 muerde (A/B propio). ⚠️ Ver la nota de fragilidad |
| `apps/desktop/scripts/reader-rss.mjs` | Gate RD-09 que muerde | ✓ VERIFIED | Auditado como código: no puede dar falso verde ni medir la nada |
| `apps/desktop/electron.vite.config.ts` | CSP sustituida en el build | ✓ VERIFIED | Verificado en el output |

### Data-Flow Trace (Level 4)

| Artifact | Data | Source | ¿Datos reales? | Status |
|----------|------|--------|----------------|--------|
| `ReaderView` | `paginas` | `api.mangaPages` → `/api/manga/pages` → `SourceEngine.pages` → disco/ZIP | Sí — 200 páginas reales a 2000×3000 en el harness | ✓ FLOWING |
| `ReaderView` | `preferencias` | `api.readerPrefs` → `reader_prefs` (SQLite) | Sí — round trip con test | ✓ FLOWING |
| `ReaderView` | `paginaActual` | `api.readerProgress` → `reader_progress` | **Sí — el viaje completo medido en Electron real**: se escribe al cerrar y se relee al reabrir | ✓ FLOWING |
| `<img src>` | `pagina.url` | `_page_url` relativo → `normalizeAssetUrls` | Sí — el harness exige `naturalWidth===2000` | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| **Reanudar: cerrar de golpe → reabrir** | `npm run test:reader-fit` | cierra en 7, reabre en 7 | ✓ PASS |
| **El gate de reanudar MUERDE** | ídem, con el flush desactivado | reabre en 5, exit 1; los otros 11 verdes | ✓ PASS |
| El reader no se pasa del techo de RSS | `npm run test:reader-rss` | 160.06 MB / pico 248.81 vs 500 | ✓ PASS |
| La ventana de decodificación no supera 5 | `npm run test:reader` | 4/4 | ✓ PASS |
| Los 3 ajustes × 3 modos maquetan bien | `npm run test:reader-fit` | 12/12, lomo 0px | ✓ PASS |
| La suite backend | `pytest -q` | 461 passed | ✓ PASS |

### Requirements Coverage

| REQ | Descripción | Status | Evidencia |
|-----|-------------|--------|-----------|
| RD-01 | CBZ/ZIP/carpeta con orden natural | ✓ SATISFIED | Criterio 1. CBR → 415 «conviértelo a CBZ» **es lo especificado** |
| RD-02 | RTL / LTR / vertical | ✓ SATISFIED | `test:reader-fit` 12/12 |
| RD-03 | Modo por serie | ✓ SATISFIED | PK `(source_name, series_id)` + test de aislamiento |
| RD-04 | Navegación de escritorio | ✓ SATISFIED | 400 pulsaciones reales en el harness. ⚠️ WR-01(F3): `preventDefault()` en `onWheel` es no-op (React registra `wheel` pasivo) |
| RD-05 | Reanudar por página | ✓ SATISFIED | **Gate medido con A/B propio.** Era el único hueco de la pasada anterior |
| RD-06 | Encadenado + evento | ✓ SATISFIED | UAT test 1 pasado |
| RD-07 | Doble página con offset | ✓ SATISFIED | `pagePairs` + lomo 0px medido |
| RD-08 | ComicInfo manda | ✓ SATISFIED | 3 tests, incluido XXE/billion-laughs |
| RD-09 | Techo de memoria | ✓ SATISFIED | **160 MB / pico 249 vs 500, medido aquí** |

Cero requisitos huérfanos: los 9 RD del ROADMAP están reclamados por los planes 03-01..03-07.

### Anti-Patterns Found

| File | Pattern | Severity | Impact |
|------|---------|----------|--------|
| — | `TBD` / `FIXME` / `XXX` | — | **Ninguno.** Barrido limpio sobre los ficheros de la fase, incluidos los dos que cambiaron |
| — | `TODO` / `HACK` / `PLACEHOLDER` | — | **Ninguno** |
| `local_archive.py:40`, `engine.py:77` | `ponytail:` | ℹ️ Info | Simplificaciones deliberadas, con techo y camino de mejora escritos. Es el patrón que el repo pide |

### Dos cosas que encontré yo y no están en ningún documento

Ninguna bloquea la fase. Las dejo escritas porque son exactamente la clase de cosa por la que esta fase
ya pagó dos falsos verdes.

**1. El gate de RD-05 muerde hoy, pero le falta un assert para no degenerar mañana.**
`medirReanudar` asierta la precondición de `asentada` (`reader-fit.mjs:771`: «un caso que no mide nada no
puede dar verde») pero **no asierta que `esperada !== asentada`**. Si en una máquina más lenta los 120ms
de `PASAR_Y_CERRAR_RAPIDO` no bastan para que React commitee la pasada de página, `esperada` valdría 5, la
BD ya tiene un 5 escrito de la fase de asentamiento, `reanudada` sería 5, y **`ok = true` sin haber
ejercitado el flush**: verde por accidente. Hoy no ocurre —mi A/B lo prueba empíricamente: `esperada`=7 ≠
`asentada`=5—, pero el caso degenerado sería silencioso. Un `if (esperada === asentada) throw` en el mismo
estilo del assert que ya está al lado lo haría ruidoso. Una línea.

**2. Salir de la app entera dentro de los 500ms de pasar página sigue perdiendo esa página.**
No hay ningún `beforeunload` en el renderer (grep: cero), y destruir la ventana no corre cleanup de React,
así que **ni el debounce ni el flush disparan**. Con `close_to_tray` activo no pasa nada: `electron/main/index.ts:55-60`
hace `win.hide()` y el renderer sobrevive, así que el debounce escribe. Pero el defecto es
`close_to_tray: false` (`native.ts:73`), y ahí un Alt+F4 justo tras pasar página cuesta una página. No lo
llamo gap: es mucho más estrecho que WR-02 (que se comía el camino de salida **normal** — Escape o el botón
cerrar, que es como todo el mundo sale de un lector), cuesta una sola página, y no se arregla con ningún
cleanup de `useEffect` — necesitaría un `beforeunload` con escritura síncrona. Es de la misma clase que los
6 Warning aceptados.

### Human Verification Required

**Ninguna.** El único ítem de la pasada anterior —RD-05, reanudar— está cerrado con medición, no con
narración: gate en Electron real, por el camino del usuario, con A/B propio que demuestra que muerde.

## Gaps Summary

**No hay gaps, y ahora RD-05 tampoco es una excepción.** El objetivo de la fase — «Nyanko lee mi colección
de CBZ», con cero red y cero rate limits en la superficie de depuración — está cumplido y **medido**:

- Los **7 criterios del ROADMAP verificados**, los 9 RD satisfechos, cero requisitos huérfanos.
- **461 passed** en mi propia ejecución del backend; los 4 gates de Electron verdes en mi propia ejecución.
- La verdad que la pasada anterior dejó abierta —reanudar— **ya no se firma sobre presencia**: se firma
  sobre un viaje medido (pasar página → cerrar dentro de los 500ms → reabrir) cuyo gate **he puesto rojo yo
  a propósito** para comprobar que tiene dientes, y cuyo rojo cae solo donde dice.
- La sospecha con la que se me mandó a mirar —«el gate solo ejercita uno de los tres caminos»— **es cierta
  y la confirmo**: mide Escape. Pero el segundo camino es *la misma referencia de función* que Escape, y el
  tercero (encadenar) no deja agujero porque la pantalla de transición no desmonta y el debounce dispara
  solo. El flush ahí es un cinturón sobre una ventana inalcanzable.

**Se quedan abiertos a propósito** (no los doy por cerrados): los 6 Warning y 2 Info de `03-REVIEW.md` — de
los cuales WR-01 (rueda pasiva), WR-03 (`series_id` sobre un `library_folders.id` AUTOINCREMENT: quitar y
volver a añadir la carpeta huérfana todo el progreso) y WR-04 (carpeta con imágenes **y** subcarpetas se
traga sus subcarpetas) son los que más muerden en un uso real —, WR-08 de la Fase 2, el desajuste de 34px en
vertical (`slot vacio 720` vs `scrollport 686`, visible en la salida del gate) y el comparador del
IntersectionObserver por `intersectionRatio`. CBR **no es un gap**: es la decisión de licencia escrita en
REQUIREMENTS.md y reafirmada por el usuario, y el 415 es el comportamiento especificado. WR-02 **sí** se
cierra: era el que estaba vivo en el camino de RD-05.

---

_Verified: 2026-07-16T21:38:01Z_
_Verifier: Claude (gsd-verifier) — re-verificación_
_Todos los gates ejecutados en este proceso. Ningún número copiado de un SUMMARY. El A/B de RD-05, hecho a mano y revertido (`git status` limpio)._
</content>
</invoke>
