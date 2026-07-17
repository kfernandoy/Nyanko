---
phase: 04-identidad-y-v-nculo-fuente-entrada-del-tracker
plan: 04
subsystem: desktop-ui
tags: [react, typescript, manga, media-mappings, reading-events, i18n]

requires:
  - phase: 04-03
    provides: endpoints de propuesta, consulta, confirmacion y borrado del vinculo; ReadingEventResponse
provides:
  - cliente TypeScript para el contrato HTTP de vinculos de manga
  - panel de propuesta y confirmacion explicita por serie local
  - aviso visible cuando un evento de lectura no tiene vinculo confirmado
affects: [phase-05-sync-progreso, manga-reader, desktop-ui]

tech-stack:
  added: []
  patterns:
    - la fila de biblioteca separa navegacion y vinculo en botones hermanos
    - toda clave de vinculo de un nodo de serie usa source_id
    - el reason de reading-events se presenta sin duplicarlo en i18n

key-files:
  created: []
  modified:
    - apps/desktop/src/types.ts
    - apps/desktop/src/api.ts
    - apps/desktop/src/MangaLibraryView.tsx
    - apps/desktop/src/ReaderView.tsx
    - apps/desktop/src/i18n.tsx
    - apps/desktop/src/styles.css

key-decisions:
  - "El matcher solo prepara la propuesta; setMangaLink aparece una vez y se alcanza desde el boton de confirmar."
  - "En MangaLibraryView la clave es siempre el source_id del nodo de serie; ReaderView conserva chapter.series_id porque alli el nodo es un capitulo."
  - "Cambiar un vinculo vigente pide confirmacion antes de desvincular, ya que el backend cortocircuita el matcher mientras la fila existe."

patterns-established:
  - "Promise.allSettled aisla fallos por raiz y por lectura de vinculo para conservar el resto de la biblioteca."
  - "Las propuestas y sugerencias comparten el mismo grupo de opciones; el score se muestra como porcentaje."

requirements-completed: [LNK-01, LNK-02, LNK-04]

coverage:
  - id: D1
    description: El cliente refleja los modelos del backend y expone las cuatro operaciones de vinculo por request()
    requirement: LNK-01
    verification:
      - kind: other
        ref: npm run check --workspace @nyanko/desktop
        status: pass
    human_judgment: false
  - id: D2
    description: La biblioteca muestra estado, propuesta, score, alternativas, offset y confirmacion o desvinculado explicitos
    requirement: LNK-02
    verification:
      - kind: manual_procedural
        ref: 04-04-PLAN.md#human-check pasos 2-8 y 10
        status: unknown
    human_judgment: true
    rationale: "El comportamiento de foco, navegacion, persistencia y aislamiento entre dos series necesita la verificacion humana prevista por el plan."
  - id: D3
    description: ReaderView muestra el reason del backend cuando reading-events responde linked false
    requirement: LNK-04
    verification:
      - kind: manual_procedural
        ref: 04-04-PLAN.md#human-check paso 9
        status: unknown
    human_judgment: true
    rationale: "Hay que completar un capitulo sin vinculo en la aplicacion para comprobar el aviso en su instante real."

duration: unknown
completed: 2026-07-17
status: complete
---

# Phase 04 Plan 04: Panel de vinculo de manga Summary

**Panel de propuesta y confirmacion explicita con score, alternativas y aviso de lectura sin vinculo.**

## Performance

- **Duration:** unknown
- **Started:** unknown
- **Completed:** 2026-07-17
- **Tasks:** 2
- **Files modified:** 6 del plan, mas este SUMMARY

## Accomplishments

- `types.ts` y `api.ts` reflejan el contrato real de 04-03, incluidas las respuestas `linked` y `reason` de los eventos de lectura.
- `MangaLibraryView` separa navegacion y vinculo en controles hermanos y ofrece propuesta, porcentaje, alternativas, offset, confirmacion y desvinculado.
- Cada operacion de vinculo en la biblioteca recibe el `source_id` del nodo de serie; las cargas independientes usan `Promise.allSettled`.
- `ReaderView` presenta el `reason` del backend mediante el canal `setAviso` ya existente.

## Task Commits

- **Task 1:** `3bcddca` — `feat(04-04): manga link client through the existing request() helper`
  (`types.ts`, `api.ts`)
- **Task 2:** `fbc8aee` — `feat(04-04): link panel — score visible, row stops nesting a button`
  (`MangaLibraryView.tsx`, `ReaderView.tsx`, `i18n.tsx`, `styles.css`)

El executor no ejecutó `git add` ni `git commit`, conforme a `.planning/CODEX-RULES.md` (regla 4: su
sandbox deniega la escritura en `.git/`). Los commits los hizo el orquestador tras medir los gates.

## Files Created/Modified

### Task 1: El cliente

- `apps/desktop/src/types.ts` - tipos `MangaLink`, `MangaLinkMatch` y `ReadingEventResponse`.
- `apps/desktop/src/api.ts` - cuatro operaciones de vinculo y firma completa de `createReadingEvent`.

### Task 2: El panel y el aviso

- `apps/desktop/src/MangaLibraryView.tsx` - estado por serie, fila accesible, panel y gestos explicitos de escritura.
- `apps/desktop/src/ReaderView.tsx` - consumo directo de `linked` y `reason`.
- `apps/desktop/src/i18n.tsx` - claves del panel en espanol e ingles.
- `apps/desktop/src/styles.css` - grid de botones hermanos y estilos minimos del panel.

### Artefacto de cierre

- `.planning/phases/04-identidad-y-v-nculo-fuente-entrada-del-tracker/04-04-SUMMARY.md` - cerrado con gates medidos; verificacion humana diferida al UAT de fin de fase.

## Decisions Made

- Se siguio la diferencia de identidad del plan: `source_id` en nodos de serie de la biblioteca y `series_id` en el capitulo que emite el evento.
- La propuesta queda preseleccionada por comodidad, pero no se persiste hasta que el usuario pulsa confirmar.
- El cambio de un vinculo existente avisa que debe desvincular primero: el endpoint de match no devuelve alternativas mientras el vinculo actual exista.

## Deviations from Plan

Ninguna de alcance del executor. No se tocaron dependencias, backend, tests ni ficheros de seguimiento
por parte del trabajo de 04-04 en sí.

La confirmacion nativa antes de cambiar un vinculo hace explicita una consecuencia del contrato de 04-03: el matcher cortocircuita por el vinculo vigente, por lo que hay que borrarlo antes de obtener una propuesta nueva.

**Una, del orquestador: dos ficheros fuera de `files_modified` llegaron con contenido revertido.**

Al retomar la ejecución, `apps/backend/tests/test_reader_persistence.py` y
`04-02-SUMMARY.md` aparecían modificados en el árbol de trabajo — ninguno de los dos está en el
`files_modified` de este plan. El diff revertía exactamente el arreglo `v10 → v11` que el orquestador
ya había medido y commiteado en `9893989` (confirmado por `git reflog`, no solo por el texto), y
`04-02-SUMMARY.md` volvía a un borrador `Self-Check: UNKNOWN` que citaba esos mismos commits como
"pendiente" pese a existir. Diagnóstico: Codex corre en modo *shared session* (un runtime único
reutilizado a lo largo de la fase, ya anotado en `.continue-here.md`), y todo indica que conservó una
lectura de esos dos ficheros de antes de que el orquestador los corrigiera tras 04-02, escribiéndola de
vuelta al cerrar 04-04 pese a la regla 6 de `CODEX-RULES.md` ("toca solo los ficheros de `files_modified`").
Corregido restaurando ambos a `HEAD` (`git checkout HEAD --`) antes de medir ningún gate de este plan;
la suite completa confirma 502 passed tras la restauración, igual que el baseline de 04-03. Ningún
fichero del `files_modified` real de 04-04 se vio afectado.

## Issues Encountered

- Ver "Deviations from Plan" — reversión fuera de alcance en 2 ficheros ajenos a este plan, detectada y
  corregida antes de commitear.
- La verificacion humana de foco, persistencia, dos series bajo una raiz y aviso al terminar un capitulo
  (pasos 2-10 del `<human-check>` de la Task 2) queda pendiente del UAT de fin de fase, tal como el plan
  declara (`human_verify_mode: end-of-phase`).

## Self-Check: PASSED (automatizado)

Medido por el orquestador fuera de cualquier sandbox:

| Gate | Estado |
|------|--------|
| `npm run check --workspace @nyanko/desktop` (tsc --noEmit) | 0 errores |
| Suite completa (`pytest -q`, backend) | **502 passed, 0 failed** (baseline 04-03: 502 — este plan no toca backend) |
| Alcance (`git status --porcelain`) | solo los 6 `files_modified` + este SUMMARY, tras restaurar los 2 ficheros ajenos (ver Deviations) |
| Fila sin botones anidados | `manga-library-item` es `<div>`; `manga-library-open` y `manga-library-link` son hermanos, cero `<button>` dentro de `<button>` |
| Manejador de vincular sin `stopPropagation()` | confirmado a fuente |
| Las cuatro llamadas de vinculo usan `.source_id`, nunca `.series_id` | confirmado a fuente en `mangaLinkMatch`, `mangaLink` (carga de lista + panel), `setMangaLink`, `deleteMangaLink` (× 2 sitios) |
| `setMangaLink` solo desde `onClick` (`confirmarVinculo`), cero `useEffect` que escriba | confirmado a fuente |
| `Promise.allSettled` en carga de vinculos por serie y en carga de raices | confirmado a fuente (UAT #6 de la Fase 3 no se repite) |
| `match_score` como porcentaje en el DOM | confirmado a fuente (`Intl.NumberFormat(..., { style: "percent" })`) |
| Con `link` presente, panel no muestra propuesta/score | confirmado a fuente (bloques mutuamente excluyentes por `propuesta.link`) |
| Offset acotado `min={-9999} max={9999}` | confirmado a fuente |
| `reason` pintado tal cual, sin clave `manga.link.*` duplicándolo | confirmado a fuente en `ReaderView.tsx` |
| Claves `manga.link.*` presentes en `es` y `en` | confirmado a fuente, mismo conjunto en los dos diccionarios |
| `git diff package.json` | vacío |

Lo que sigue **sin medir por automático** son las aserciones de comportamiento que necesitan la app
corriendo (pasos 2-10 del human-check de la Task 2): que pulsar vincular abre el panel sin navegar,
que Tab da dos paradas de foco, que cerrar sin confirmar no crea vinculo, que elegir una sugerencia
vincula a la sugerencia y no al match, que el vinculo sobrevive un reinicio, que dos series de la misma
raiz no comparten vinculo, y que el aviso de "sin vincular" se ve al terminar un capitulo. El plan ya
declara esto `human_verify_mode: end-of-phase`; se ejecuta junto con el resto del UAT de la Fase 4.

## User Setup Required

Ninguno.

## Next Phase Readiness

El panel consume el backend de 04-03 y deja visible el estado sin vinculo que la Fase 5 necesita
respetar. Con este plan cierran los 4/4 planes de la Fase 4; los gates automaticos de los cuatro estan
medidos y en verde. Sigue la verificacion de fase (`gsd-verifier`) y, si hay items de juicio humano, el
UAT correspondiente antes de cerrar la fase.

---
*Phase: 04-identidad-y-v-nculo-fuente-entrada-del-tracker*
*Completed: 2026-07-17*
