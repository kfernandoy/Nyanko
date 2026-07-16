---
phase: 03-page-pipe-lectura-local-la-piedra-angular
plan: 06
subsystem: desktop
tags: [react, typescript, manga, reader, memory-window]

requires:
  - phase: 03-05
    provides: cliente del reader, navegación de capítulos y hueco de pantalla completa
provides:
  - lector local con modos paginados RTL/LTR y continuo vertical
  - persistencia por serie de preferencias y por capítulo de progreso
  - ventana demostrable de un máximo de cinco imágenes vivas
  - transición entre capítulos que origina el evento pendiente de lectura
affects: [03-07-reader-verification, phase-05-sync]

tech-stack:
  added: []
  patterns:
    - cálculo puro de ventana de decodificación separado del DOM
    - imágenes vecinas precargadas mediante montaje acotado y desmontaje fuera de ventana
    - preferencias persistentes en SQLite y zoom/paneo transitorios en estado React

key-files:
  created:
    - apps/desktop/src/readerWindow.ts
    - apps/desktop/src/ReaderView.tsx
  modified:
    - apps/desktop/src/App.tsx
    - apps/desktop/src/i18n.tsx
    - apps/desktop/src/styles.css

key-decisions:
  - "La ausencia de preferencias se materializa con un PUT vacío para que el RTL predeterminado siga teniendo una sola autoridad: el esquema SQLite."
  - "El modo vertical conserva espaciadores para todo el capítulo, pero solo monta imágenes dentro de decodeWindow."
  - "El evento se emite al entrar en la transición hacia delante y un Set por sesión impide duplicarlo para el mismo capítulo."

patterns-established:
  - "ReaderView consume directamente las URLs normalizadas por api.ts y nunca construye ni persiste URLs."
  - "La navegación por teclado registra un único listener global y lo elimina en el cleanup."
  - "La doble página agrupa índices con offset manual sin ampliar el techo de cinco imágenes."

requirements-completed: [RD-02, RD-03, RD-04, RD-05, RD-06, RD-07, RD-09]

coverage:
  - id: D1
    description: decodeWindow implementa la ventana literal ±2 y pagePairs el offset manual
    requirement: RD-07, RD-09
    verification:
      - kind: unit
        ref: npm run test:reader --workspace @nyanko/desktop (lo aporto el plan 03-07)
        status: pass
    human_judgment: false
    rationale: "El plan 03-07 entregó el test que este difería. Corrido por el orquestador: 4/4. Con DECODE_AHEAD=5 se pone rojo, así que muerde."
  - id: D2
    description: ReaderView ofrece RTL, LTR y vertical con navegación, ajustes, zoom, paneo y progreso
    requirement: RD-02, RD-03, RD-04, RD-05, RD-07
    verification:
      - kind: manual_procedural
        ref: UAT del reader en la aplicación Electron
        status: pass
      - kind: other
        ref: npm run check --workspace @nyanko/desktop
        status: pass
    human_judgment: false
    rationale: "UAT manual PASADO por el usuario (2026-07-16): los tres modos, los tres ajustes, doble página y zoom. Destapó 3 defectos de UX, todos cerrados: «alto» no ajustaba (grid rompía la cadena de alturas), saltos de scroll en vertical (915px, `overflow-anchor:none`) y ~92px de hueco en el lomo. Vigilado ahora por `npm run test:reader-fit` (11 casos). NOTA: el paneo y el progreso/reanudar de esta descripción NO se confirmaron uno a uno en la UAT; el progreso lo cubre 03-04 D3 con test de backend."
  - id: D3
    description: El DOM mantiene como máximo cinco imágenes de página y desmonta las restantes
    requirement: RD-09
    verification:
      - kind: manual_procedural
        ref: scripts/reader-fit.mjs y scripts/reader-rss.mjs (Electron real, medido por el orquestador)
        status: pass
    human_judgment: false
    rationale: "MEDIDO, no razonado. `test:reader-fit` imprime las páginas montadas en un capítulo de 12: `montadas 6,7,8,9,10` — exactamente 5, y se desplazan al scrollear. `test:reader-rss` recorre 200 páginas reales: 136-166 MB contra el techo de 500, exit 0."
  - id: D4
    description: La transición encadena capítulos y emite una sola fila pendiente al terminar
    requirement: RD-06
    verification:
      - kind: manual_procedural
        ref: terminar un capítulo y consultar reading_events en la SQLite de la aplicación
        status: unknown
    human_judgment: true
    rationale: "SIGUE SIN VERIFICAR. La UAT del 2026-07-16 cubrió modos, ajustes, zoom y navegación, pero NO llegó al final de un capítulo, así que ni la pantalla de transición ni la fila de reading_events se han visto nunca. Es el único hueco real de la fase: D-15 dice que el evento nace antes que su consumidor para que la Fase 5 encuentre el trigger ya persistido — si no emite, la Fase 5 arranca sobre una tabla vacía y el fallo aparece allí, lejos de su causa."

duration: unknown
completed: 2026-07-16
status: complete
---

# Phase 03 Plan 06: Reader local con memoria acotada Summary

**Lector de manga local completo, con tres modos, progreso persistente, encadenado de capítulos y un techo estructural de cinco imágenes vivas.**

## Performance

- **Duration:** unknown
- **Started:** unknown
- **Completed:** 2026-07-16
- **Tasks:** 3
- **Files modified:** 5

## Accomplishments

- `readerWindow.ts` concentra la aritmética pura de la ventana ±2 y el emparejamiento doble con
  offset manual.
- `ReaderView` implementa los modos RTL, LTR y vertical, junto con teclado, rueda, zonas de clic,
  pantalla completa, ajuste, zoom y paneo.
- Las preferencias se guardan por serie y el progreso por capítulo; zoom y paneo solo viven durante
  la sesión actual del componente.
- La transición permite avanzar o retroceder entre capítulos y origina una única fila de evento al
  terminar, aunque todavía no exista su consumidor de sincronización.
- `ReaderView` sustituye el `app-shell` durante la lectura, con textos en español/inglés y estilos
  propios `.reader*`.

## Task Commits

- `8ae77c2` feat(03-06): ReaderView with three modes, navigation and decode window (Tareas 1-3; sin test file autorizado por `files_modified`)
- `docs(03-06)`: este SUMMARY (commit de cierre)

## Files Created/Modified

- `apps/desktop/src/readerWindow.ts` - ventana pura de decodificación y grupos de doble página.
- `apps/desktop/src/ReaderView.tsx` - lector, persistencia, navegación y transición de capítulos.
- `apps/desktop/src/App.tsx` - montaje real del reader fuera de `app-shell`.
- `apps/desktop/src/i18n.tsx` - textos `reader.*` en español e inglés.
- `apps/desktop/src/styles.css` - estilos prefijados del reader y precarga fuera del lienzo.

## Decisions Made

- Se usa un `PUT` vacío cuando no existe la fila de preferencias, de modo que SQLite aplique RTL y
  el cliente no duplique el valor predeterminado del esquema.
- En vertical se conservan contenedores de altura estimada para estabilizar el scroll; su `<img>` se
  crea exclusivamente cuando el índice pertenece a `decodeWindow`.
- El conjunto de capítulos ya emitidos vive en un `useRef`: evita duplicados dentro de la sesión sin
  convertir ese estado transitorio en otra persistencia.

## Deviations from Plan

Ninguna.

## Issues Encountered

- La comprobación directa del módulo TypeScript con `node --import tsx` no pudo iniciarse porque el
  sandbox denegó el proceso auxiliar de `esbuild` con `EPERM`; no se alteró la infraestructura para
  eludir la restricción.
- No se ejecutó ningún test runner por la prohibición expresa de `.planning/CODEX-RULES.md`.
- No se hicieron commits ni se actualizaron `STATE.md`, `ROADMAP.md` o `REQUIREMENTS.md`; esas tareas
  corresponden al orquestador.

## Self-Check: pass (tsc) / medición y UAT pendientes

`npm run check --workspace @nyanko/desktop` (tsc --noEmit) ejecutado por el orquestador: **sin
errores**. Backend intacto → suite pytest inalterada (447 passed). Quedan pendientes por diseño:
el test unitario de `readerWindow.ts` y la **medición RSS de RD-09**, que entrega el plan 03-07;
y la UAT del reader en Electron, al cerrar la fase.

## User Setup Required

Ninguno.

## Next Phase Readiness

El plan 03-07 puede probar la función pura, verificar el máximo de cinco imágenes en el DOM y medir
el RSS real. La fila de `reading_events` queda disponible para el consumidor de la Fase 5.

---
*Phase: 03-page-pipe-lectura-local-la-piedra-angular*
*Completed: 2026-07-16*
