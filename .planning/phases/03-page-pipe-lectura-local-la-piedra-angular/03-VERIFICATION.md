---
phase: 03-page-pipe-lectura-local-la-piedra-angular
verified: 2026-07-16T21:01:36Z
status: human_needed
score: 6/7 must-haves verified
behavior_unverified: 1
overrides_applied: 0
behavior_unverified_items:
  - truth: "ROADMAP criterio 3 / RD-05: se reanuda por la pagina donde se dejo"
    test: |
      Abre un capitulo, ve a la pagina 50, ESPERA >1s, cierra con Escape y reabre el
      mismo capitulo. Repite cerrando INMEDIATAMENTE (<500ms) tras pasar de pagina.
    expected: |
      Caso 1 (esperando): reabre en la pagina 50.
      Caso 2 (cierre inmediato): reabre en la 49 — WR-02 conocido y ACEPTADO como
      warning. Si el caso 1 tambien falla, RD-05 no se cumple y es un gap real.
    why_human: |
      La cadena esta entera y cada eslabon verificado por separado (DB + API por
      test_preferencias_progreso_y_evento_hacen_round_trip_sin_persistir_urls; la
      lectura en el mount por codigo, ReaderView.tsx:82,91-94), pero NADIE ha
      ejercitado el viaje completo cerrar→reabrir. No hay infra de tests de
      componentes React y montarla es una dependencia nueva. Ademas WR-02 es un
      defecto VIVO justo en el camino de escritura: el debounce de 500ms se cancela
      en el cleanup del efecto (ReaderView.tsx:185-192) sin flush al desmontar. El
      propio 03-06-SUMMARY D2 lo admite: «el paneo y el progreso/reanudar NO se
      confirmaron uno a uno en la UAT».
human_verification:
  - test: |
      Abre un capitulo, ve a la pagina 50, espera >1s, cierra con Escape y reabre.
      Repite cerrando inmediatamente (<500ms) tras pasar de pagina.
    expected: |
      Con espera: reabre en la 50. Con cierre inmediato: reabre en la 49 (WR-02,
      aceptado). Si con espera tampoco reanuda, RD-05 es un gap real.
    why_human: |
      Unico eslabon de la fase que ningun test ni la UAT ha ejercitado nunca, y con
      un defecto conocido (WR-02) en ese mismo camino.
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
**Verified:** 2026-07-16T21:01:36Z
**Status:** human_needed
**Re-verification:** No — verificación inicial

## Cómo se verificó esto

**Ningún número de este informe sale de un SUMMARY.** Todos los gates se ejecutaron en este proceso:

| Gate | Comando | Resultado medido aquí |
|------|---------|----------------------|
| Suite backend | `pytest -q` (desde `apps/backend`) | **461 passed** en 94.76s |
| Typecheck | `npm run check` | limpio |
| Ventana de decodificación | `npm run test:reader` | **4/4** |
| CSP | `npm run test:csp` | **6/6** |
| Cadena de alturas | `npm run build && npm run test:reader-fit` | **11/11** |
| **RD-09 (RSS real)** | `npm run build && npm run test:reader-rss` | **159.08 MB final, pico 252.75 MB vs techo 500 → exit 0** |
| CSP en el build | `grep` sobre `out/renderer/index.html` | CSP presente en el HTML **construido**, no solo en el fuente |

Esta fase se comió dos falsos verdes, así que los tres harnesses se auditaron **como código** antes
de creerles:

- **`reader-rss.mjs` es honesto ahora**: `codigoSalida` nace en `1` y solo pasa a `0` con la medición
  delante (línea 447); el `app.on("window-all-closed", () => {})` (línea 39) mata la carrera que hacía
  imprimir «FALLO» y salir 0. Y **no puede medir la nada**: `esperarPagina` exige `imagenes.length > 0`
  y que cada `<img>` esté `complete` con `naturalWidth === 2000 && naturalHeight === 3000` antes de
  muestrear (líneas 331-344). El bug del harness de layout (4 páginas contra una ventana de 5) no
  puede repetirse aquí.
- **El test del cache de CR-03 ya no miente**: existe `test_dos_peticiones_sirven_el_cache_cuando_la_fuente_falla`
  en `test_manga_api.py` — dos GET por la **superficie HTTP**, que es justo lo que el review exigía
  frente al test viejo que reusaba un engine a mano.

## Goal Achievement

### Observable Truths (los 7 criterios del ROADMAP)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | CBZ / ZIP / carpeta se leen en orden natural (`2` antes que `10`); `ComicInfo.xml` manda sobre el nombre | ✓ VERIFIED | `_natural_key` (`local_archive.py:56-60`) usado en los **tres** caminos: capítulos (:100), páginas sueltas (:145) y miembros del ZIP (:178) — una sola función de orden. ComicInfo manda: `:109` lee `Number` y `:124-128` solo cae al nombre `if number_text is None`. Tests: `test_archivo_local_iguala_zip_y_carpeta_en_orden_natural`, `test_comic_info_del_cbz_manda_sobre_el_nombre`, `test_comic_info_malformado_degrada_al_nombre`, `test_comic_info_peligroso_o_desmedido_no_se_parsea` |
| 2 | Tres modos (RTL por defecto, LTR, vertical), modo recordado **por serie** y superviviente al reinicio; doble página con offset manual | ✓ VERIFIED | Los 3 modos en `ReaderView.tsx:406-408` + clases `reader--${mode}`. **RTL por defecto en el ESQUEMA** (`database.py:280`: `mode TEXT NOT NULL DEFAULT 'rtl'`), no duplicado en el cliente (`ReaderView.tsx:87-88`: PUT vacío y decide SQLite). Por serie: PK `(source_name, series_id)`, `test_preferencias_se_aislan_por_serie_y_conservan_actualizaciones_parciales`. `test:reader-fit` **11/11** pinta los 3 modos × 3 ajustes. Doble página + offset: `pagePairs`, `test:reader` 4/4, lomo **0px** medido. ⚠️ Ver WR-03 |
| 3 | Navegación de escritorio completa **+ se reanuda por la página donde se dejó** | ⚠️ PRESENT_BEHAVIOR_UNVERIFIED | **Navegación: verificada de sobra.** Teclado (`:257-270`: ←/→ con inversión RTL, AvPág/RePág, Espacio, Inicio/Fin), rueda (`:285`), zonas de click (`:332-342`), F11 (`:242-247`), contador (`:459`, **fuera del header** tras UAT #5), 3 ajustes, zoom, paneo. El harness RSS ejercita **400 pulsaciones reales** de AvPág/RePág contra Electron real y lee `.reader-counter` → teclado y contador probados por comportamiento, no por grep. `test:reader-fit` 11/11 prueba los ajustes. **Lo que NO está probado: reanudar.** Ver Human Verification |
| 4 | Encadena capítulo con pantalla de transición, y la transición **emite el evento «capítulo terminado»** | ✓ VERIFIED | `abrirTransicion` (`:155-168`) → pantalla (`:363-389`) → `onChapterChange`. El evento solo en `next` y deduplicado (`eventosEmitidos`, `:158-159`). **UAT test 1 PASADO** por el usuario: encadena y `reading_events` gana UNA fila (no dos). Backend: `test_evento_de_lectura_conserva_el_capitulo_decimal_y_media_id_nulo` (el 12.5 cabe: `chapter REAL`), `test_preferencias_progreso_y_evento_hacen_round_trip_sin_persistir_urls`. D-15 cumplido: la fila se escribe y no la lee nadie |
| 5 | RSS del renderer bajo el número escrito, tras 200 páginas de ida y vuelta | ✓ VERIFIED | **Medido por mí:** `159.08 MB final, pico 252.75 MB` contra techo **500** → exit 0. `MAX_LIVE_PAGES`=5 (`DECODE_BEHIND 2 + 1 + DECODE_AHEAD 2`) y `TECHO_RSS_MB`=500 **sin tocar**: el número baja porque el reader retiene menos, no porque se aflojara el gate. `test:reader-fit` imprime `montadas 6,7,8,9,10` — exactamente 5. Con `DECODE_AHEAD=5` el gate se pone rojo (muerde) |
| 6 | Ninguna URL de página persiste con host o puerto; `/assets/…` relativo resuelto por `normalizeAssetUrls`; la guardia FND-05 sigue verde | ✓ VERIFIED | `_page_url` (`main.py:348-351`) devuelve **relativo**. `normalizeAssetUrls` (`api.ts:207-220`) reescribe cualquier string `/assets/`, y `mangaPages` pasa por `request()` → `:254`. La guardia FND-05 se llama tras las escrituras de ESTA fase: 6 sitios en `test_reader_persistence.py` + `test_manga_api.py:300`. `test_guardia_rechaza_url_absoluta_en_una_tabla_nueva`. **Probado por comportamiento**: el harness RSS carga 200 páginas reales por esta cadena en Electron. Ruta ANTES del mount (`:1517` vs `:1542`, D-04) con `test_la_ruta_de_paginas_esta_antes_del_mount_de_assets`. Traversal cerrado: 8 casos parametrizados (D-05) |
| 7 | Existe una CSP y `webSecurity` sigue en `true` | ✓ VERIFIED | **Comprobado en el HTML CONSTRUIDO** (`out/renderer/index.html`), no solo en el fuente: `default-src 'self'; img-src 'self' http://127.0.0.1:* https: blob: data:; connect-src 'self' http://127.0.0.1:* ws://127.0.0.1:*; style-src 'self' 'unsafe-inline'; script-src 'self'; object-src 'none'; frame-src 'none'; base-uri 'none'; form-action 'none'`. Producción sin `unsafe-inline` ni `unsafe-eval`. `webSecurity:true` + `contextIsolation:true` + `nodeIntegration:false` + `sandbox:true` en las **dos** ventanas. `test:csp` 6/6. **UAT test 2 PASADO**: portadas, HMR y splash intactos |

**Score:** 6/7 truths verified (1 presente y cableada, comportamiento sin ejercitar)

### Las dos desviaciones del texto del ROADMAP — ninguna es un gap

| Criterio | Texto literal | Realidad | Veredicto |
|----------|---------------|----------|-----------|
| 6 | «por el mount `StaticFiles` existente» | Ruta **dinámica** `/assets/pages/{page_id:path}` declarada antes del mount | **Intención cumplida.** D-02 anuló el `_stream/` del ROADMAP y **el propio ROADMAP lo documenta** («Anulado en planificación (D-02)»). Sin caché no existe el bug que el techo describía |
| 7 | `img-src 'self' http://127.0.0.1:* blob: data:` | ...`https: blob: data:` + `connect-src ... ws://127.0.0.1:*` | **Intención cumplida.** H-3 lo predijo: la CSP literal borra todas las portadas (CDN del proveedor) y mata `playbackSocket()`. El texto del criterio tenía un bug; la CSP se escribió corregida. La UAT visual lo confirmó |

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `apps/backend/nyanko_api/sources/local_archive.py` | CBZ/ZIP/carpeta + ComicInfo + orden natural | ✓ VERIFIED | 337 líneas. CR-01 cerrado de verdad |
| `apps/backend/nyanko_api/sources/contract.py` | `page_bytes` + `SOURCE_API_VERSION` 2 | ✓ VERIFIED | D-16/D-17 |
| `apps/backend/nyanko_api/sources/engine.py` | Cache + taxonomía | ✓ VERIFIED | CR-03 + WR-03(F2) cerrados |
| `apps/backend/nyanko_api/main.py` | Ruta antes del mount + API `/api/manga/*` | ✓ VERIFIED | `:1517` < `:1542` |
| `apps/backend/nyanko_api/database.py` | Esquema v9, RTL por defecto | ✓ VERIFIED | `:277-300` |
| `apps/desktop/src/ReaderView.tsx` | 3 modos, navegación, encadenado, ventana | ✓ VERIFIED | 515 líneas, sin stubs |
| `apps/desktop/src/readerWindow.ts` | `decodeWindow` / `pagePairs` | ✓ VERIFIED | Separado del componente para ser probable sin DOM |
| `apps/desktop/scripts/reader-rss.mjs` | Gate RD-09 que muerde | ✓ VERIFIED | Auditado como código: no puede dar falso verde ni medir la nada |
| `apps/desktop/electron.vite.config.ts` | CSP sustituida en el build | ✓ VERIFIED | Verificado en el output |

### Data-Flow Trace (Level 4)

| Artifact | Data | Source | ¿Datos reales? | Status |
|----------|------|--------|----------------|--------|
| `ReaderView` | `paginas` | `api.mangaPages` → `/api/manga/pages` → `SourceEngine.pages` → disco/ZIP | Sí — 200 páginas reales cargadas a 2000×3000 en el harness | ✓ FLOWING |
| `ReaderView` | `preferencias` | `api.readerPrefs` → `reader_prefs` (SQLite) | Sí — round trip con test | ✓ FLOWING |
| `ReaderView` | `paginaActual` | `api.readerProgress` → `reader_progress` | Sí en DB/API; el viaje UI no ejercitado | ⚠️ Ver Human Verification |
| `<img src>` | `pagina.url` | `_page_url` relativo → `normalizeAssetUrls` | Sí — el harness exige `naturalWidth===2000` | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| El reader no se pasa del techo de RSS | `npm run test:reader-rss` | 159.08 MB / pico 252.75 vs 500 | ✓ PASS |
| La ventana de decodificación no supera 5 | `npm run test:reader` | 4/4 | ✓ PASS |
| Los 3 ajustes × 3 modos maquetan bien | `npm run test:reader-fit` | 11/11, lomo 0px | ✓ PASS |
| La CSP llega al HTML construido | `grep out/renderer/index.html` | CSP completa | ✓ PASS |
| La suite backend | `pytest -q` | 461 passed | ✓ PASS |
| Reanudar cerrar→reabrir | — | sin infra de tests de componentes React | ? SKIP → humano |

### Requirements Coverage

| REQ | Descripción | Status | Evidencia |
|-----|-------------|--------|-----------|
| RD-01 | CBZ/ZIP/carpeta con orden natural | ✓ SATISFIED | Criterio 1. CBR → 415 «conviértelo a CBZ» **es lo especificado** (`test_cbr_se_rechaza_sin_intentar_abrirlo`) |
| RD-02 | RTL / LTR / vertical | ✓ SATISFIED | `test:reader-fit` 11/11 |
| RD-03 | Modo por serie | ✓ SATISFIED | PK `(source_name, series_id)` + test de aislamiento |
| RD-04 | Navegación de escritorio | ✓ SATISFIED | 400 pulsaciones reales en el harness; ajustes por `test:reader-fit`. ⚠️ WR-01: `preventDefault()` en `onWheel` es no-op (React registra `wheel` pasivo) → ctrl+rueda zoomea la UI entera |
| RD-05 | Reanudar por página | ⚠️ NEEDS HUMAN | DB+API con test; UI sin ejercitar; WR-02 vivo en ese camino |
| RD-06 | Encadenado + evento | ✓ SATISFIED | UAT test 1 pasado |
| RD-07 | Doble página con offset | ✓ SATISFIED | `pagePairs` + lomo 0px medido |
| RD-08 | ComicInfo manda | ✓ SATISFIED | 3 tests, incluido XXE/billion-laughs |
| RD-09 | Techo de memoria | ✓ SATISFIED | **159 MB / pico 252 vs 500, medido aquí** |

Cero requisitos huérfanos: los 9 RD del ROADMAP están reclamados por los planes 03-01..03-07.

### Anti-Patterns Found

| File | Pattern | Severity | Impact |
|------|---------|----------|--------|
| — | `TBD` / `FIXME` / `XXX` | — | **Ninguno.** Barrido limpio sobre los ficheros de la fase |
| — | `TODO` / `HACK` / `PLACEHOLDER` | — | **Ninguno** |
| `local_archive.py:40`, `engine.py:77` | `ponytail:` | ℹ️ Info | Simplificaciones deliberadas, con techo y camino de mejora escritos. Es el patrón que el repo pide, no deuda oculta |

### Tres notas de STATE.md que la medición contradice

El orquestador pidió comprobar WR-06. Al hacerlo aparecieron **dos notas más ya obsoletas**:

| Nota | Dice | Realidad medida | Veredicto |
|------|------|-----------------|-----------|
| **WR-06** (STATE.md) | «el registry se construye una sola vez en `lifespan`: una carpeta añadida en caliente es invisible hasta reiniciar» | `add_library_folder` (`main.py:2140`) **y** `delete_library_folder` (`:2156`) reconstruyen el registry, y `_source_engine` (`:1106`) deriva el engine de la **identidad** del registry, así que el cache muere con él. Solo existen esos **2** sitios de mutación (grep de `add_library_folder`/`delete_library_folder`) | **OBSOLETA — bórrala** |
| **WR-01** (Fase 2, STATE.md) | «`SourceEngine` no se re-exporta en `sources/__init__.py` (4 líneas)» | **SÍ se re-exporta**: `sources/__init__.py:11` (`from .engine import ... SourceEngine ...`) y está en `__all__`. H-4 del CONTEXT decía que esta fase lo pagaba «gratis, de paso» — se pagó | **OBSOLETA — ciérrala** |
| **WR-08** (Fase 2, STATE.md) | «los `RateLimitedClient` nunca se cierran en el shutdown» | **CIERTA.** El `lifespan` (`main.py:1503-1508`) para watcher/worker/checker/detector y no cierra ningún cliente. Sin `aclose()` en ningún sitio | **SIGUE ABIERTA** → Fase 9 |

### Human Verification Required

#### 1. Reanudar por la página donde se dejó (RD-05)

**Test:** Abre un capítulo, ve a la página 50, **espera >1s**, cierra con Escape y reabre el mismo
capítulo. Luego repite cerrando **inmediatamente** (<500 ms) después de pasar de página.

**Expected:**
- Con espera: reabre en la **50**.
- Con cierre inmediato: reabre en la **49** — es WR-02, conocido y aceptado como warning.
- **Si el primer caso tampoco reanuda, RD-05 no se cumple y esto es un gap real.**

**Why human:** Es el **único eslabón de la fase que nadie ha ejercitado nunca**. Cada capa está
verificada por separado — la DB y la API por `test_preferencias_progreso_y_evento_hacen_round_trip_sin_persistir_urls`,
la lectura en el mount por código (`ReaderView.tsx:82,91-94`) — pero el viaje completo cerrar→reabrir
no lo cubre ningún test, y no hay infra de tests de componentes React (montarla sería una dependencia
nueva). Y no es teoría: **WR-02 es un defecto vivo justo en ese camino de escritura** — el debounce de
500 ms se cancela en el cleanup del efecto (`ReaderView.tsx:185-192`) y no hay flush al desmontar. El
propio `03-06-SUMMARY` D2 lo admite en letra pequeña: *«el paneo y el progreso/reanudar de esta
descripción NO se confirmaron uno a uno en la UAT»*.

Es un minuto de trabajo y cierra el último hueco de la fase.

## Gaps Summary

**No hay gaps.** El objetivo de la fase — «Nyanko lee mi colección de CBZ», con cero red y cero rate
limits en la superficie de depuración — **está cumplido y medido**, no narrado:

- Los **3 Critical están cerrados de verdad**, comprobados contra el código y no contra el parte:
  CR-01 (la frontera archivo/miembro se **deriva** de los datos con `_ARCHIVE_MEMBER_BOUNDARY`, con 5
  tests de regresión incluido el caso `.cbz!` que el review señaló como roto en ambos sentidos),
  CR-02/RD-09 (**159 MB, pico 252, contra 500 — medido aquí**), CR-03 (el engine se memoiza por
  identidad del registry, con un test que va **por HTTP** en vez de reusar un engine a mano).
- La suite backend da **461 passed** en mi propia ejecución, y los 4 gates de Electron están verdes.
- Los 9 defectos de la UAT manual y los 2 checkpoints de la UAT formal están cerrados.

Lo único que impide firmar `passed` es **una verdad presente pero no ejercitada**: reanudar
(RD-05). No la marco `failed` porque el código está entero y cableado en las cuatro capas, y la DB y
la API tienen test. No la marco `verified` porque **presencia no es comportamiento**, y esta fase ya
se comió dos falsos verdes precisamente por firmar mecanismos que nadie había ejecutado — uno de
ellos (el cache de CR-03) llevaba un test verde encima con el bug delante. Firmar RD-05 sobre la
misma clase de evidencia sería repetir el error que esta fase pagó dos veces.

**Se quedan abiertos a propósito** (no los doy por cerrados): los 6 Warning y 2 Info de `03-REVIEW.md`
— de los cuales WR-01 (rueda pasiva), WR-02 (flush del progreso), WR-03 (`series_id` sobre un
`library_folders.id` AUTOINCREMENT: quitar y volver a añadir la carpeta huérfana todo el progreso) y
WR-04 (carpeta con imágenes **y** subcarpetas se traga sus subcarpetas) son los que más muerden en un
uso real —, WR-08 de la Fase 2, el desajuste de 34px en vertical (`slot vacio 720` vs `scrollport 686`,
visible en la salida del gate) y el comparador del IntersectionObserver por `intersectionRatio`.
CBR **no es un gap**: es la decisión de licencia escrita en REQUIREMENTS.md, y el 415 es el
comportamiento especificado.

---

_Verified: 2026-07-16T21:01:36Z_
_Verifier: Claude (gsd-verifier)_
_Todos los gates ejecutados en este proceso. Ningún número copiado de un SUMMARY._
