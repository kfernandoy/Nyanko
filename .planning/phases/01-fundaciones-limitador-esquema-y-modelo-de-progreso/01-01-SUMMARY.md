---
phase: 01-fundaciones-limitador-esquema-y-modelo-de-progreso
plan: 01
subsystem: http
tags: [rate-limiting, asyncio, event-loop, httpx, anilist, kitsu, myanimelist, tdd]

# Dependency graph
requires: []
provides:
  - "RateLimitedClient con presupuesto dirigido por X-RateLimit-Limit (valor del constructor = inicial + techo)"
  - "Reloj de salidas (next_slot) que espacia peticiones FUERA del semáforo"
  - "Estado del limitador por event loop (_LoopState), podado igual que _clients"
  - "Propiedad pública RateLimitedClient.budget (presupuesto efectivo observable)"
  - "Fixture real_rate_limit_sleep: grabador de sleeps que anula el noop autouse"
affects: [motor-de-fuentes, page-pipe, cola-de-descargas, sync-de-progreso]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Estado ligado a asyncio keyed por event loop + poda de loops cerrados"
    - "Ritmo por reloj de salidas (deadline/next_slot), no por sleep post-petición"
    - "Datos del proveedor como parámetro de control: parsear, validar y ACOTAR"

key-files:
  created: []
  modified:
    - apps/backend/nyanko_api/http.py
    - apps/backend/nyanko_api/anilist.py
    - apps/backend/nyanko_api/kitsu.py
    - apps/backend/nyanko_api/myanimelist.py
    - apps/backend/tests/test_http.py
    - apps/backend/tests/conftest.py

key-decisions:
  - "El número del constructor (90/50/60) pasa de ser «el presupuesto» a ser «valor inicial y techo»; el presupuesto real lo anuncia el proveedor."
  - "El semáforo deja de ser el mecanismo de ritmo y pasa a ser solo tope de peticiones en vuelo (max_concurrency=8)."
  - "Se acota el presupuesto anunciado a [1, techo]: una cabecera hostil (999999) no puede desactivar el limitador (T-01-02)."
  - "NO se pone suelo al clamp por encima de 1 (T-01-05 aceptado): ignorar un presupuesto genuinamente bajo cambiaría un parón por un baneo."
  - "El estado del limitador vive por event loop porque MutationWorker hace asyncio.run() en otro hilo (un loop nuevo por mutación)."
  - "Los tests de ritmo se afirman contra los sleeps SOLICITADOS (grabador), no a reloj de pared: deterministas e instantáneos."

patterns-established:
  - "Calendario acumulativo como aserción de ritmo: [i * intervalo for i in range(n)], nunca «cada sleep vale el intervalo» (esa forma es verde para el bug)."
  - "Observar cabeceras de control ANTES de raise_for_status: el 429 es la respuesta que trae el presupuesto degradado."

requirements-completed: [FND-01, FND-02, FND-03]

coverage:
  - id: D1
    description: "FND-01: el ritmo lo fija X-RateLimit-Limit; el número del constructor es valor inicial y techo"
    requirement: "FND-01"
    verification:
      - kind: unit
        ref: "tests/test_http.py#test_pacing_follows_provider_header[120|45|12]"
        status: pass
      - kind: unit
        ref: "tests/test_http.py#test_budget_degrades_and_recovers"
        status: pass
      - kind: unit
        ref: "tests/test_http.py#test_hostile_budget_header_is_clamped"
        status: pass
    human_judgment: false
  - id: D2
    description: "FND-02: el sleep del intervalo ocurre fuera de cualquier semáforo retenido"
    requirement: "FND-02"
    verification:
      - kind: unit
        ref: "tests/test_http.py#test_concurrent_requests_get_distinct_deadlines"
        status: pass
      - kind: unit
        ref: "tests/test_http.py#test_max_concurrency_caps_requests_in_flight"
        status: pass
    human_judgment: false
  - id: D3
    description: "FND-03: el estado del limitador vive por event loop y se poda como _clients"
    requirement: "FND-03"
    verification:
      - kind: unit
        ref: "tests/test_http.py#test_burst_from_two_event_loops"
        status: pass
      - kind: unit
        ref: "tests/test_http.py#test_loop_state_prunes_closed_loops"
        status: pass
    human_judgment: false
  - id: D4
    description: "Los tres proveedores (AniList/Kitsu/MAL) siguen en verde con el limitador arreglado"
    verification:
      - kind: unit
        ref: "cd apps/backend && python -m pytest -q (331 passed)"
        status: pass
    human_judgment: false

metrics:
  duration: ~50 min
  completed: 2026-07-13
  tasks: 3
  commits: 3
status: complete
---

# Phase 01 Plan 01: Fundaciones del limitador Summary

Los tres bugs del limitador cerrados a la vez: el presupuesto lo dicta ahora `X-RateLimit-Limit` del
proveedor (acotado a un techo para que una cabecera hostil no lo desactive), el sleep del intervalo
salió de dentro del semáforo hacia un reloj de salidas, y el estado de asyncio pasó a vivir por event
loop — podado igual que `_clients`.

## Qué se construyó

**`RateLimitedClient` reescrito** (`nyanko_api/http.py`):

| Antes | Ahora |
|-------|-------|
| `requests_per_minute` = el presupuesto, horneado | `_ceiling` (techo) + `_budget` (efectivo, del proveedor) |
| `asyncio.Semaphore(90)` construido en `__init__` | `_LoopState(lock, semaphore, next_slot)` por event loop |
| `await asyncio.sleep(interval)` **dentro** del semáforo | reloj de salidas: reserva hueco bajo `lock`, duerme fuera, luego entra al semáforo |
| Semáforo = mecanismo de ritmo (valor 90) | Semáforo = tope de peticiones **en vuelo** (`max_concurrency=8`) |
| Nadie leía las cabeceras | `_observe_budget()` tras **cada** respuesta, **antes** de `raise_for_status` |

**Por qué los tres juntos y no solo el 90→30:** el limitador sobrevivía porque *nunca contendía*. Un
`Semaphore(90)` no llega a esperar nunca, y un primitivo de asyncio solo se ata a un loop **cuando
tiene que esperar**. Arreglar solo el número habría hecho que empezara a contender — y ahí es donde
el semáforo compartido entre el loop de uvicorn y el `asyncio.run()` del `MutationWorker` habría dado
el `RuntimeError`. Lo comprobé en la práctica (ver «Evidencia»).

## Evidencia de que los tests tienen dientes

Requisito explícito del plan: un test de ritmo que no falle contra el bug de hoy no prueba nada.

1. **`test_concurrent_requests_get_distinct_deadlines` contra el `http.py` roto** (ejecutado antes de
   arreglar, con una copia del test sin el import de `RATE_LIMIT_HEADER` para que el fallo fuera de
   comportamiento y no de colección):

   ```
   assert len(set(real_rate_limit_sleep)) == requests
   E   assert 1 == 10
   E    +  where 1 = len({0.6666666666666666})
   ```

   Diez corrutinas durmiendo **el mismo** intervalo y saliendo en el mismo tick: FND-02 exactamente.

2. **`_observe_budget` neutralizado** (un `return` temprano temporal, ya revertido) →
   `test_pacing_follows_provider_header` **falla en los tres parámetros** (120, 45, 12) y
   `test_budget_degrades_and_recovers` también (`assert [90, 90...`). Ningún presupuesto puede
   colarse horneado en el código.

3. **`test_burst_from_two_event_loops` PASA contra el código roto** — y eso *no* es un fallo del test,
   es la tesis del plan hecha visible: con `Semaphore(90)` y 50 corrutinas por loop el semáforo nunca
   llega a esperar, así que nunca se ata a un loop y la bomba no explota. Los dientes de FND-03 los
   pone `test_loop_state_prunes_closed_loops` (que revienta con `AttributeError` sin `_loop_state`).
   Dejé el fake del burst **cediendo el control** (`await _real_sleep(0)`) para que con
   `max_concurrency=8` el semáforo sí espere de verdad en **ambos** loops: es el camino que habría
   explotado con estado compartido, y ahora es un guardián real de regresión.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `_client_for` podía reventar con `RuntimeError: dictionary changed size during iteration`**
- **Found during:** Task 1
- **Issue:** El plan pedía replicar `_client_for` «exactamente». Pero su poda itera el dict
  (`[known for known in self._clients if known.is_closed()]`) sin lock, y ahora hay dos hilos con dos
  loops tocándolo: el otro hilo puede **insertar** su entrada mientras iteramos. Copiar el patrón tal
  cual habría duplicado el fallo latente en `_loop_state`.
- **Fix:** `list(self._loop_state)` (snapshot atómico a nivel C) antes de iterar, y `pop(stale, None)`
  en vez de `del`. Aplicado **a los dos** — arreglar solo el nuevo dejaba el original roto (root cause,
  no síntoma).
- **Files modified:** `apps/backend/nyanko_api/http.py`
- **Commit:** 8f4efc4

### Orden de los commits (TDD)

El plan lista la implementación (Task 1) antes de los tests (Task 2), pero ambas tareas son
`tdd="true"` y el criterio de aceptación de la Task 2 exige *ver el test fallar contra el `http.py`
actual*. Se ejecutó en orden RED → GREEN: commit de tests primero (`3cfb95a`), implementación después
(`8f4efc4`). Mismo contenido, orden invertido, evidencia real.

## Tests tocados y por qué

| Test | Qué se hizo | Motivo |
|------|-------------|--------|
| `test_rate_limited_client_enforces_concurrency_limit` | **Eliminado**, partido en dos | **Afirmaba el bug**, no una regresión. Pasaba *únicamente* porque con `requests_per_minute=1` el semáforo roto degeneraba en un cerrojo de concurrencia 1. No probaba ritmo ni concurrencia: probaba el accidente. Sustituido por `test_max_concurrency_caps_requests_in_flight` (concurrencia, sin `rpm=1`) y los tests de ritmo. |

**Ningún test de proveedor hubo que tocarlo.** Cero regresiones: 331 passed.

## Kitsu y MAL: sin cambio de comportamiento

Confirmado explícitamente (`test_missing_budget_header_keeps_constructor_budget`): ninguno de los dos
manda `X-RateLimit-Limit`, y sin cabecera `_observe_budget` **no toca nada**. Su ritmo sigue siendo
byte a byte el de antes (50 y 60 req/min). El `getattr(response, "headers", {})` es lo que impide que
los fakes incompletos de la suite (que solo definen `raise_for_status`) revienten con `AttributeError`.

## Verificación

```
cd apps/backend
python -m pytest tests/test_http.py -q --durations=5   # 20 passed in 0.84s (más lento: 0.01s)
python -m pytest -q                                    # 331 passed in 31.7s
python -m ruff check nyanko_api/ tests/                # All checks passed!
```

Ningún test de ritmo duerme de verdad (el más lento es 0,01 s): se afirma contra los sleeps
*solicitados*, no a reloj de pared.

## Anomalía observada (no es una regresión)

La **primera** ejecución de la suite completa dio un `PytestUnraisableExceptionWarning` (OSError en GC)
achacado a `test_anilist.py::test_discover_returns_paginated_results`. No se ha vuelto a reproducir:

- Suite completa con mis cambios: **9 ejecuciones consecutivas limpias** (331 passed).
- `tests/test_http.py` con `-W error::pytest.PytestUnraisableExceptionWarning`: **5/5 limpias**.
- Baseline pre-cambio (`b6a265d`, extraído a un dir temporal): 5/5 limpias.
- **Argumento de orden:** `test_anilist.py` corre *antes* que `test_http.py` alfabéticamente, así que
  los event loops que crean mis tests nuevos no pueden haberse recolectado durante él.

Conclusión: artefacto de finalización de handles de Windows en el arranque en frío, no del limitador.
Queda anotado por honestidad, no como deuda.

## Threat Flags

Ninguna superficie nueva fuera del `<threat_model>` del plan. T-01-02 (valor alto hostil) mitigado y
cubierto por test; T-01-03 (crecimiento del dict) mitigado con la poda; T-01-05 (valor bajo hostil) y
T-01-04 aceptados según el plan, con `budget` expuesto como propiedad pública para que un parón sea
visible y no silencioso.

## Self-Check: PASSED

- `apps/backend/nyanko_api/http.py` — FOUND
- `apps/backend/tests/test_http.py` — FOUND
- `apps/backend/tests/conftest.py` — FOUND
- Commit `3cfb95a` (test, RED) — FOUND
- Commit `8f4efc4` (feat, GREEN) — FOUND
