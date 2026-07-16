---
quick_id: 260716-boe
description: Vertical sin saltos de scroll (UAT #4) + contador de pagina siempre visible (UAT #5)
date: 2026-07-16
status: complete
commits:
  - a395ea6 test(quick-boe): measure the vertical scroll jump in a real Electron (UAT #4)
  - b62a83f fix(quick-boe): dejar que el navegador ancle el scroll vertical + contador siempre visible
key_files:
  created: []
  modified:
    - apps/desktop/scripts/reader-fit.mjs
    - apps/desktop/src/styles.css
    - apps/desktop/src/ReaderView.tsx
---

# Quick 260716-boe — Vertical sin saltos + contador visible

## Que se hizo

Los hallazgos #4 y #5 del UAT manual de la fase 03. **Nota de proceso**: el executor se corto por
limite de sesion justo despues de medir y antes de correr los gates; el orquestador continuo desde
ahi — corrio los gates, hizo el #5 (que el executor no llego a tocar) y cerro los artefactos.

## #4 — El salto de scroll en vertical

**Causa raiz, MEDIDA (no razonada):** el scroller montaba y soltaba paginas por diseno (la ventana
de decodificacion), y a ajuste «ancho» una pagina real mide **1635px** mientras su slot vacio solo
reserva `min-height: 100vh` = **720px**. O sea que cada montaje cambia la altura en **915px**
(1635-720). El navegador tiene una funcion nativa para compensar exactamente eso — el anclaje de
scroll — y `.reader-vertical` la desactivaba a proposito con `overflow-anchor: none`.

**El arreglo es una declaracion MENOS**: borrar `overflow-anchor: none`. Nada mas.

**De cuatro sospechosos, solo uno era el culpable** — y los otros tres NO se tocaron:

| # | Sospechoso | Veredicto |
|---|---|---|
| S1 | Desajuste de 34px (`100vh`=720 vs scrollport real 686) | No contribuye al SALTO. Un desajuste constante desalinea, no salta. Sigue en pie como posible desalineacion; no se toca. |
| S2 | El slot crece al montar la img (720 -> 1635) | **Es la fuente del cambio de altura** — pero es el diseno del scroller, no el bug. |
| S3 | `overflow-anchor: none` | **LA CAUSA**: desactivaba la compensacion nativa de S2. |
| S4 | El IO ordena por `intersectionRatio` (favorece al slot vacio: 0.95 vs 0.42) | Real como asimetria, pero el gate quedo verde sin tocarlo. No se toca. |

**El parte del usuario era impreciso en un punto** (igual que paso con «ancho» en el #3): decia
«hacia arriba», pero la medicion muestra **915px hacia arriba Y -915px hacia abajo** — bajando
tambien se desmonta una pagina de ARRIBA del ancla. El sintoma era mas amplio de lo percibido.

## #5 — El contador de pagina

Existia (`ReaderView.tsx:441`) pero vivia DENTRO del `<header>` de controles, que se alterna con un
clic: ocultar el chrome para leer te costaba saber en que pagina ibas. Sacado del header a posicion
absoluta abajo-izquierda, discreto y siempre visible. **Precedente en el propio fichero**:
`.reader-notice` ya vivia fuera del header por la misma razon. Abajo-IZQUIERDA para no chocar con el
aviso, que ocupa abajo-derecha. Sin preferencia configurable ni modo nuevo (YAGNI).

## La trampa que se esquivo — habria sido el tercer falso verde de la fase

`reader-fit.mjs` fijaba `TOTAL_PAGINAS = 4`, y `decodeWindow` devuelve TODAS las paginas cuando
`total <= MAX_LIVE_PAGES` (5). Con 4 paginas **no se monta ni se desmonta nada nunca**: el #4 es
estructuralmente imposible de reproducir ahi. Un gate escrito sobre ese harness habria salido verde
midiendo NADA. Subido a 12 (la ventana se asienta en 6..10, con margen a los dos lados).

## Verificacion — numeros reales, corridos por el orquestador

| Gate | Resultado |
|---|---|
| `test:reader-fit` | **11/11 OK, exit 0** (9 de paginado + 2 de vertical) |
| El gate del #4, VISTO EN ROJO | Con `overflow-anchor:none` puesto: `915, 0, 915` arriba y `-915, -915` abajo, **exit 1** |
| `test:reader-rss` (RD-09) | **exit 0** — 136.37 MB, pico 225.36, techo 500 |
| `check` (tsc) | limpio |
| `test:reader` / `test:csp` / `test:native` / `test:prefs` | verdes |
| pytest backend | **461 passed** = baseline exacto |

El gate se vio en ROJO antes de darlo por bueno, mismo estandar que el #3. `MAX_LIVE_PAGES` (5) y
`TECHO_RSS_MB` (500) **sin tocar**: el diff no los roza.

## Pendiente

- **UAT manual**: que el scroll vertical a ajuste «ancho» ya no salte, y que el contador se vea al
  ocultar los controles.
- S1 (los 34px) y S4 (el comparador del IO) siguen en pie como posibles desalineaciones menores. No
  se tocaron porque el gate quedo verde sin ellos: arreglar cuatro cosas donde el bug era una es como
  se rompen las otras tres.

## Self-Check: PASSED
