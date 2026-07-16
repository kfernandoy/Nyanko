---
status: awaiting_human_verify
trigger: "El ajuste «alto» (fit-height) no muestra la pagina entera en el reader paginado LTR/RTL, y lo mismo con doble pagina. El ajuste «ancho» si funciona."
created: 2026-07-16
updated: 2026-07-16
source: UAT manual de la fase 03, hallazgo #3
---

# Debug: el ajuste «alto» corta la pagina

## Symptoms

- **Expected**: con Ajuste = «Alto» (fit-height) la pagina se ve ENTERA, acotada a la altura del stage.
- **Actual**: no se ve la pagina entera — queda cortada. Pasa en paginado LTR y RTL, y tambien con
  doble pagina activada. Con Ajuste = «Ancho» SI funciona.
- **Errors**: ninguno. Es puramente visual, no hay excepcion ni log.
- **Timeline**: encontrado en el UAT manual del 2026-07-16. **NO es regresion del trabajo de hoy**:
  el quick 260716-6ba solo toco la rama PAGINADA del render (montar solo el grupo visible) y borro
  las reglas `.reader-page--preload*`; las reglas de `--visible` y de ajuste no se tocaron. Se
  presume preexistente desde la 03-06, que entrego los tres modos.
- **Reproduction**: `npm run dev` → anadir carpeta de biblioteca con un CBZ → vista `local-manga` →
  abrir un capitulo → selector «Ajuste» = «Alto». Comparar con «Ancho».

## Current Focus

hypothesis: "CONFIRMADA Y MEDIDA — `.reader-pages{height:100%}` no resuelve porque su bloque
contenedor `.reader-paged{display:grid;place-items:center}` deja al item SIN estirar y con altura
indefinida. Un porcentaje contra una altura indefinida degrada: `height:100%` de la img pasa a auto
y `max-height:100%` pasa a none. La img se pinta al alto derivado de su aspecto (1650px) dentro de
un stage de 686px y `.reader-stage{overflow:hidden}` la recorta."
test: "Medido con scripts/reader-fit.mjs (Electron real + sidecar, bundle construido)."
expecting: "RESUELTO — ver Resolution. Pendiente de confirmacion humana del sintoma visual."
next_action: "Esperar a que el usuario confirme el ajuste «alto» en su flujo real."

## Evidence

- timestamp: 2026-07-16 — CSS relevante, leido del arbol actual (`apps/desktop/src/styles.css`):
  ```
  .reader { position: relative; height: 100vh; overflow: hidden; }
  .titlebar + .reader { height: calc(100vh - 34px); }
  .reader-stage { position: relative; width: 100%; height: 100%; overflow: hidden; }
  .reader-paged { display: grid; place-items: center; }
  .reader-pages { position: relative; width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; transform-origin: center; }
  .reader-page--visible { flex: 1 1 0; height: 100%; min-width: 0; display: flex; align-items: center; justify-content: center; overflow: clip; }
  .reader-page--visible img { display: block; max-width: 100%; max-height: 100%; object-fit: contain; }
  .reader-fit-height .reader-page--visible img { width: auto; height: 100%; }
  .reader-fit-width  .reader-page--visible img { width: 100%; height: auto; }
  ```

- timestamp: 2026-07-16 — **MEDICION ANTES DEL ARREGLO** (`scripts/reader-fit.mjs`, Electron real,
  ventana 1100x720, pagina 2000x3000, `getBoundingClientRect()`):
  ```
  ltr / ajuste width     stage 1100x686 | pages 1100x1650 | slots 1100x1650 | img 1100x1650
  ltr / ajuste height    stage 1100x686 | pages 1100x1650 | slots 1100x1650 | img 1100x1650
  ltr / ajuste original  stage 1100x686 | pages 2000x3000 | slots 2000x3000 | img 2000x3000
  rtl / ajuste height    stage 1100x686 | pages 1100x1650 | slots 1100x1650 | img 1100x1650
  ltr doble / height     stage 1100x686 | pages 1100x825  | slots 550x825 + 550x825 | img 550x825 + 550x825
  ```
  checked: los rects de `.reader-stage`, `.reader-pages`, `.reader-page--visible` y la img.
  found: **`stage` mide 686 de alto (DEFINIDO) pero `pages` mide 1650.** El `height:100%` de
  `.reader-pages` NO resuelve: degrada a auto y el contenedor crece hasta el alto del contenido.
  implication: **la cadena de alturas se rompe exactamente en `.reader-pages`**, o sea en el paso
  «item de `.reader-paged{display:grid; place-items:center}`». Queda decidida la ambiguedad que
  bloqueaba al orquestador: el stretch por defecto de las pistas auto NO salva la altura, porque
  `align-content:stretch` estira la PISTA pero `place-items:center` deja al ITEM sin estirar. La
  lectura correcta era la segunda. **Nota**: `pages` mide 2000 de ANCHO en «original», o sea que el
  grid rompia tambien la cadena de anchuras; en los otros ajustes coincidia con el stage por
  casualidad (la pista auto se dimensionaba al contenido, que ya era <= 1100).

- timestamp: 2026-07-16 — **HALLAZGO QUE CORRIGE EL PARTE DEL UAT**: antes del arreglo, «ancho» y
  «alto» pintaban la img EXACTAMENTE IGUAL (1100x1650 los dos). No son dos comportamientos, son el
  MISMO bug.
  checked: contraste entre los tres ajustes en la misma medicion.
  found: con la altura indefinida, «alto» degrada `height:100%`→auto→alto natural 3000, y `width:auto`
  →2000 lo clampa `max-width:100%` (el ANCHO si es definido: 1100) → el aspecto recalcula a 1100x1650.
  Que es, punto por punto, lo que da «ancho». «Ancho» sobrevive porque su clamp cae en el eje DEFINIDO
  y ademas su `max-height:100%` degrada a none, que es justo lo que necesita para llenar el ancho.
  implication: el usuario percibe «ancho funciona» porque llenar el ancho es lo que «ancho» debe hacer,
  y «alto no funciona» porque le sale un «ancho» disfrazado. Un unico eslabon indefinido explica los
  dos sintomas. Esto es lo que obliga a que el arreglo de la cadena NO cambie «ancho» (ver Resolution).

- timestamp: 2026-07-16 — **MEDICION DESPUES DEL ARREGLO** (mismo harness, tras `npm run build`):
  ```
  ltr / ajuste width     stage 1100x686 | pages 1100x686 | slots 1100x686 | img 1100x1650
  ltr / ajuste height    stage 1100x686 | pages 1100x686 | slots 1100x686 | img 457.33x686
  ltr / ajuste original  stage 1100x686 | pages 1100x686 | slots 1100x686 | img 2000x3000
  rtl / ajuste height    stage 1100x686 | pages 1100x686 | slots 1100x686 | img 457.33x686
  ltr doble / height     stage 1100x686 | pages 1100x686 | slots 550x686 + 550x686 | img 457.33x686 + 457.33x686
  ```
  found: `pages` ya calca al stage (686). «Alto» pinta 457.33x686 = la pagina ENTERA usando toda la
  altura. Doble pagina, dos paginas enteras (914px de 1100 disponibles). **«Ancho» sigue en 1100x1650,
  identico al numero de antes del arreglo** → no se ha tocado. «Original» sigue en 2000x3000.

- timestamp: 2026-07-16 — **EL GATE FALLA CON EL BUG PUESTO** (reintroduje `.reader-paged{display:grid;
  place-items:center}`, reconstrui y corri el harness): los 9 casos en rojo, `EXIT=1`, con el motivo
  `.reader-pages mide 1100x1650 y deberia calcar el stage (1100x686)`. Restaurado despues.
  implication: la cobertura es real, no un verde de adorno. Esta fase ya se comio DOS falsos verdes
  (el harness de RD-09 imprimiendo FALLO y saliendo 0; el test de cache de CR-03 verde con el bug
  delante), asi que el gate se ha visto en ROJO antes de darlo por bueno.

## Eliminated

- hypothesis: "`.titlebar + .reader` no casa, asi que `.reader` se queda en 100vh mientras el
  titlebar le come 34px, y la pagina se sale por abajo."
  reason: **DESCARTADA leyendo `App.tsx:1156-1168`**. La estructura es
  `<>{isNative && <Titlebar />}{readerChapter ? <ReaderView/> : <div className="app-shell">}</>`,
  o sea que `<div class="titlebar">` y `<section class="reader">` SI son hermanos adyacentes cuando
  el reader esta abierto: el selector casa y `.reader` recibe `calc(100vh - 34px)`. Correcto.
  **CONFIRMADO ADEMAS POR MEDICION**: el stage mide 686 = 720 - 34. El selector casa.

- hypothesis: "El stretch por defecto de las pistas auto de grid (`align-content:normal` ~ `stretch`)
  hace DEFINIDA la altura de la fila, asi que `.reader-pages{height:100%}` resuelve y la causa esta
  en otro sitio."
  reason: **DESCARTADA POR MEDICION**: `pages` mide 1650 con el stage en 686. `align-content:stretch`
  estira la PISTA, pero `place-items:center` fija `align-self:center` en el ITEM, que por tanto no se
  estira y conserva altura indefinida. El porcentaje no resuelve contra ella.

## Resolution

root_cause: |
  `.reader-paged { display: grid; place-items: center; }` convertia `.reader-pages` en un item de
  grid centrado. `place-items:center` implica `align-self:center`, o sea que el item NO se estira y
  su altura queda INDEFINIDA (que la pista auto se estire es irrelevante: estira la pista, no el
  item). Como `.reader-pages{height:100%}` no puede resolver contra una altura indefinida, degrada a
  auto y la indefinicion se propaga hasta la img: alli `height:100%` degrada a auto y —lo decisivo—
  `max-height:100%` degrada a `none`, con lo que desaparece el unico tope que acotaba la pagina al
  stage. La img se pinta a 1650px de alto dentro de un stage de 686 y `.reader-stage{overflow:hidden}`
  recorta el resto. «Ancho» parecia sano porque su clamp util (`max-width:100%`) cae en el eje de
  ANCHURAS, que si era definido, y porque necesita precisamente el `max-height:none` que la
  degradacion le regalaba.

fix: |
  Dos declaraciones en `apps/desktop/src/styles.css`, ninguna linea de TSX:
  1. **Borrada** la regla `.reader-paged { display: grid; place-items: center; }`. El stage paginado
     vuelve a ser un bloque normal, asi que `.reader-pages` resuelve su `height:100%` contra la altura
     definida de `.reader-stage` (686) y la cadena entera vuelve a ser definida. El grid no aportaba
     centrado alguno: `.reader-pages` ya centra sus paginas con `display:flex; align-items:center;
     justify-content:center`. Era redundante Y era la causa. La clase `reader-paged` se deja en el TSX
     (marca de estado, hermana de `reader-vertical`) y el comentario que explica la trampa vive justo
     donde alguien reintroduciria el grid.
  2. **Anadido `max-height: none`** a `.reader-fit-width .reader-page--visible img`. Con la cadena ya
     definida, el `max-height:100%` de la regla base pasaria a MORDER y `object-fit:contain` apaisaria
     «ancho» hasta ~457px: llenar el ancho es lo que «ancho» significa. Hasta ahora ese `none` lo
     ponia la degradacion por accidente; ahora es explicito. Sin este punto, arreglar «alto» habria
     roto «ancho» de rebote — y el alcance de esta sesion es SOLO el hallazgo #3.

verification: |
  - `npm run test:reader-fit` (nuevo, `scripts/reader-fit.mjs`): 9/9 OK, exit 0. Y **visto en ROJO**
    (9/9 FALLO, exit 1) reintroduciendo el grid a proposito.
  - `npm run check` (tsc --noEmit): limpio.
  - `npm run test:reader`: 4/4.
  - `npm run test:reader-rss` (gate de RD-09): **exit 0** — 140.71 MB finales, pico 237.75 MB contra
    el techo de 500. `MAX_LIVE_PAGES` (5) y `TECHO_RSS_MB` (500) intactos. El arreglo no puede mover
    el RSS: el ajuste por defecto es «ancho» y su geometria de img es identica antes y despues
    (1100x1650 medido en ambos); lo unico que encoge son contenedores vacios (1650→686), que no
    rasterizan.
  - `cd apps/backend && .venv/Scripts/python.exe -m pytest -q`: **461 passed** = baseline exacta.

files_changed:
  - apps/desktop/src/styles.css: borrada la regla grid de `.reader-paged`; `max-height:none` en el ajuste «ancho».
  - apps/desktop/scripts/reader-fit.mjs: NUEVO. Gate de layout que mide los rects en Electron real.
  - apps/desktop/package.json: script `test:reader-fit`.

## Notes

- **La cobertura anti-regresion es `npm run test:reader-fit`.** Mide con `getBoundingClientRect()` en
  un Electron de verdad los tres ajustes x {LTR, RTL, doble pagina} = 9 casos. Su asercion central no
  es sobre la img sino sobre la CADENA: `.reader-pages` y cada hueco de pagina tienen que calcar la
  altura del stage. Esa invariante es independiente del ajuste y se rompe en cuanto alguien
  reintroduce un eslabon de altura indefinida, que es la clase de bug que fue este. Ojo: el harness
  carga `out/renderer/index.html`, o sea **hay que `npm run build` antes o mides codigo viejo**.
- Sobre las aserciones del gate: «ancho» se comprueba como `img.w == hueco.w` (llenar el ancho) y NO
  se le exige caber en el stage; exigirselo seria pedirle que se comporte como «alto» y congelaria
  como «correcta» justo la regresion que el `max-height:none` evita. «Original» solo se comprueba a
  tamano natural: desbordar es su definicion.
- **Evidencia para el hallazgo #4 (saltos de scroll en vertical), NO arreglado aqui (fuera de
  alcance)**: la rama vertical tiene el mismo desajuste de 34px que se descarto en paginado, pero de
  verdad. `.reader-vertical-slot{min-height:100vh}`, `.reader-page--vertical{min-height:100vh}` y
  `.reader-fit-height .reader-page--vertical img{height:100vh}` miden **100vh (720px)**, mientras que
  el scrollport real es `.reader` = `calc(100vh - 34px)` = **686px**. Cada slot es 34px mas alto que
  la ventana visible, asi que `scrollIntoView({block:'start'})` y los thresholds del IntersectionObserver
  (que usa `root: .reader-vertical`) trabajan sobre una geometria que no casa con la que se ve: es
  una causa candidata muy fuerte de los saltos. Empezar por ahi cuando se ataque el #4.
- El arreglo de esta sesion NO toca la rama vertical: `.reader-paged` y `.reader-page--visible` son
  exclusivos del paginado (vertical usa `.reader-page--vertical`).
- No tengo evidencia nueva sobre el hallazgo #5 (contador de pagina).
