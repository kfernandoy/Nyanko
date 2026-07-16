---
phase: 03-page-pipe-lectura-local-la-piedra-angular
plan: 07
subsystem: desktop
tags: [electron, reader, rss, csp, node-test]

requires:
  - phase: 03-06
    provides: lector local con ventana pura de un máximo de cinco imágenes vivas
provides:
  - gate unitario barato para la ventana de decodificación de RD-09
  - harness Electron de ida y vuelta sobre 200 páginas con RSS real del renderer
  - CSP diferenciada para producción, desarrollo y splash
affects: [phase-03-verification, desktop-security, reader-memory]

tech-stack:
  added: []
  patterns:
    - propiedades puras con node:test para límites estructurales
    - medición de workingSetSize filtrada por el PID del renderer
    - CSP de renderer emitida por transformIndexHtml según el modo

key-files:
  created:
    - apps/desktop/src/readerWindow.test.ts
    - apps/desktop/scripts/reader-rss.mjs
    - apps/desktop/electron/main/csp.test.ts
  modified:
    - apps/desktop/electron/main/splash.ts
    - apps/desktop/index.html
    - apps/desktop/electron.vite.config.ts
    - apps/desktop/package.json

key-decisions:
  - "El gate caro mide exclusivamente app.getAppMetrics().memory.workingSetSize para el PID devuelto por getOSProcessId; no tiene fallback a otro proceso."
  - "El pico observado durante el recorrido decide el resultado, aunque el RSS final después del GC sea menor."
  - "La variante de producción conserva HTTPS para portadas y HTTP/WS de loopback para páginas y playbackSocket; unsafe-inline en script-src queda limitado a desarrollo."
  - "El splash usa default-src 'none' y solo permite estilos y sus tres manejadores inline."
  - "RD-09 NO se marca cumplido: el gate se ejecutó y el número medido (621 MB) supera el techo de 500 MB. El plan prohíbe expresamente relajar la ventana o el criterio para que salga verde."

requirements-completed: []

coverage:
  - id: D1
    description: decodeWindow nunca supera cinco índices y conserva límites, orden y simetría ±2
    requirement: RD-09
    verification:
      - kind: unit
        ref: npm run test:reader --workspace @nyanko/desktop
        status: passing
      - kind: manual_procedural
        ref: "prueba de dientes: DECODE_AHEAD=5 pone rojo el test de la propiedad"
        status: passing
    human_judgment: false
    rationale: "4/4 verdes. Con DECODE_AHEAD=5 caen 3 tests y sale con 1 ('pagina 1: 6 indices vivos'); revertido limpio."
  - id: D2
    description: el reader recorre 200 páginas de ida y vuelta y falla si el pico RSS del renderer supera 500 MB
    requirement: RD-09
    verification:
      - kind: integration
        ref: npm run build --workspace @nyanko/desktop && npm run test:reader-rss --workspace @nyanko/desktop
        status: failing
      - kind: manual_procedural
        ref: "prueba de dientes: la medición responde a la ventana (1 página = 153 MB, 5 páginas = 621 MB)"
        status: passing
    human_judgment: true
    rationale: "El harness mide de verdad y tiene dientes, pero el número REPROBADO: 621 MB (pico 691 MB) contra un techo de 500 MB. RD-09 no se cumple."
  - id: D3
    description: la ventana principal y el splash tienen CSP sin relajar las preferencias seguras de Electron
    requirement: RD-09
    verification:
      - kind: unit
        ref: npm run test:csp --workspace @nyanko/desktop
        status: passing
      - kind: manual_procedural
        ref: comprobar portadas, páginas locales, playbackSocket, HMR y botones del splash
        status: unknown
    human_judgment: true
    rationale: "6/6 verdes y la CSP de producción verificada dentro de out/renderer/index.html. La UAT visual (portadas/HMR/splash) sigue pendiente del orquestador."
  - id: D4
    description: los cambios TypeScript conservan firmas válidas del escritorio
    requirement: RD-09
    verification:
      - kind: other
        ref: npm run check --workspace @nyanko/desktop
        status: passing
    human_judgment: false
    rationale: "tsc --noEmit limpio."

duration: ~50min
completed: 2026-07-16
status: complete
---

# Phase 03 Plan 07: Gates medidos de memoria y CSP Summary

**Los dos gates de RD-09 existen y se ejecutaron: el barato pasa, el caro MIDE 621 MB contra un techo
de 500 MB — RD-09 no se cumple. Seam G aterriza con CSP para app y splash.**

## Performance

- **Duration:** ~50 min
- **Completed:** 2026-07-16
- **Tasks:** 3
- **Files modified:** 8

## El resultado que importa: RD-09 NO se cumple

El plan existía para convertir RD-09 de intención en número. El número está, y es rojo.

| Ventana de decodificación | RSS final | Pico | Gate |
|---|---|---|---|
| 1 página (`0/0`) | **153,36 MB** | 221,76 MB | sale 0 |
| **5 páginas (`±2` de D-07, lo que se envía)** | **621,47 MB** | **690,93 MB** | **sale 1 — FALLO** |

Cinco corridas independientes con la ventana real: 609,42 / 617,35 / 618,42 / 621,47 / 635,62 MB
(picos 679–705 MB). La medición es estable, no es ruido.

**La medición es real y tiene dientes.** Con la ventana en 1 página el mismo harness, sobre la misma
app y el mismo capítulo, mide 153 MB y sale verde. O sea: el número responde a la ventana, luego el
harness está midiendo bitmaps de páginas y no una línea base fija. El presupuesto del plan (~250 MB de
Electron + 5 × 24 MB = ~370 MB) se queda corto contra los 621 MB reales; la diferencia entre 1 y 5
páginas (468 MB) es muy superior a los 4 × 24 MB = 96 MB que predecía el modelo, lo que apunta a que
la caché de imágenes decodificadas de Chromium retiene bitmaps más allá de los `<img>` montados —
`window.gc()` no la vacía porque no es heap de JS.

**No se ha tocado nada para que salga verde.** El plan lo prohíbe explícitamente: «PROHIBIDO relajar
la ventana de decodificación para que el numero salga. Si el RSS se pasa de 500 MB, el bug esta en el
reader, no en el criterio». Ni la ventana ni el techo se han movido. Esto **requiere decisión** y cae
fuera de `files_modified` de este plan (el reader es 03-06; el criterio es del ROADMAP):

1. **El reader retiene de más** → arreglarlo (¿límite de caché de imágenes, `img.decoding`, liberar
   `src` al desmontar?). Es la lectura que asume el plan.
2. **El techo de 500 MB es irreal** para Chromium con bitmaps de 24 MB → recalibrar el criterio con
   datos, no por conveniencia.

## Accomplishments

- `readerWindow.test.ts` afirma el techo literal de cinco índices para las 200 posiciones, sus bordes
  y el agrupamiento de doble página con offset. Verificado que tiene dientes.
- `reader-rss.mjs` construye una biblioteca temporal de 200 JPEG de 2000x3000, arranca el sidecar
  real, conduce el reader con PageDown/PageUp y mide el RSS del renderer por su PID. **Ejecutado.**
- La ventana principal recibe una CSP de producción estricta y otra de desarrollo compatible con
  React Refresh en el puerto 1420; el splash recibe una política independiente con red cerrada.
- `csp.test.ts` protege las fuentes necesarias para portadas, assets locales y playbackSocket, y
  afirma que ambas ventanas mantienen las preferencias seguras de Electron.

## Task Commits

- **Task 1:** `9ea55db` — test(03-07): decode window ceiling as a pure property.
- **Task 2:** `e6bedc1` — test(03-07): measure renderer RSS over a real 200-page chapter.
- **Task 3:** `1561912` — feat(03-07): the app's first CSP, corrected not literal (Seam G).

## Verificación ejecutada (números reales, no `unknown`)

| Gate | Resultado |
|---|---|
| `npm run test:reader` | **4/4 verdes** |
| dientes del gate barato (`DECODE_AHEAD=5`) | **rojo, sale 1** (`pagina 1: 6 indices vivos`); revert limpio |
| `npm run test:csp` | **6/6 verdes** |
| `npm run check` (tsc) | **limpio** |
| `npm run build` → CSP en `out/renderer/index.html` | **aplicada**, sin `%CSP%` residual, `script-src 'self'` |
| `rg "webSecurity: *false\|nodeIntegration: *true\|'unsafe-eval'"` | **vacío** |
| `rg "getProcessMemoryInfo\|privateBytes"` en el harness | **0 coincidencias** (falso verde evitado) |
| `npm run test:reader-rss` | **rojo, sale 1 — 621 MB > 500 MB** |

CSP de producción verificada dentro del build:
`default-src 'self'; img-src 'self' http://127.0.0.1:* https: blob: data:; connect-src 'self' http://127.0.0.1:* ws://127.0.0.1:*; style-src 'self' 'unsafe-inline'; script-src 'self'; object-src 'none'; frame-src 'none'; base-uri 'none'; form-action 'none'`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] El shell ocultaba la vista local sin cuenta ni biblioteca remota**

- **Found during:** Task 2.
- **Issue:** `App.tsx:1247` antepone la pantalla «conecta tu cuenta» a TODAS las vistas cuando no hay
  cuenta autenticada Y `media` está vacío — incluida `local-manga`, que solo lee ficheros locales. Con
  un data dir temporal eso es siempre cierto, así que el reader era inalcanzable por la UI.
- **Fix:** se siembra una entrada mínima en la SQLite temporal tras arrancar el sidecar. No se usa el
  llavero (`PYTHON_KEYRING_BACKEND=null`), no se consulta ningún proveedor, no se toca al usuario.
- **Files modified:** `apps/desktop/scripts/reader-rss.mjs`.
- **Verification:** el harness llega al reader y mide.

**2. [Rule 1 - Bug] El harness imprimía «-> FALLO» y salía con 0 (FALSO VERDE)**

- **Found during:** verificación de Task 2 (ejecutando el gate).
- **Issue:** sin listener de `window-all-closed`, Electron aplica su comportamiento por defecto —
  cerrar la última ventana termina la app **con código 0**. `limpiar()` destruye la ventana y luego
  hace `await`; ese quit(0) gana la carrera y `app.exit(codigoSalida)` nunca se ejecuta. Reproducido
  aislado: `destroy + await + exit(1)` → sale **0**; con un listener vacío → sale **1**.
- **Por qué es grave:** es exactamente el falso verde que este plan existe para impedir. RD-09 se
  habría dado por cumplido con el gate en rojo delante.
- **Fix:** `app.on("window-all-closed", () => {})`.
- **Files modified:** `apps/desktop/scripts/reader-rss.mjs`. **Commit:** `e6bedc1`.

**3. [Rule 1 - Bug] El gate fallaba de forma intermitente con «database is locked»**

- **Found during:** verificación de Task 2.
- **Issue:** la siembra abre con `node:sqlite` la MISMA SQLite que el sidecar ya tiene abierta, sin
  `busy_timeout`: la primera escritura choca con su lock. Un gate que falla al azar acaba
  reintentándose hasta que sale verde.
- **Fix:** `PRAGMA busy_timeout = 10000` + `BEGIN IMMEDIATE`.
- **Files modified:** `apps/desktop/scripts/reader-rss.mjs`. **Commit:** `e6bedc1`.

**4. [Rule 3 - Blocking] `reader-rss.mjs` caía bajo la regla `scripts/` de `.gitignore`**

- **Issue:** un `git add` normal lo habría ignorado en silencio y el harness nunca habría llegado al
  repo. Sus hermanos (`publish-bridge.mjs`) ya están trackeados pese a la regla.
- **Fix:** `git add -f`, sin tocar `.gitignore`.

---

**Total deviations:** 4 auto-fixed (2 de ellas bugs críticos del propio gate).

## Issues Encountered

- **RD-09 no se cumple** (621 MB > 500 MB). Ver arriba: requiere decisión, no se ha maquillado.
- **Colisión de ejecutores:** Codex ejecutó este mismo plan en paralelo sobre el mismo árbol mientras
  el ejecutor GSD trabajaba. El código de las tareas 2 y 3 es de Codex; la verificación, los tres
  arreglos y los commits son del ejecutor. Hubo dos colisiones de escritura (una revirtió
  temporalmente los scripts de `package.json`, restaurados y verificados). Conviene no lanzar los dos
  a la vez sobre el mismo working tree.
- UAT visual de CSP (portadas, HMR, botones del splash) pendiente del orquestador.
- `node:sqlite` verificado disponible en Electron 43.1.0 (Node 24.18.0), incluido `RETURNING`.

## Self-Check: PASSED

- Ficheros creados presentes: `readerWindow.test.ts`, `reader-rss.mjs`, `csp.test.ts` — OK.
- Commits existen: `9ea55db`, `e6bedc1`, `1561912` — OK.
- `requirements-completed` vacío a propósito: RD-09 medido y REPROBADO.

## Next Phase Readiness

**La fase 03 NO puede cerrarse todavía.** Los artefactos del plan 07 están completos y verificados,
pero RD-09 está en rojo con evidencia medida. Antes de cerrar hace falta decidir entre arreglar la
retención del reader o recalibrar el techo con datos — y volver a correr `test:reader-rss`.

---
*Phase: 03-page-pipe-lectura-local-la-piedra-angular*
*Completed: 2026-07-16*
