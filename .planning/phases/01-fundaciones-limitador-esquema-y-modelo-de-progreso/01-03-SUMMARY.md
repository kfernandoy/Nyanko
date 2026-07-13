---
phase: 01-fundaciones-limitador-esquema-y-modelo-de-progreso
plan: 03
subsystem: backend/persisted-url-guard
tags: [guard, sqlite, schema-introspection, regression-prevention, tdd]
requires:
  - "01-02: schema v8 (library_entries.chapter_progress) y scripts/verify_real_db_migration.py"
provides:
  - "tests/test_persisted_urls.py — la guardia FND-05, que descubre el esquema en runtime"
  - "assert_no_persisted_urls(connection) — helper IMPORTABLE para las Fases 3/7/8"
  - "find_persisted_urls(connection) — la detección: (tabla, columna, filas)"
  - "REMOTE_URL_ALLOWLIST — 6 exenciones, cada una con su justificación escrita"
  - "scripts/check_persisted_urls.py — la misma guardia contra la BD real, mode=ro"
affects: []
tech-stack:
  added: []
  patterns:
    - "Introspección del esquema en runtime (sqlite_master + PRAGMA table_info) en vez de listas de columnas escritas a mano"
    - "Detección compartida entre el test y el script: el script importa del test, no reimplementa"
    - "La lista blanca es de EXENCIONES, no de cobertura: se deriva corriendo la guardia contra datos reales"
key-files:
  created:
    - apps/backend/tests/test_persisted_urls.py
    - apps/backend/scripts/check_persisted_urls.py
  modified: []
decisions:
  - "La guardia enumera tablas y columnas en runtime: una lista escrita a mano es una lista que un día no se actualiza (es justo el fallo de check_stale_asset_ports.py)"
  - "La detección vive en dos funciones importables, no dentro de un test: sobre tablas vacías la guardia pasa en vacío, así que las Fases 3/7/8 tienen que poder invocarla tras SUS escrituras"
  - "La regla dura comprueba el sufijo `path` a secas, no `_path`: las dos columnas de rutas locales reales (local_files.path, library_folders.path) no acaban en `_path`"
  - "wont_watch.cover_image entra en la lista blanca por lo que su ESCRITOR guarda (main.py:3992), no por un acierto: la tabla está vacía en la BD real"
  - "check_stale_asset_ports.py se queda: compara contra el puerto vivo, que es otra comprobación"
metrics:
  duration: ~25 min
  tasks_completed: 2
  commits: 3
  tests: 360 passed (6 nuevos en test_persisted_urls.py)
  completed: 2026-07-13
status: complete
---

# Phase 1 Plan 03: La guardia de URLs persistidas (FND-05) — Summary

Ninguna columna persistida puede empezar por `http` sin una justificación escrita, y la guardia
que lo comprueba **no tiene ninguna lista de columnas que mantener**: enumera las tablas desde
`sqlite_master` y sus columnas desde `PRAGMA table_info`, en runtime. Cubre el esquema v8 y todo
lo que traiga la Fase 3 sin que nadie tenga que acordarse de actualizarla. Ejercitada contra la
BD real de 31,9 MB migrada a v8: 12.610 filas de URL remota legítima inspeccionadas, cero
violaciones.

## Qué se construyó

### Task 1 — La guardia genérica (`a8f8dc4` RED, `4bf4928` GREEN)

`tests/test_persisted_urls.py`. La forma la marcó lo que **no** hay que copiar de
`check_stale_asset_ports.py`: su `COLS = ("cover_image_local", "banner_image_local")` es una lista
escrita a mano, y el esquema v8 acaba de añadir una columna que esa lista no conoce. La guardia
que hay que actualizar a mano es la guardia que un día no se actualiza.

- **`find_persisted_urls(connection)`** → `list[(tabla, columna, filas)]`. Enumera todo en
  runtime. Devuelve **todos** los aciertos, incluidos los exentos: el script los imprime con sus
  recuentos, que es como un humano ve que la guardia no está pasando en vacío.
- **`assert_no_persisted_urls(connection)`** → falla con un mensaje que nombra tabla, columna y
  número de filas. **Importable**, y ese es el punto (ver abajo).
- **`REMOTE_URL_ALLOWLIST`** → `frozenset[tuple[str, str]]`, 6 entradas, cada una justificada.

**El RED fue real:** el commit `a8f8dc4` deja las dos funciones como `raise NotImplementedError`
y los 5 tests de datos fallan por eso (el sexto, la regla dura, es una aserción sobre la lista
blanca y ya pasaba en RED — no necesita implementación). `4bf4928` los pone en verde.

### La lista blanca, derivada de la BD real (no inventada)

Corrida la detección contra la copia v8 de la BD de producción, salieron **5 aciertos**. Los 5
son URLs **del proveedor**, no del sidecar — no caducan con el puerto:

| Tabla.columna | Filas | Por qué está exenta |
|---|---|---|
| `external_identities.url` | 5.099 | La URL pública del media: `https://anilist.co/manga/30002` |
| `media_details_cache.site_url` | 2.786 | El `siteUrl` que devuelve AniList |
| `media_details_cache.banner_image` | 1.938 | El banner **en el CDN del proveedor**. Su copia local es `banner_image_local`, que NO está exenta |
| `media_details_cache.cover_image` | 2.786 | La portada en el CDN. Su copia local es `cover_image_local` — la que se llevó por delante la biblioteca. No está exenta y no puede estarlo |
| `torrent_sources.url` | 1 | El feed RSS de nyaa.si |

La sexta entrada, **`wont_watch.cover_image`**, no salió de un acierto: la tabla está **vacía** en
la BD real. Está exenta por lo que su **escritor** guarda — `add_wont_watch` (`main.py:3992`)
persiste lo que el cliente le manda, que es la portada del CDN del proveedor cuando no hay asset
local cacheado. Se documenta aquí porque es la única entrada que no viene de mirar datos, y una
lista blanca sin trazabilidad es una lista blanca que crece sola.

Nada entró «para que pase». Las columnas `*_json` y `cache.payload` **no** están en la lista
blanca y no hacen falta: llevan URLs remotas *dentro*, pero el valor empieza por `{` o `[`, no por
`http`. Si algún día una de ellas empezara por `http`, querríamos enterarnos — y saltaría.

### La regla dura, y un agujero que el plan no vio

`test_allowlist_never_covers_local_columns` afirma que ninguna entrada de la lista blanca es una
columna de ruta local. El plan pedía comprobar los sufijos `_local` y `_path`. **`_path` no cubre
nada**: las dos columnas de rutas locales que existen hoy se llaman `local_files.path` y
`library_folders.path`, y `"path".endswith("_path")` es `False`. La regla comprueba el sufijo
**`path` a secas**, que sí las cubre, además de `_local`. Una regla literal `_path` habría dejado
fuera exactamente las columnas que existe para proteger.

### Task 2 — La misma guardia, contra la BD real (`dc645d2`)

`scripts/check_persisted_urls.py`. **Importa** `find_persisted_urls` y `REMOTE_URL_ALLOWLIST` del
test; no reimplementa nada. Abre siempre en `mode=ro`. Sin BD en la ruta, imprime que omite y sale
0 (mismo trato que `verify_real_db_migration.py`: un gate que revienta en toda máquina sin la
biblioteca del autor no es un gate).

## Evidencia FND-05: salida real contra la BD v8

```
BD: C:\Users\kfern\AppData\Local\Temp\nyanko-v8-verify.sqlite3  (31.9 MB, mode=ro)
schema: v8

columnas de URL remota legitima (lista blanca) -- 5 con datos:
  OK  external_identities.url                  5099 filas empiezan por http
  OK  media_details_cache.site_url             2786 filas empiezan por http
  OK  media_details_cache.banner_image         1938 filas empiezan por http
  OK  media_details_cache.cover_image          2786 filas empiezan por http
  OK  torrent_sources.url                         1 filas empiezan por http
  --  wont_watch.cover_image                      0 filas (exenta, pero vacia)

OK: ninguna columna persistida empieza por http fuera de la lista blanca.
(12610 filas de URL remota legitima inspeccionadas: la guardia no paso en vacio)
exit=0
```

Y la ruta sin BD:

```
sin BD que inspeccionar en C:\no\existe.sqlite3: omitido
exit=0
```

Corrida contra la **copia migrada a v8**, no contra la BD de producción (que sigue en v7 y no
tiene las columnas nuevas). Correr la guardia contra la v7 es exactamente el hueco que este plan
cierra.

## La demostración de que la guardia tiene dientes

El criterio de aceptación era: **añadir una columna de texto nueva al `SCHEMA` y sembrarla con
`http://...` hace fallar el test SIN EDITAR EL TEST**. Hecho, observado, deshecho:

1. Añadida a `database.py`, en `media_details_cache`:
   `page_image_local TEXT NOT NULL DEFAULT 'http://127.0.0.1:8765/assets/p1.jpg'`
   — una columna que **`test_persisted_urls.py` no nombra en ninguna línea**.
2. `python -m pytest tests/test_persisted_urls.py::test_no_persisted_column_starts_with_http`,
   **sin tocar el test**:

```
E   AssertionError: URLs absolutas persistidas (el bug que dejó la biblioteca sin portadas):
E     media_details_cache.page_image_local: 1 fila(s) empiezan por 'http'
E   Guarda una ruta RELATIVA ('/assets/...'). Una URL con host:puerto dentro muere en cuanto
E   el sidecar arranca en otro puerto, y no se cura sola.
```

3. Revertido `database.py` (`git diff` limpio, comprobado), suite entera en verde de nuevo.

El mensaje nombra la tabla, la columna y el número de filas, que es lo que hace que el fallo sea
accionable en vez de un «algo pasó». La misma propiedad queda además fijada como test permanente
(`test_guard_covers_columns_it_never_names`, que añade la columna con `ALTER TABLE` en runtime),
para que la propiedad no dependa de que alguien repita esta demostración a mano.

## Lo que esta guardia previene, y el fallo silencioso que casi tiene

El fallo de un control sobre **datos** no es que falle: es que pase **en vacío**. Sobre una tabla
sin filas, `SELECT ... LIKE 'http%'` no encuentra nada y el test es verde **sin haber mirado
nada**. Tal cual, la guardia solo mordería al reader de la Fase 3 si a la Fase 3 le diera por
escribir filas en sus propios tests. Dos cosas lo evitan:

1. **El test de la fase corre sobre una BD sembrada**, no vacía: una fila en cada tabla que la
   fase puede tocar (26 inserts). `test_guard_is_not_passing_vacuously` afirma que la detección
   **sí encuentra** los aciertos exentos — si la siembra se rompe, ese test cae y nos enteramos,
   en vez de tener un verde hueco.
2. **`assert_no_persisted_urls` es importable.** Es el contrato con las fases siguientes.

## Para la Fase 3 (y la 7, y la 8) — el contrato

```python
from tests.test_persisted_urls import assert_no_persisted_urls
assert_no_persisted_urls(connection)   # DESPUÉS de tus escrituras, no antes
```

Llámala al final de **cualquier** test que persista una URL de página, de portada o de cualquier
asset. Está escrito también en el docstring del módulo, dirigido a quien planifique la Fase 3. Si
la Fase 3 no la invoca, la guardia se queda verde mientras el reader persiste URLs absolutas — que
es exactamente el fallo que existe para impedir. La guardia cubre las columnas nuevas de la Fase 3
por construcción; lo que no puede hacer sola es inventarse las filas.

**Y no metas una columna `*_local` / `*path` en la lista blanca para que pase.** Hay un test que
lo impide, y está ahí a propósito.

## Verificación

| Check | Resultado |
|-------|-----------|
| `python -m pytest -q` (suite completa) | **360 passed** (354 + 6 nuevos) |
| `python -m pytest tests/test_persisted_urls.py -q` | 6 passed |
| `ruff check nyanko_api/ tests/ scripts/` | limpio |
| `check_persisted_urls.py` contra la copia **v8** de la BD real | exit 0, salida arriba |
| `check_persisted_urls.py` sin BD en la ruta | exit 0, «omitido» |
| Columna nueva en `SCHEMA` + `http://` → el test falla **sin editarlo** | OK (salida arriba) |
| `cover_image_local` envenenado → el fallo nombra tabla, columna y nº de filas | OK |
| La lista blanca no contiene ninguna columna `_local` / `path` | OK (test propio) |
| La detección no está duplicada: el script importa del test | OK |
| La BD real no se modifica (`mode=ro`) | OK |
| Cero listas literales de tablas/columnas a inspeccionar en el test | OK (`sqlite_master` + `PRAGMA`) |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing correctness] La regla dura comprueba el sufijo `path`, no `_path`**
- **Found during:** Task 1
- **Issue:** El plan especificaba que ninguna columna acabada en `_local` o `_path` puede estar en
  la lista blanca. Pero las únicas dos columnas de rutas locales del esquema real son
  `local_files.path` y `library_folders.path`: **ninguna acaba en `_path`**. La regla tal cual
  escrita no cubría nada más allá de `_local` — un test verde que no protege lo que dice proteger.
- **Fix:** `column.endswith("path")` además de `endswith("_local")`, con el motivo escrito en el
  docstring del test.
- **Files modified:** `apps/backend/tests/test_persisted_urls.py`
- **Commit:** `4bf4928`

### Desviaciones deliberadas

**Sexta entrada en la lista blanca (`wont_watch.cover_image`) sin acierto que la respalde.** El
plan exigía derivar la lista blanca **corriendo la guardia** contra datos reales. Salieron 5
aciertos, no 6. `wont_watch` está vacía en la BD real (0 filas), así que la guardia no la señaló —
pero su escritor (`add_wont_watch`, `main.py:3992`) persiste la portada del CDN del proveedor que
le manda el cliente. Dejarla fuera habría hecho saltar la guardia con un **falso positivo** la
primera vez que un usuario marque algo como «no quiero verlo», y una guardia que grita con datos
legítimos es una guardia que alguien apaga. Está exenta por lo que su escritor guarda, con el
`fichero:línea` citado, y no puede tapar el bug original: los assets locales ya se persisten
**relativos** (`_asset_url`, `main.py:317`, devuelve `/assets/...` sin host ni puerto), así que un
valor local en esa columna nunca empieza por `http`.

**El RED de la Task 1 son stubs `NotImplementedError`, no un módulo ausente.** El plan pide que la
detección viva **dentro** de `tests/test_persisted_urls.py` (para que el script pueda importarla de
ahí). Test e implementación en el mismo fichero hacen imposible el RED clásico de «el módulo no
existe»: el fichero tiene que existir para que los tests existan. El RED honesto que esa forma
permite es el que se hizo — las funciones declaradas y sin cuerpo, los 5 tests de datos cayendo con
`NotImplementedError`, que es fallar por la razón correcta: la detección no existe todavía.

## Known Stubs

Ninguno. Las dos funciones están implementadas, testeadas y ejercitadas contra la BD real.

Lo que **sí** queda pendiente por diseño, y no es un stub sino el contrato de arriba:
`assert_no_persisted_urls` no tiene todavía ningún llamador fuera de este módulo y de su script.
Los llamadores son las Fases 3/7/8, tras sus propias escrituras. Hasta que el reader exista, no hay
filas de páginas que mirar.

## Threat Flags

Ninguno. El plan no añade superficie: dos ficheros nuevos, ninguna dependencia (solo `sqlite3`,
`os`, `sys`, `pathlib` de la stdlib), ningún endpoint, ninguna escritura (`mode=ro`).

Nota para la Fase 3, no un flag de esta fase: `wont_watch.cover_image` es la única columna exenta
cuyo valor **lo elige el cliente** (viene en el body de `POST /api/discover/wont-watch`). Hoy es
inocuo — un asset local se persiste relativo y no empieza por `http`. Si alguna fase futura vuelve a
componer URLs de asset absolutas en el renderer, esa columna es por donde volverían a entrar.

## Self-Check: PASSED

Ficheros creados verificados en disco:
- `apps/backend/tests/test_persisted_urls.py` — FOUND
- `apps/backend/scripts/check_persisted_urls.py` — FOUND

Commits verificados en `git log`:
- `a8f8dc4` — FOUND (Task 1 RED: la guardia falla, `NotImplementedError`)
- `4bf4928` — FOUND (Task 1 GREEN: detección por introspección del esquema)
- `dc645d2` — FOUND (Task 2: el script contra la BD real)

`apps/backend/nyanko_api/database.py` verificado **sin cambios** tras la demostración de dientes
(`git diff --quiet` → limpio).
