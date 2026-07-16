---
phase: 260716-boe
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - apps/desktop/scripts/reader-fit.mjs
  - apps/desktop/src/styles.css
  - apps/desktop/src/ReaderView.tsx
  - apps/desktop/src/i18n.tsx
autonomous: false
requirements: [RD-02, RD-09]
must_haves:
  truths:
    - "En vertical + ajuste ancho, montar una pagina POR ENCIMA del viewport no mueve lo que estas mirando: la pagina ancla se desplaza EXACTAMENTE lo que se ha scrolleado, ni un pixel mas."
    - "El mecanismo del salto queda MEDIDO en numeros antes de tocar nada: se sabe cual de los cuatro sospechosos contribuye y cuanto."
    - "Solo se arregla lo que la medicion senala. Un sospechoso que no contribuye se documenta y se deja como esta."
    - "El contador de pagina se ve con el chrome oculto: `controlesVisibles=false` ya no lo oculta."
    - "npm run test:reader-rss sigue saliendo 0, con MAX_LIVE_PAGES=5 y TECHO_RSS_MB=500 SIN TOCAR."
    - "npm run test:reader-fit sigue verde en los 9 casos de paginado: arreglar vertical no rompe el ajuste «alto» del #3."
  artifacts:
    - apps/desktop/scripts/reader-fit.mjs
    - apps/desktop/src/styles.css
    - apps/desktop/src/ReaderView.tsx
  key_links:
    - "El gate mide la INVARIANTE (posicion en viewport del ancla), no el mecanismo: sirve tanto si el arreglo es reservar bien la altura como si es dejar que el navegador ancle el scroll."
    - "TOTAL_PAGINAS del harness DEBE superar MAX_LIVE_PAGES (5) o no monta/desmonta NADA y el gate mide un bug que no puede ocurrir."
    - "El harness carga out/renderer/index.html (el bundle CONSTRUIDO): sin `npm run build` previo mide el codigo VIEJO."
---

<objective>
Cerrar los hallazgos #4 (vertical + ajuste ancho: saltos bruscos al scrollear HACIA ARRIBA) y #5
(el contador de pagina desaparece con el chrome) del UAT manual de la Fase 03.

Purpose: RD-02 pide los tres modos de lectura y el UAT encontro el vertical inusable. Es el ultimo
bloque funcional entre la Fase 03 y `/gsd-verify-work 3`.
Output: un gate runnable que falla si vuelve el salto, el arreglo que la medicion senale (y solo ese),
y un contador que sobrevive al toggle de controles.
</objective>

<context>
@.planning/CODEX-RULES.md
@.planning/debug/fit-height-corta-la-pagina.md

@apps/desktop/scripts/reader-fit.mjs
@apps/desktop/src/ReaderView.tsx
@apps/desktop/src/styles.css
@apps/desktop/src/readerWindow.ts
@apps/desktop/src/i18n.tsx
</context>

<quien_ejecuta_este_plan>
**Este plan NO se delega a Codex.** Todas las tareas dependen de LEER una medicion de un Electron real,
y Codex no arranca Electron en su jaula (STATE.md lo deja escrito para `reader-rss.mjs`; `reader-fit.mjs`
tiene exactamente la misma dependencia). El `<done>` de la Tarea 1 es un numero que Codex no puede
producir, y la Tarea 2 ("arregla solo lo medido") no existe sin ese numero.

Precedente: la sesion de debug del #3 la ejecuto el debugger de punta a punta, midiendo. Mismo trato aqui.
</quien_ejecuta_este_plan>

<constraints_verificadas>
Comprobado contra el arbol real durante la planificacion. No son suposiciones:

1. **El harness de hoy NO PUEDE reproducir el #4, y por eso hay que subir `TOTAL_PAGINAS` primero.**
   `reader-fit.mjs:34` fija `TOTAL_PAGINAS = 4`, y `decodeWindow` (`readerWindow.ts:10`) devuelve
   **todas** las paginas cuando `total <= MAX_LIVE_PAGES` (5). Con 4 paginas **no se monta ni se
   desmonta nada NUNCA**: el bug es estructuralmente imposible en el harness actual. Sin subir ese
   numero por encima de 5, cualquier gate del #4 sale verde midiendo nada. Es el falso verde numero
   tres de esta fase esperando a ocurrir.

2. **Extender `reader-fit.mjs` no toca `.gitignore` ni necesita `git add -f`.** Ya esta TRACKEADO
   (`git ls-files apps/desktop/scripts/` lo confirma). La regla `scripts/` (l.11) solo se traga
   ficheros NUEVOS. Este plan **no crea ficheros** en `scripts/` y **no anade script npm**: la
   cobertura del vertical entra en `npm run test:reader-fit`, que ya arranca Electron + sidecar y
   sabe leer rects. Un harness nuevo seria un segundo arranque de 30s y una segunda mina de gitignore.

3. **Subir `TOTAL_PAGINAS` no altera los 9 casos de paginado ya verdes.** Sus aserciones solo miran
   `.reader-page--visible` (el grupo visible: 1 pagina, o 2 con doble), que es identico con 4 o con
   12 paginas. El cache de imagenes (`nyanko-reader-fit-2000x3000-v1`) esta indexado por DIMENSIONES,
   no por cantidad: las paginas extra se generan una vez y se reutilizan.

4. **El arreglo del #4 no puede montar mas paginas.** Vertical es la rama que monta la ventana entera
   y es la que sostiene RD-09 (147.78 MB / pico 236.58 contra el techo de 500). Los dos arreglos
   plausibles (borrar `overflow-anchor:none`, cambiar `min-height:100vh` por `100%`) son **CSS puro y
   RSS-neutros**: no montan un solo elemento mas. Si la medicion concluyera que el unico arreglo real
   exige montar mas paginas o retener bitmaps, **PARA y dilo** — eso ya no es este plan.
</constraints_verificadas>

<los_sospechosos>
El enunciado nombra tres. Leyendo el codigo aparece un **cuarto** con un mecanismo igual de concreto.
Los cuatro son candidatos, ninguno esta medido, y **puede que solo uno cause el salto**:

- **S1 — desajuste de 34px.** `.reader-vertical-slot{min-height:100vh}` (l.433),
  `.reader-page--vertical{min-height:100vh}` (l.434) y la img de fit-height (l.437) miden **720px**;
  el scrollport real `.titlebar + .reader` mide **686px** (medido en el #3). Ojo con el veredicto: un
  desajuste CONSTANTE de 34px no produce saltos por si solo — produce desalineacion. Si el salto medido
  es de ~930px, S1 explica 34 de esos 930: **eso no es la causa**, es un defecto aparte.
- **S2 — el slot crece al montar la img.** `min-height:100vh` reserva 720px, pero a ajuste ANCHO la
  pagina real mide ~1650px (medido en el #3). Cada slot que monta por encima del viewport crece ~930px
  y empuja hacia abajo todo lo que hay debajo.
- **S3 — `overflow-anchor: none`** (l.432) desactiva el anclaje de scroll del navegador, que es el
  mecanismo nativo que existe justo para compensar S2. **Nota:** `git log -S` dice que entro en
  `8ae77c2` (el commit que creo el ReaderView entero), no en un arreglo posterior: es un defensivo que
  vino de serie, no una decision contra un bug concreto. Eso abarata borrarlo.
- **S4 — el IntersectionObserver premia a los slots VACIOS** (`ReaderView.tsx:212`,
  `.sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0]`). `intersectionRatio` es area visible
  / area TOTAL DEL TARGET, asi que un target mas alto que el viewport nunca llega a 1: un slot montado
  de 1650px topa en 686/1650 = **0.42**, mientras que un slot vacio de 720px llega a **0.95**. Ordenar
  por ratio favorece SISTEMATICAMENTE al slot mas pequeno, o sea al que no tiene pagina. Encaja con el
  perfil del sintoma: a ajuste ALTO la img mide 100vh = el `min-height`, los slots miden todos igual y
  la asimetria desaparece — o sea que tambien seria especifico de ANCHO.

S2 y S3 son dos mitades de un mismo numero: S2 es el tamano del cambio de layout, S3 es que nadie lo
compensa. Por eso el gate se pone sobre el RESULTADO (¿se movio lo que miro?) y no sobre el mecanismo.
</los_sospechosos>

<tasks>

<task type="auto">
  <name>Tarea 1: Medir el #4 en Electron real y dejar el gate en ROJO</name>
  <files>apps/desktop/scripts/reader-fit.mjs</files>
  <action>
    Extender `reader-fit.mjs` (NO crear otro harness, NO anadir script npm) con una seccion de vertical.
    No se arregla NADA en esta tarea: solo se mide y se deja el gate rojo.

    Primero, la precondicion que hace posible el bug: subir `TOTAL_PAGINAS` de 4 a 12. Con 4 <=
    `MAX_LIVE_PAGES` (5) la ventana devuelve todas las paginas y no hay montaje ni desmontaje que medir
    (ver constraint 1). Deja el comentario que explica POR QUE el numero tiene que superar la ventana,
    justo encima de la constante: es la clase de dato que alguien "optimiza" a la baja sin saberlo.

    El caso a medir, en modo `vertical` + ajuste `width`:
    1. Llevar el scroll a la pagina 8 con
       `raiz.querySelector('[data-reader-page="8"]').scrollIntoView({block:"start"})`, y esperar a que
       el estado se estabilice: el IO pone `paginaActual=8`, la ventana pasa a 6..10, o sea que
       `[data-reader-page="10"] img` EXISTE y `[data-reader-page="5"] img` NO. Esperar por esas dos
       condiciones (con `esperarCondicion`), no por un sleep.
    2. Anclar: leer `scrollTop_0` y `top_0` = `slot8.getBoundingClientRect().top - raiz.getBoundingClientRect().top`.
    3. Provocar el montaje de arriba: `raiz.scrollTop = scrollTop_0 - DELTA` (DELTA ~400px) y esperar a
       que aparezca `[data-reader-page="5"] img`.
    4. Volver a medir `top_1` y `scrollTop_1`.

    **La invariante del gate (un solo numero):** `top_1` tiene que valer `top_0 + DELTA`. Has scrolleado
    DELTA hacia arriba, asi que el ancla baja DELTA en el viewport: ni un pixel mas. El motivo del fallo
    se imprime como `la pagina ancla se movio N px de mas al montar la pagina de arriba`. Se mide la
    POSICION EN VIEWPORT y no `scrollTop` a secas a proposito: asi el gate es agnostico del arreglo
    (pasa si el slot reserva bien la altura Y pasa si el navegador ancla el scroll compensando
    `scrollTop`), y lo que congela es lo que el usuario ve, no la implementacion. Misma filosofia que
    la asercion de la cadena de alturas del #3. Tolerancia: `TOLERANCIA_PX` (1px) es demasiado fina
    para scroll; usa ~2px y justificalo en un comentario — el fallo que vigila es de ~930px.

    **Mide TAMBIEN hacia ABAJO** (mismo procedimiento, `scrollTop_0 + DELTA`, esperando a que
    `[data-reader-page="11"] img` monte). El parte del usuario dice «hacia arriba», pero bajando tambien
    se DESMONTA una pagina de arriba (la ventana se desplaza) y encogerse tambien mueve el layout. En el
    #3 la medicion ya CORRIGIO el parte del usuario una vez («ancho» tampoco funcionaba). Si abajo
    tambien salta, el arreglo tiene que cubrirlo; si no salta, es un dato que discrimina entre S2 y S4.

    **Diagnosticos que hay que IMPRIMIR** (no son aserciones — son los que reparten culpas entre los
    cuatro sospechosos, y sin ellos la Tarea 2 no puede decidir):
    - Alto del scrollport (`.reader-vertical`) vs alto de un slot VACIO vs alto de un slot MONTADO.
      Separa S1 (delta de 34) de S2 (delta de ~930).
    - `paginaActual` (lee `.reader-counter`) antes y despues de cada scroll: si salta 2+ paginas de
      golpe con un scroll de 400px, es S4.
    - `intersectionRatio` implicito: alto del slot vacio vs alto del slot montado ya lo dice
      (686/720 = 0.95 contra 686/1650 = 0.42).

    Ojo con una trampa de la medicion: asignar `scrollTop` por script podria comportarse distinto que
    una rueda real de cara al anclaje del navegador (S3). Si en la Tarea 2 borras `overflow-anchor:none`
    y el gate NO se pone verde, comprueba con `ventana.webContents.sendInputEvent({type:"mouseWheel", ...})`
    (evento CONFIABLE, provoca scroll nativo de verdad) antes de concluir que S3 no era.

    `npm run build` ANTES de correr el harness: carga `out/renderer/index.html`, el bundle construido.
  </action>
  <verify>
    <automated>cd apps/desktop && npm run build && npm run test:reader-fit; echo "EXIT=$?"</automated>
  </verify>
  <done>
    Los 9 casos de paginado siguen en OK, y el/los caso(s) nuevos de vertical salen en **FALLO con
    EXIT=1**, imprimiendo el desplazamiento de mas en pixeles. Un gate nuevo que naciera verde estaria
    midiendo otra cosa: el bug esta vivo ahora mismo.
    Los diagnosticos impresos permiten decir, con numeros, cual de S1/S2/S3/S4 contribuye y cuanto, y si
    el salto ocurre tambien hacia abajo. Ese veredicto se escribe en el SUMMARY: es la entrada de la
    Tarea 2.
  </done>
</task>

<task type="auto">
  <name>Tarea 2: Arreglar SOLO el mecanismo que la medicion senale</name>
  <files>apps/desktop/src/styles.css, apps/desktop/src/ReaderView.tsx</files>
  <action>
    Entra el veredicto de la Tarea 1. **Arregla lo medido y nada mas.** Un sospechoso que la medicion
    exculpe se documenta en el SUMMARY y se deja EXACTAMENTE como esta: arreglar tres cosas donde el bug
    era una es como se rompen las otras dos.

    Escalera de arreglos, del mas barato al mas caro. Para en el primero que ponga el gate verde:

    1. **Si contribuye S3** — borrar `overflow-anchor: none` de `.reader-vertical` (l.432). Es una
      declaracion MENOS: el anclaje de scroll es la funcion nativa del navegador que existe exactamente
      para compensar cambios de altura por encima del viewport. Entro de serie con el ReaderView
      (`8ae77c2`), no como arreglo de nada, asi que no hay una razon documentada que defender.
    2. **Si contribuye S4** — en el comparador del IO (`ReaderView.tsx:210-213`), dejar de ordenar por
      `intersectionRatio` (que premia al target pequeno, o sea al slot vacio) y elegir por una magnitud
      que no dependa del alto del target: el candidato visible cuyo borde superior este mas cerca del
      borde superior del root (`entrada.boundingClientRect.top` contra `entrada.rootBounds.top`), que
      ademas es la definicion de «la pagina que estoy leyendo» en un scroll continuo. No anadas estado
      ni un modo nuevo.
    3. **Si contribuye S1 y el gate sigue rojo sin el** — `min-height: 100vh` → `min-height: 100%` en
      `.reader-vertical-slot`. El porcentaje resuelve contra `.reader-vertical` (que hereda la altura
      DEFINIDA de `.reader-stage`: 686px), no contra la ventana. Es la misma leccion de cadena definida
      del #3. **No lo toques si el gate ya esta verde**: 34px no explican un salto de ~930.

    **Prohibido**: tocar `MAX_LIVE_PAGES` (5) o `TECHO_RSS_MB` (500) para que salga un numero. Si RD-09
    se pasa del techo, el bug es del arreglo. Y no reserves la altura real de la pagina «adivinandola»:
    el sidecar no sirve dimensiones y sacarlas es otra fase, no un rodeo dentro de este plan.

    Reporta en el SUMMARY: mecanismo, numero antes, numero despues, y que sospechosos quedan vivos y
    documentados como no-contribuyentes.
  </action>
  <verify>
    <automated>cd apps/desktop && npm run build && npm run test:reader-fit && npm run test:reader-rss && npm run test:reader && npm run check</automated>
  </verify>
  <done>
    `test:reader-fit` sale **0**: los 9 casos de paginado del #3 siguen OK y el vertical ya no mueve el
    ancla mas de lo scrolleado (el numero de «px de mas» cae a ~0).
    `test:reader-rss` sale **0** por debajo de 500 MB, con `MAX_LIVE_PAGES` y `TECHO_RSS_MB` intactos
    (compruebalo: `grep -n "MAX_LIVE_PAGES = DECODE_BEHIND" src/readerWindow.ts` y
    `grep -n "TECHO_RSS_MB = 500" scripts/reader-rss.mjs`).
    `test:reader` 4/4 y `check` limpio.
  </done>
</task>

<task type="auto">
  <name>Tarea 3: Desacoplar el contador de pagina del chrome de controles (#5)</name>
  <files>apps/desktop/src/ReaderView.tsx, apps/desktop/src/styles.css, apps/desktop/src/i18n.tsx</files>
  <action>
    El contador es informacion de LECTURA, no un control, y hoy vive dentro del `<header
    className="reader-controls">` que `controlesVisibles` (l.53 / l.329) alterna con un clic. Sacarlo
    del header es todo el arreglo.

    En `ReaderView.tsx`: mover el `<span className="reader-counter">{paginaActual} / {total}</span>`
    (l.441) FUERA del bloque `{controlesVisibles && (<header>…</header>)}`, dejandolo como hermano del
    header dentro del `<section className="reader …">`. No lo condiciones a nada: siempre visible es la
    razon de ser del cambio.

    En `styles.css`: `.reader-counter` (l.404) pasa de item flex del header a indicador flotante
    discreto en una esquina — `position: absolute` con `z-index` por debajo de `.reader-controls` (20) y
    de `.reader-notice` (25), en la esquina inferior IZQUIERDA (la derecha inferior ya es de
    `.reader-notice`, l.407, y solaparse con el aviso de error seria cambiar un bug de visibilidad por
    otro). Dale el mismo lenguaje visual que el chrome que lo rodea, que ya existe: fondo
    `rgba(12,15,23,.9)`, borde `#303647`, radio, `backdrop-filter: blur(12px)`, y mantén el
    `font-variant-numeric: tabular-nums` que ya tenia (evita el baile de anchos al pasar de 9 a 10).
    Quita el `margin-left: auto`, que era su forma de empujarse a la derecha DENTRO del flex del header
    y ya no significa nada. En el `@media (max-width: 900px)` (l.446-450), la regla
    `.reader-counter { margin-left: 0 }` queda huerfana por lo mismo: borrala.

    En `i18n.tsx`: el contador deja de tener el `<header>` alrededor que le daba contexto, asi que
    anade `aria-label={\`${t("reader.page")} ${paginaActual} / ${total}\`}` y con el la clave
    `"reader.page"` en ES ("Página") **y** en EN ("Page"). `t` es `(key: string) => string`, sin
    interpolacion (l.661): la clave es solo la palabra y los numeros se concatenan fuera. Sin esto un
    lector de pantalla anuncia «3 barra 12» flotando sin contexto.

    **No** anadas una preferencia configurable ni un modo nuevo para esto (YAGNI): el usuario pidio VER
    la pagina en la que esta.

    Nota para no romper la Tarea 1: `reader-fit.mjs` usa `.reader-counter` como senal de «el reader esta
    abierto» (`abrirPrimerCapitulo`, l.309/312) y `.reader-controls select` para cambiar ajustes. Sacar
    el contador del header mantiene ambos selectores validos — y de hecho vuelve el primero mas robusto.
  </action>
  <verify>
    <automated>cd apps/desktop && npm run check && npm run build && npm run test:reader-fit</automated>
  </verify>
  <done>
    `check` limpio y `test:reader-fit` sigue saliendo 0 (el harness encuentra `.reader-counter` en su
    sitio nuevo y los 9 + N casos siguen verdes).
    El contador esta fuera de `{controlesVisibles && …}` en el JSX: ocultar el chrome ya no puede
    ocultarlo. Las claves `reader.page` existen en ES y EN.
  </done>
</task>

<task type="checkpoint:human-verify" gate="blocking">
  <what-built>
    Los hallazgos #4 y #5 del UAT, con el mecanismo del #4 medido en Electron real y congelado en
    `npm run test:reader-fit`.
  </what-built>
  <how-to-verify>
    1. `cd apps/desktop && npm run dev`, abre un capitulo real de tu biblioteca (uno LARGO: con 5
       paginas o menos el bug no puede ni ocurrir).
    2. Modo = **Vertical**, Ajuste = **Ancho**. Baja unas cuantas paginas y luego **scrollea HACIA
       ARRIBA despacio**: la pagina no debe pegar tirones ni saltar. Este es el #4.
    3. Scrollea tambien hacia ABAJO: mismo criterio (la medicion dira si ahi tambien saltaba).
    4. Haz clic en el centro de la pagina para ocultar los controles: **el contador `N / M` sigue
       visible** en la esquina inferior izquierda. Este es el #5.
    5. De paso, confirma que no se ha roto lo de ayer: modo Paginado LTR/RTL con Ajuste = «Alto» sigue
       mostrando la pagina ENTERA.
  </how-to-verify>
  <resume-signal>Escribe "aprobado" o describe que sigue saltando</resume-signal>
</task>

</tasks>

<verification>
Gates que corre el orquestador (Codex no puede: ni Electron ni pytest — ver `<quien_ejecuta_este_plan>`):

- `cd apps/desktop && npm run build` — obligatorio ANTES de cualquier harness.
- `npm run test:reader-fit` → **0**. Los 9 casos de paginado del #3 + los casos nuevos de vertical.
- `npm run test:reader-rss` → **0**, por debajo de 500 MB. `MAX_LIVE_PAGES`=5 y `TECHO_RSS_MB`=500 sin tocar.
- `npm run test:reader` → 4/4.
- `npm run check` (tsc --noEmit) → limpio.
- `cd apps/backend && .venv/Scripts/python.exe -m pytest -q` → **461 passed** (baseline exacta; este
  plan no toca backend, asi que cualquier otro numero es una senal de alarma, no un exito).
- Sin dependencias nuevas. Sin tocar `.gitignore`, `conftest.py`, `pyproject.toml` ni `pytest.ini`.

**El gate nuevo se ha visto en ROJO** con el bug vivo (es el `<done>` de la Tarea 1), no reintroducido
a posteriori: el bug esta en produccion ahora mismo, asi que el rojo es gratis y es real. Esta fase ya
se comio DOS falsos verdes (el harness de RD-09 imprimiendo FALLO y saliendo 0; el test de cache de
CR-03 verde con el bug delante); el rojo previo no es opcional.
</verification>

<success_criteria>
- El mecanismo del #4 esta MEDIDO, no razonado: el SUMMARY nombra cual de S1/S2/S3/S4 contribuye, con
  numeros, y cuales quedan exculpados y sin tocar.
- `npm run test:reader-fit` falla si vuelve el salto, y se le ha visto fallar.
- El contador sobrevive al toggle de controles.
- RD-09 sigue cerrado con sus constantes intactas.
- Si la medicion contradice el parte del usuario (como en el #3), gana la medicion y queda escrito.
</success_criteria>

<output>
Crear `.planning/quick/260716-boe-vertical-sin-saltos-de-scroll-y-contador/260716-boe-SUMMARY.md` al terminar.
</output>
