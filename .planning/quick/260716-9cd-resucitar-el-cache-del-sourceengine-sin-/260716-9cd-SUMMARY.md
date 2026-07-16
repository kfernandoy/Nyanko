---
phase: quick-260716-9cd
plan: 01
subsystem: sources
tags: [cache, rate-limit, fastapi, CR-03, WR-03]
requires:
  - source_error_action() (taxonomia de errores, Fase 02)
  - app.state.source_registry (WR-06, Fase 03)
provides:
  - Cache de capitulos vivo entre peticiones (CR-03)
  - Back-pressure preservada ante 429 con cache caliente (WR-03)
affects:
  - /api/manga/chapters
tech-stack:
  added: []
  patterns:
    - Derivar al leer + memoizar por identidad (mismo patron que progress.effective_chapter, Phase 01)
key-files:
  created: []
  modified:
    - apps/backend/nyanko_api/sources/engine.py
    - apps/backend/nyanko_api/main.py
    - apps/backend/tests/test_source_engine.py
    - apps/backend/tests/test_manga_api.py
decisions:
  - El criterio del fallback es source_error_action(error) == "esperar", no un isinstance nuevo
  - El engine se deriva de la identidad del registry al leer, no se mantiene en los 3 sitios de rebuild
metrics:
  duration: ~15min
  completed: 2026-07-16
  tests: 455 passed (baseline 452 + 3 nuevos)
status: complete
---

# Quick 260716-9cd: Resucitar el cache del SourceEngine sin perder el back-pressure — Summary

Cache de capitulos vivo entre peticiones (engine derivado de la identidad del registry) y un 429 que
sigue saliendo 429 con el cache caliente — CR-03 y WR-03 cerrados en el mismo commit-set, sin ventana
donde la costura exista.

## Que se hizo

### Tarea 1 — WR-03: el fallback no se traga un 429 (`b4d60a8`)

`SourceEngine.chapters()` tenia `except SourceError:` a secas y `SourceRateLimitError` **hereda** de
`SourceError`: el fallback devolvia cache ante un 429. Ahora el `except` filtra por la taxonomia que
ya existia en `errors.py`:

```python
if source_error_action(error) == "esperar":
    raise
```

No se escribio un `isinstance(SourceRateLimitError)` nuevo: eso duplicaria una decision que
`source_error_action()` ya posee, y si mañana otro error mapea a `"esperar"` la version con
`isinstance` no se entera. El criterio **no** es "solo reintentar": `SourceParseError` mapea a
`"actualizar_la_fuente"` y sigue sirviendo cache (`test_chapters_returns_good_cache_after_source_parse_error`
verde sin tocarlo).

### Tarea 2 — CR-03: el engine vive lo que vive el registry (`ab1cb34`)

`_source_engine()` construia un `SourceEngine` nuevo por request: el cache siempre nacia vacio y su
fallback era codigo muerto en produccion. Ahora el engine se **deriva de la identidad del registry al
leer** y se memoiza en `app.state.source_engine`, reconstruyendose solo si no existe o si
`engine.registry is not registro`. Se añadio la property publica `SourceEngine.registry` para no meter
mano en `engine._registry` desde `main.py`.

Los **tres** sitios que llaman a `build_source_registry` (`main.py` lifespan, alta, baja) quedaron
intactos: el rebuild cambia la identidad del registry y eso ya tira el engine y su cache por
construccion. Un helper que pusiera registry+engine en los tres habria dejado un invariante con tres
escritores — el cuarto que llamara a `build_source_registry` a pelo reintroduciria CR-03 en silencio.
Es el patron que el proyecto ya decidio (STATE.md, Phase 01: «un invariante mantenido en cuatro sitios
se rompe, uno derivado al leer no»).

## El RED de cada test — ejecutado, no razonado

| Test | Nivel | RED comprobado | Salida real |
|---|---|---|---|
| `test_un_429_no_se_sirve_de_cache_aunque_este_caliente` | engine | antes de la Tarea 1 | `Failed: DID NOT RAISE <class 'SourceRateLimitError'>` |
| `test_dos_peticiones_sirven_el_cache_cuando_la_fuente_falla` | API | antes de la Tarea 2 | `assert 502 == 200` |
| `test_un_429_por_la_api_no_devuelve_cache` | API | **a mano**, ver abajo | `assert 200 == 429` |

El tercero es el guardian de la costura y estaba **verde hoy pero en vacio**: pasaba por accidente
porque el cache estaba muerto, no porque la guarda funcionara. Con CR-03 y WR-03 ya arreglados pasa de
verdad, asi que su RED se demostro a mano segun manda el plan (Tarea 2, paso 5): revirtiendo
temporalmente la guarda `"esperar"` (`if False and ...`), el test **da 200 en vez de 429** — el cache
resucitado se traga el 429. Guarda restaurada acto seguido. Sin este paso el test no probaria nada.

El **orden importo**: WR-03 primero. El arbol nunca paso por un estado con el cache caliente y el
`except SourceError:` a secas — la costura no llego a existir ni transitoriamente.

## Tests de guardia — verdes sin tocarlos

- `test_alta_y_baja_de_carpeta_refrescan_el_registry_sin_reiniciar` — castiga las dos formas de
  equivocarse (memo naif con `hasattr` → 404 en `visible`; engine persistente sin tirar cache → 200 en
  `invisible`). Verde.
- `test_empty_chapters_are_parse_error_and_do_not_cache_empty_list` — afirma `engine._chapters == {}`.
  Verde: el camino de escritura del cache no se toco.
- `test_lifespan_builds_source_registry_once` — verde: este cambio no añade ni una llamada a
  `build_source_registry`.
- `test_source_engine_cache_stays_in_memory_only` — verde: no se escribieron los literales `set_cache`
  ni `sqlite` (tampoco en comentarios).

## Verificacion

```
cd apps/backend && .venv/Scripts/python.exe -m pytest -q
455 passed in 88.61s
```

Baseline previo: 452 passed. +3 tests nuevos, 0 regresiones. (Nota: la suite solo recolecta con
`apps/backend` como cwd; desde la raiz del repo falla con `ModuleNotFoundError: No module named 'tests'`.)

## Deviations from Plan

Ninguna. El plan se ejecuto tal cual, incluido el orden WR-03 → CR-03 y la demostracion manual del RED
del guardian de la costura.

Nota de ejecucion: las reglas 2 y 4 de CODEX-RULES (no ejecutar tests, no commitear) son restricciones
del sandbox de Codex; este plan lo ejecuto Claude, que si puede correr pytest y commitear. Los numeros
de arriba son ejecutados, no estimados.

## Fuera de alcance — anotado, no tocado

Un `SourceNotFoundError` (404) con cache caliente y mismo registry sirve cache rancio: `"actualizar_la_fuente"`
tiene fallback. Ya pasaba antes de este cambio y esta fuera del alcance de WR-03 (que es rate limit).
El plan lo anota explicitamente como observacion, no como bug a arreglar aqui.

## Self-Check: PASSED

- `apps/backend/nyanko_api/sources/engine.py` — FOUND (modificado)
- `apps/backend/nyanko_api/main.py` — FOUND (modificado)
- `apps/backend/tests/test_source_engine.py` — FOUND (modificado)
- `apps/backend/tests/test_manga_api.py` — FOUND (modificado)
- Commit `b4d60a8` (Tarea 1) — FOUND
- Commit `ab1cb34` (Tarea 2) — FOUND
- Suite: 455 passed — EJECUTADO
