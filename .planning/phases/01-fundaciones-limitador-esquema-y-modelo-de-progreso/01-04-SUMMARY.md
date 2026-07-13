---
phase: 01-fundaciones-limitador-esquema-y-modelo-de-progreso
plan: 04
subsystem: backend/persisted-url-guard
tags: [guard, sqlite, trust-boundary, gap-closure, tdd, dead-code]
requires:
  - "01-02: schema v8 y scripts/verify_real_db_migration.py"
  - "01-03: la guardia FND-05 (find_persisted_urls, REMOTE_URL_ALLOWLIST)"
provides:
  - "find_loopback_urls(connection) — la detección NO EXENTABLE: (tabla, columna, filas) que apuntan al sidecar"
  - "assert_no_persisted_urls(connection) — ahora falla incluso en una columna de la lista blanca"
  - "next_progress(chapter, tracker_progress) — sin el parámetro que no leía"
affects:
  - "Fase 3 (reader) y Fase 5 (sync): la guardia importable ya cubre el valor, no solo la columna"
tech-stack:
  added: []
  patterns:
    - "Guardia en dos capas: una exentable (prefijo `http`) y una que NINGUNA lista blanca puede silenciar (host loopback)"
    - "El loopback se busca DENTRO del valor (substring), no solo al principio: el veneno llega también embutido en un payload JSON"
key-files:
  created: []
  modified:
    - apps/backend/tests/test_persisted_urls.py
    - apps/backend/scripts/check_persisted_urls.py
    - apps/backend/nyanko_api/progress.py
    - apps/backend/tests/test_progress.py
    - docs/specs/progress-model.md
    - .planning/REQUIREMENTS.md
decisions:
  - "La exención es de la COLUMNA; el veneno es una propiedad del VALOR. La segunda comprobación no tiene lista blanca y no puede tenerla: es precisamente la que un ejecutor con prisa querría silenciar"
  - "Substring, no prefijo: `cache.payload` empieza por `{` y un LIKE 'http%' no la ve, pero la portada envenenada que lleva dentro muere con el puerto igual. Verificado contra la BD real antes de elegir: cero falsos positivos"
  - "Los tres hosts son `//127.0.0.1`, `//localhost`, `//[::1]`, sin esquema delante: cubre http, https y lo que venga; el `//` evita acertar la palabra suelta en una sinopsis"
  - "El script de la BD real corre también la comprobación de loopback: la guardia es un control sobre DATOS, y el fixture no tiene los datos del usuario"
  - "next_progress pierde tracker_status; is_reread se queda intacto: es la señal de relectura para la Fase 5, y ese SÍ lo lee"
metrics:
  duration: ~35 min
  tasks: 2
  commits: 4
  completed: 2026-07-13
status: complete
---

# Phase 01 Plan 04: Cerrar FND-05 y el parámetro muerto de `next_progress` Summary

La guardia FND-05 ya no puede silenciarse metiendo la columna en la lista blanca: una URL que apunte al propio sidecar falla **esté donde esté**, exenta o no, al principio del valor o embutida en un JSON.

## Qué se construyó

### Task 1 — La exención cubre `http`, nunca `loopback:puerto` (RED → GREEN)

`assert_no_persisted_urls` corre ahora **dos** comprobaciones, y solo una es exentable:

1. **NO EXENTABLE** — `find_loopback_urls`: ningún valor, en ninguna columna, puede contener `//127.0.0.1`, `//localhost` ni `//[::1]`. `REMOTE_URL_ALLOWLIST` exime de `LIKE 'http%'`; de esto no exime a nadie, y el mensaje de error lo dice con esas palabras.
2. Exentable — la de 01-03: ninguna columna fuera de la lista blanca empieza por `http`.

Descubrimiento de esquema en runtime igual que antes (`sqlite_master` + `PRAGMA table_info`, factorizado en `_columns()`): cero listas escritas a mano.

**Prueba de dientes, roja antes que verde.** El test parametrizado `test_loopback_url_fails_even_in_an_allowlisted_column` mete `http://127.0.0.1:8765/assets/...` (y las variantes `localhost`, `[::1]`, `https`) en **`wont_watch.cover_image` — la columna EXENTA** y exige que la guardia falle. Contra el código de 01-03:

```
FAILED test_loopback_url_fails_even_in_an_allowlisted_column[http://127.0.0.1:8765/...]
E   AssertionError: la guardia dejó pasar una URL al PROPIO sidecar por estar en una columna exenta
```

4 rojos (uno por variante de host) + 2 rojos más (`cache.payload`, y el negativo del CDN). Commit rojo `7f229e3`, verde `b456463`. El agujero era real y está tapado.

`test_allowlist_never_covers_local_columns` sigue verde e **intacto** (no se ha tocado una línea).

### Task 2 — `next_progress` ya no declara lo que no lee

`tracker_status` fuera de la firma (ruff no lo veía: ARG002 desactivado). La guarda monotónica ya cubre la relectura; `is_reread(chapter, tracker_progress, tracker_status)` —que **sí** lo lee— es la señal para la Fase 5 y queda como estaba. Cero llamadores fuera de los tests (`grep -rn "next_progress" apps/backend/`). Tabla de casos de `test_progress.py` actualizada, cobertura de `is_reread` conservada.

## Decisiones

**Substring, no prefijo, y se comprobó antes de decidir.** Un `LIKE 'http%'` no ve una URL de loopback dentro de un payload JSON (`cache.payload` empieza por `{`), pero esa portada la sirve el backend igual y muere con el puerto igual. El riesgo de la búsqueda por substring son los falsos positivos, así que se midió contra la BD real **antes** de escribir el código: los únicos aciertos de `127.0.0.1` en la BD de producción v7 son `cover_image_local` (2.784 filas) y `banner_image_local` (1.935) — el bug histórico literal, que la migración a v8 ya limpia. Cero falsos positivos en 12.610 filas de URL remota legítima.

**El script de la BD real corre también la comprobación nueva.** La guardia es un control sobre datos; el fixture no tiene los datos del usuario. Un `exit 0` que no mira la biblioteca real no vale nada.

## Verificación

| Criterio | Resultado |
|---|---|
| Loopback en columna EXENTA → guardia falla | ✅ probado ROJO contra el código anterior, verde después |
| `test_allowlist_never_covers_local_columns` verde e intacto | ✅ |
| `next_progress` no declara nada que no lea; `is_reread` intacto | ✅ |
| Suite completa del backend | ✅ 366 passed |
| `ruff check nyanko_api/ tests/ scripts/` | ✅ All checks passed |
| `check_persisted_urls.py` contra la BD real v8 (`mode=ro`) | ✅ exit 0, 12.610 filas inspeccionadas (no pasó en vacío) |
| FND-05 marcado `[x]` (checkbox + tabla) | ✅ |

## Deviations from Plan

**1. [Rule 2 - Missing critical functionality] La comprobación de loopback también en `scripts/check_persisted_urls.py`**
- **Found during:** Task 1
- **Issue:** El plan solo pedía endurecer el helper del test. Pero el script es la única capa que mira los datos REALES del usuario, y el bug de FND-05 vivió siempre en los datos, nunca en el esquema. Un script que siga diciendo `OK` con una URL de loopback en `wont_watch.cover_image` es exactamente el punto ciego que este plan existe para cerrar.
- **Fix:** El script importa `find_loopback_urls` y sale con 1 si acierta, señalando explícitamente cuándo la columna estaba exenta.
- **Files modified:** `apps/backend/scripts/check_persisted_urls.py`
- **Commit:** b456463

**2. [Rule 1 - Bug] `docs/specs/progress-model.md:68` atribuía `tracker_status` a `next_progress`**
- **Found during:** Task 2
- **Issue:** El spec decía «el `tracker_status` que consume `next_progress`» — falso ya antes de este plan (el cuerpo nunca lo leyó), y falso de forma más visible después.
- **Fix:** La línea apunta ahora a `is_reread` y dice por qué `next_progress` no lo recibe.
- **Files modified:** `docs/specs/progress-model.md`
- **Commit:** dbc194e

## Known Stubs

Ninguno.

## Threat Flags

Ninguno nuevo. Este plan **cierra** una superficie: el reenvío cliente→backend de una URL normalizada por el renderer (`api.ts:204` → `addWontWatch` → `add_wont_watch`, `main.py:3992`) ya no puede persistirse en silencio.

## Commits

| Commit | Tipo | Qué |
|---|---|---|
| `7f229e3` | test | RED: el test de dientes falla contra la guardia de 01-03 |
| `b456463` | feat | GREEN: comprobación de loopback no exentable + script real |
| `dbc194e` | refactor | `next_progress` sin `tracker_status` |

## Self-Check: PASSED

Ficheros y commits verificados en disco/git. `tracker_status` solo sobrevive en `is_reread` (`progress.py:49,57`), que es donde debe estar.
