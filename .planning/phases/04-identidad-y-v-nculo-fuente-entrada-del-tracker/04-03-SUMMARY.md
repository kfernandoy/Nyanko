---
phase: 04-identidad-y-v-nculo-fuente-entrada-del-tracker
plan: 03
subsystem: backend
tags: [fastapi, pydantic, manga, matcher, media-mappings, reading-events]

requires:
  - phase: 04-02
    provides: media_mappings.chapter_offset, guarda de namespace y resolve_link
provides:
  - flujo HTTP para proponer, consultar, confirmar y borrar vinculos de manga
  - unico escritor de vinculos de manga con validacion de id canonico
  - eventos de lectura que informan linked y conservan media_id cuando existe vinculo
affects: [04-04-panel-vinculo, phase-05-sync-progreso, manga-reader]

tech-stack:
  added: []
  patterns:
    - el matcher solo propone; unicamente el PUT convierte la decision del usuario en fila
    - todas las lecturas de vinculo de manga pasan por resolve_link

key-files:
  created:
    - apps/backend/tests/test_manga_link.py
  modified:
    - apps/backend/nyanko_api/main.py
    - apps/backend/nyanko_api/models.py

key-decisions:
  - "El POST de propuesta no copia ninguna rama de auto-persistencia por score del flujo de anime."
  - "El media_id del vinculo es siempre canonico; la conversion al id externo queda para la Fase 5."
  - "reading-events usa resolve_link y siempre registra el log local; require_link sigue reservado para el sync de la Fase 5."

patterns-established:
  - "GET y match cortocircuitan por resolve_link; una confirmacion guardada manda sobre el fuzzy."
  - "El source y el series_id del PUT se validan mediante SourceEngine antes de persistir."

requirements-completed: [LNK-01, LNK-02, LNK-04]

coverage:
  - id: D1
    description: El matcher propone sobre la biblioteca de MANGA con score y sugerencias sin escribir media_mappings
    requirement: LNK-02
    verification:
      - kind: integration
        ref: apps/backend/tests/test_manga_link.py#test_match_propone_con_score_sin_persistir_ni_duplicar_sugerencias
        status: passed
    human_judgment: false
    rationale: "Medido por el orquestador fuera del sandbox: suite completa 502 passed, 0 failed (baseline 488 tras 04-02, +14). El gate central es un RECUENTO DE FILAS y no un grep: test_match_propone_con_score_sin_persistir_ni_duplicar_sugerencias afirma match_score >= 0.99 Y media_mappings = 0. Como 0.99 > 0.85, una copia de CUALQUIERA de las dos ramas de auto-persistencia del precedente de anime (main.py:3616-3621 biblioteca, main.py:3688-3691 catalogo) lo pone rojo, incluida una tercera que nadie haya nombrado."
  - id: D2
    description: PUT es el unico escritor, valida serie e id canonico, y GET/DELETE completan el CRUD idempotente
    requirement: LNK-01
    verification:
      - kind: integration
        ref: apps/backend/tests/test_manga_link.py#test_confirmar_guarda_el_id_canonico_revincula_y_desvincula
        status: passed
    human_judgment: false
    rationale: "Medido por el orquestador fuera del sandbox (502 passed). Gate del ESCRITOR UNICO ejecutado con AST y no con grep — deliberado: el gate de grep de este plan ya fallo dos veces porque la llamada real ocupa 121 chars con line-length=100 y el estilo de la casa la parte en 5 lineas, asi que ni el grep de una linea ni el remedio con -A2 la ven. Medido sobre el arbol: de los 5 llamadores de set_media_mapping en main.py, EXACTAMENTE UNO pasa manga_link=True (main.py:1782, el PUT); los cuatro de anime (:3809, :3879, :4137, :4283) no lo pasan. delete_media_mapping: uno (:1806, el DELETE). El gate se puso rojo sobre un fixture con dos escritores partidos al estilo de la casa."
  - id: D3
    description: Los endpoints de manga no leen, pisan ni borran mappings del namespace de anime
    requirement: LNK-01
    verification:
      - kind: integration
        ref: apps/backend/tests/test_manga_link.py#test_una_correccion_de_playback_no_reapunta_un_vinculo_de_manga y tests de lectura/borrado de namespace
        status: passed
    human_judgment: false
    rationale: "Medido por el orquestador fuera del sandbox (502 passed): test_una_correccion_de_playback_no_reapunta_un_vinculo_de_manga (el guarda de 04-02 visto desde HTTP: el POST no responde 204 y el vinculo sigue en media_id 42), test_un_mapping_de_anime_no_se_lee_como_vinculo_de_manga y test_un_delete_de_manga_no_borra_un_mapping_de_anime. Las tres operaciones guardadas, verificadas desde el borde HTTP que hoy las viola."
  - id: D4
    description: reading-events registra siempre el log local, informa linked/reason y no encola sin confirmacion
    requirement: LNK-04
    verification:
      - kind: integration
        ref: apps/backend/tests/test_manga_link.py#test_un_evento_sin_vinculo_se_registra_y_no_encola
        status: passed
    human_judgment: false
    rationale: "Medido por el orquestador fuera del sandbox (502 passed): test_un_evento_sin_vinculo_se_registra_y_no_encola (linked=false, reason en espanol, reading_events.media_id NULL, pending_mutations = 0) y test_una_propuesta_alta_no_encola_nada_sin_confirmacion. Gate de fuente ejecutado en las dos direcciones: 0 LLAMADAS anadidas a enqueue_mutation/edit_entry/update_remote_library_entry en el diff de main.py (excluyendo comentarios — hay una mencion en comentario, que es el tripwire documentado y NO una llamada), y el gate da 1 al inyectarle una llamada real. main.py importa resolve_link y NO require_link: cero llamadores de produccion, como el plan declara."

duration: ~19min (Codex) + gates del orquestador
completed: 2026-07-17
status: complete
---

# Phase 04 Plan 03: Vinculo de manga en HTTP Summary

**Propuesta sin escritura, confirmacion canonica explicita y eventos de lectura conscientes del vinculo.**

## Performance

- **Duration:** unknown
- **Started:** unknown
- **Completed:** 2026-07-17
- **Tasks:** 3
- **Files modified:** 3 del plan, mas este SUMMARY

## Accomplishments

- `POST /api/manga/link/match` propone desde la biblioteca de manga, devuelve score y sugerencias y no contiene ningun camino de persistencia.
- `GET`, `PUT` y `DELETE /api/manga/link` forman el CRUD; el `PUT` valida la serie contra la fuente y el `media_id` contra ids canonicos de la biblioteca.
- `POST /api/manga/reading-events` conserva el log local sin vinculo, devuelve `linked`/`reason` y rellena `media_id` cuando existe una confirmacion.
- El gate HTTP cubre biblioteca plana, ids externos, namespaces cruzados y el tripwire de `pending_mutations`.

## Task Commits

- **Tasks 1-3:** `3fc071d` — `feat(04-03): manga link flow over HTTP — propose, confirm, unlink`

El executor no commiteo (CODEX-RULES regla 4: su sandbox deniega la escritura en `.git/`). Los commits
los hizo el orquestador tras medir los gates. **Un solo commit para las tres tasks**, a diferencia de
04-01 (cuatro) y 04-02 (dos): las tres tocan LOS MISMOS tres ficheros y estan acopladas
(`MangaLinkMatchResponse` lleva un campo `link: MangaLink | None`, y `MangaLink` es de la Task 2), asi
que trocear por task daria commits intermedios que ni siquiera importan. Un commit honesto es mejor
que tres que mienten sobre ser atomicos.

## Files Created/Modified

- `apps/backend/nyanko_api/models.py` - modelos del vinculo, confirmacion, propuesta y respuesta del evento.
- `apps/backend/nyanko_api/main.py` - cuatro endpoints, biblioteca parametrizada, titulo derivado del id y resolucion del vinculo en reading-events.
- `apps/backend/tests/test_manga_link.py` - gates HTTP de LNK-01, LNK-02 y LNK-04.
- `.planning/phases/04-identidad-y-v-nculo-fuente-entrada-del-tracker/04-03-SUMMARY.md` - traspaso pendiente de verificacion externa.

## Decisions Made

- Se siguio el plan: ninguna de las dos auto-persistencias por umbral de anime se traslado al matcher de manga.
- El `PUT` guarda directamente el id canonico validado; no escribe `match_corrections` ni convierte al id externo.
- El evento de lectura usa `resolve_link`, no `require_link`: el primero informa y permite registrar el log; el segundo queda sin llamadores productivos hasta que la Fase 5 anada el sync.

## Deviations from Plan

**Ninguna en el codigo.** Alcance respetado: solo los tres `files_modified`. `database.py` y
`linking.py` (de 04-02, ya cerrados) quedaron intactos.

`test_manga_api.py` no se modifico y no hizo falta: el executor lo dejo anotado como «compatibilidad
APARENTE, pendiente de verificacion externa» porque `ReadingEventResponse` sustituye al
`dict[str, int]` que devolvia `create_reading_event`. Medido por el orquestador: la suite completa da
502 passed, 0 failed — el test vivo solo consume la clave `id`, que la respuesta nueva conserva. La
cautela del executor era correcta y la verificacion la confirma.

Unica desviacion de forma, del orquestador: un commit en vez de tres (ver Task Commits).

## Issues Encountered

- No se ejecuto pytest ni ningun runner por la prohibicion expresa de `CODEX-RULES.md`.
- No se hicieron commits ni se actualizaron `STATE.md`, `ROADMAP.md` o `REQUIREMENTS.md`; corresponden al orquestador.
- La conducta HTTP y la secuencia RED/GREEN quedan pendientes de verificacion fuera del sandbox.

## Self-Check: PASSED

Cerrado por el orquestador con gates ejecutados fuera del sandbox. Los `unknown` del executor eran
correctos: no podia medir nada de esto (CODEX-RULES reglas 2 y 4).

| Gate | Estado |
|------|--------|
| Suite completa (`pytest -q`) | **502 passed, 0 failed** en 89.99s (baseline 488 tras 04-02, +14) |
| Alcance (`git status --porcelain`) | solo los 3 `files_modified` + SUMMARY. `database.py` y `linking.py` intactos |
| `conftest.py` / `pyproject.toml` / `pytest.ini` | intactos (regla 3) |
| `ruff check` sobre los tres ficheros | All checks passed |
| **Escritor unico** (AST, no grep) | 1 de 5 llamadores de `set_media_mapping` pasa `manga_link=True` (`main.py:1782`, el PUT). Anime: `:3809`, `:3879`, `:4137`, `:4283`, ninguno con opt-in. `delete_media_mapping`: 1 (`:1806`, el DELETE) |
| **No auto-persistencia** (recuento de filas) | `match_score >= 0.99` con `media_mappings = 0`. 0.99 > 0.85 pone rojo a cualquiera de las dos ramas |
| **No encola** (llamadas, no menciones) | 0 llamadas anadidas a `enqueue_mutation`/`edit_entry`/`update_remote_library_entry`; el gate da 1 al inyectar una real |
| `require_link` sin llamadores de produccion | `main.py:52` importa `UnlinkedSeriesError` y `resolve_link`, NO `require_link`. Correcto por diseno |
| Tripwire de `pending_mutations` | presente y verde en vacio (`test_manga_link.py:409`), con su comentario de por que hoy pasa gratis |

**Nota sobre los gates de fuente** (anti-patron `blocking` de esta fase). Dos de los tres gates de
este plan dieron **falso positivo** en su primera redaccion y hubo que medirlos:

1. El gate de «no encola» greppeaba el token `enqueue_mutation` y cazaba un **comentario** — justo la
   documentacion del tripwire que el plan PIDE. La prohibicion habla de una *llamada*. Corregido a
   `enqueue_mutation\(` excluyendo lineas de comentario.
2. El gate del **escritor unico** es el que este plan ya tenia documentado como roto dos veces (grep de
   una linea: 0 sobre codigo correcto; remedio con `-A2`: el mismo bug). No se reintento con grep: se
   midio con **AST**, que es inmune al formato. Ese es el remedio estructural, no una ventana mas grande.

Los dos se comprobaron en las dos direcciones: el numero esperado, y rojo al inyectar la regresion.

## User Setup Required

Ninguno.

## Next Phase Readiness

El contrato HTTP queda implementado para el panel 04-04, pendiente de que el orquestador ejecute la suite y cierre los estados `unknown`.

---
*Phase: 04-identidad-y-v-nculo-fuente-entrada-del-tracker*
*Completed: 2026-07-17*
