---
phase: 02-motor-de-fuentes-contrato-presupuesto-y-taxonom-a-de-errores
verified: 2026-07-14T00:10:00Z
status: passed
score: 12/12 must-haves verificados
behavior_unverified: 0
overrides_applied: 0
gaps: []
resolved_gaps:
  - truth: "D-08 (plan 02-02): las peticiones de lectura tienen prioridad sobre descargas cuando compiten por el mismo bucket"
    status: resolved
    fixed_by: "398404f — fix(02): read priority now works outside the 1ms grouping window"
    reason: >-
      El gap era real: `_dispatch_waiters` drenaba el heap ENTERO en una pasada, de modo que cada
      waiter despachado ya era dueno de su hueco y una lectura posterior solo podia ponerse detras
      de todas las descargas. La prioridad solo reordenaba dentro de la ventana de agrupacion de
      1 ms — cosmetica justo en el caso que importa.
    fix: >-
      Los huecos se conceden de UNO EN UNO y en la SALIDA (`_grant_slot` llamado desde
      `_release_slot`, `http.py:206-227`): quien acaba de salir abre el siguiente hueco, asi que
      el heap se consulta lo mas tarde posible, cuando la lectura prioritaria ya esta dentro.
    evidence: >-
      Re-verificado ejecutando, no leyendo el commit. `test_read_priority_overtakes_queued_downloads`
      (`test_source_budget.py:119-164`) reescrito: espera a que una descarga haya SALIDO de verdad
      (`while not salidas`) antes de meter la lectura — el escenario de produccion, no la rafaga
      simultanea. Contra el dispatcher viejo (checkout de `http.py` en 4851e0a) el test FALLA
      (`adelantadas = 0`); contra el actual pasa y la lectura adelanta >= 2 descargas ya encoladas.
      Suite completa: 407 passed.
accepted_deviations:
  - prohibition: "D-02/deferred (plan 02-01): `LocalArchiveSource` no hace ordenacion natural; el orden lexicografico queda para Fase 3"
    status: violada_deliberadamente
    evidence: >-
      El fix de CR-01 (commit 0e1c953) anadio `_natural_key` en `local_archive.py:24-28` y el test
      `test_local_archive_lists_only_images_in_natural_order` ahora asserta
      `["1.jpg", "2.jpg", "10.jpg"]` — exactamente lo contrario de lo que el plan 02-01 exigia
      ("el orden devuelto es lexicografico `1.jpg`, `10.jpg`, `2.jpg`").
    assessment: >-
      Adelanta RD-01 (Fase 3) por 5 lineas. No es un blocker del goal: es comportamiento correcto y
      la deuda va en la direccion buena. Se registra para que no pase como aprobado en silencio.
      CBZ y ComicInfo.xml siguen sin leerse, asi que el resto de D-02 se respeta.
---

# Fase 2: Motor de fuentes — Informe de Verificacion

**Goal de la fase:** Existe un contrato de fuente versionado contra el que se puede construir, con el
presupuesto de peticiones **en el motor y no en sus llamadores**, y con los errores tipados antes de
que exista un solo consumidor.

**Verificado:** 2026-07-13 (inicial) · **Re-verificado:** 2026-07-14 (tras el fix de D-08)
**Estado:** passed
**Re-verificacion:** Si — el unico gap de la pasada inicial (D-08) esta cerrado y comprobado

## Veredicto

**Los 6 criterios de exito del ROADMAP se cumplen, y las 12 verdades observables tambien.** Los
verifique contra el codigo y ejecutandolo, no contra los SUMMARY. Los 4 blockers del code review
estan realmente cerrados (no solo commiteados).

La pasada inicial encontro **un** gap, en una promesa del plan 02-02 y no del ROADMAP: D-08
(prioridad de lectura sobre descargas) era cosmetica fuera de una ventana de 1 ms — y tenia un test
verde encima. Se arreglo en `398404f` y **el fix esta comprobado ejecutando**, no dado por bueno por
estar commiteado: el test nuevo falla contra el dispatcher viejo y pasa contra el actual (ver la
seccion «Gap cerrado»).

Que importara ahora y no en Fase 7 era el punto: el ROADMAP pone esta fase antes del reader online y
de la cola de descargas precisamente para cerrar Seam F («retrofittearlo despues obliga a reescribir
todos los adapters»). Un mecanismo de prioridad que *parece* correcto (kwarg + heap + test verde) es
exactamente la trampa armada-pero-no-disparada que esta fase existe para desactivar. Se desactivo
aqui, con ~10 lineas, y no en Fase 8 con dos consumidores encima.

## Logro del Goal

### Verdades Observables

| #  | Verdad | Estado | Evidencia |
|----|--------|--------|-----------|
| 1 | **SC1** — fuente con `api_version` distinta se rechaza, se reporta en la UI, el sidecar arranca igual | VERIFICADO | `registry.py:36-42` rechaza por version; `register()` esta **dentro** del try en `build_source_registry` (`registry.py:108-114`, fix CR-03). `test_a_broken_source_never_takes_down_the_sidecar` cubre constructor que revienta + `name` ausente + nombre duplicado. `/api/sources` devuelve `status`/`rejection_reason` (`main.py:1497-1515`). Ejecutado: registry arranca con `[('local_archive','ok')]` |
| 2 | **SC2** — test de conformidad parametrizado sobre todas las fuentes registradas, incluida `LocalArchiveSource` | VERIFICADO | `test_sources.py:119-127`: `@pytest.mark.parametrize("source_class", SOURCES)` sobre el registro real + `isinstance(source, Source)` + verificacion de firmas de `search`/`chapters`/`pages`. Anadir una fuente que no cumpla el Protocol rompe el test |
| 3 | **SC3** — 0 resultados lanza `ParseError`, nunca `[]`; un fallo no pisa cache buena | VERIFICADO | `engine.py:87-94` (cache solo tras resultado valido; en `SourceError` devuelve la cacheada) y `local_archive.py:66,94`. Tests: `test_chapters_returns_good_cache_after_source_parse_error`, `test_chapters_rethrows_parse_error_without_cache`, `test_empty_chapters_are_parse_error_and_do_not_cache_empty_list` (asserta `engine._chapters == {}`) |
| 4 | **SC4** — dos consumidores simultaneos beben del mismo cubo; el ritmo agregado no supera el presupuesto | VERIFICADO | Un unico `RateLimitedClient` por fuente, creado por `engine.build_source_fetcher` e inyectado (`registry.py:109-111`). `test_consumers_share_one_source_bucket` lanza 2 lecturas + 2 descargas sobre el mismo fetcher y asserta sleeps acumulativos `[0.0, 1.0, 2.0, 3.0]` a 60 req/min. Con dos cubos saldria `[0,1,0,1]`: el test tiene dientes. Pide `real_rate_limit_sleep` (sin ese fixture seria verde vacio) |
| 5 | **SC5** — la fuente declara headers como dato y el fetcher generico los aplica | VERIFICADO | `SourceCapabilities.headers` (`contract.py:13`); `DefaultSourceFetcher.request` los mergea (`engine.py:46-49`). `grep` de `if source.name ==` en `sources/` y `main.py`: **cero** ramas por nombre. `test_source_fetcher_applies_declared_headers` lo prueba con `Referer` + `User-Agent` |
| 6 | **SC6** — en build empaquetado PyInstaller onedir la lista de fuentes no esta vacia | VERIFICADO | **Ejecutado, no inferido:** `pytest tests/test_packaged_sources.py` → 1 passed en 72s. Construye un onedir real con `pyinstaller nyanko-api.spec` en tmp, lo lanza con `NYANKO_DATA_DIR` fresco y puerto propio leido de `<data_dir>/port`, y asserta `len(payload) > 0` con el pid vivo. No skippea. `grep pkgutil\|importlib\|__subclasses__` en `sources/`: **limpio**. `SOURCES = [LocalArchiveSource]` escrito a mano (`__init__.py:22`) |
| 7 | **D-05/D-06** — el motor crea el bucket y lo inyecta; los llamadores no poseen el presupuesto | VERIFICADO | `build_source_fetcher` vive en `engine.py:58-64`; ningun llamador construye un `RateLimitedClient` de fuente. `test_sources_package_does_not_reimplement_rate_limiting` asserta que `sources/` no contiene `class RateLimited`, `next_slot` ni `Semaphore` |
| 8 | **D-07** — `requests_per_minute` se acota a un techo global antes de construir el bucket | VERIFICADO | `_bounded_requests_per_minute` (`engine.py:119-124`), `SOURCE_RATE_LIMIT_CEILING = 120`. `test_registry_builds_one_rate_limited_fetcher_per_source`: una fuente que declara 600 queda en 120 |
| 9 | **D-08** — las peticiones de lectura tienen prioridad sobre descargas cuando compiten por el mismo bucket | VERIFICADO (tras fix `398404f`) | Fallido en la pasada inicial; cerrado ahora. Los huecos se conceden de uno en uno en la SALIDA (`_grant_slot` desde `_release_slot`, `http.py:206-227`), asi que el heap se consulta cuando la lectura ya esta dentro. Comprobado ejecutando: el test reescrito espera a que una descarga haya salido de verdad y luego mete la lectura; **falla contra el dispatcher viejo** (`adelantadas = 0`) y pasa contra el actual. Ver «Gap cerrado» |
| 10 | **D-16** — una fuente que carga bien pero falla siempre sigue viva con `status == "ok"` | VERIFICADO | `_AlwaysFailSource` en `test_source_api.py:83` aparece como `ok`; nada la desactiva sola |
| 11 | **D-12** — el mensaje depende del TIPO de error, no de `str(exc)` | VERIFICADO | `source_error_action` (`errors.py:34-39`): `SourceRateLimitError`→`esperar`, `SourceNetworkError`→`reintentar`, resto→`actualizar_la_fuente`. Unit-tested |
| 12 | **D-01/D-03/D-13** — Protocol con exactamente 3 metodos, tipos propios separados de `models.py`, version entera exacta | VERIFICADO | `contract.py`: `SOURCE_API_VERSION = 1` (int), `@runtime_checkable class Source(Protocol)` con solo `search`/`chapters`/`pages`. Sin `popular`/`latest`/`series_detail`. `SourceSeries`/`SourceChapter`/`SourcePage` no importan ni heredan de `nyanko_api.models` |

**Score: 12/12 verdades verificadas** (11/12 en la pasada inicial; D-08 cerrado en `398404f`).

### Los 4 blockers del review: verificados como cerrados

No los di por buenos por estar commiteados — los verifique en el codigo.

| ID | Fix | Estado | Evidencia |
|----|-----|--------|-----------|
| CR-01 | Orden natural de paginas y capitulos | CERRADO | `_natural_key` (`local_archive.py:24-28`) usado en **ambos** `sorted()` (lineas 62 y 90). Test asserta `["1.jpg","2.jpg","10.jpg"]` e `index == [1,2,3]` |
| CR-02 | `_call_source` tipa toda excepcion que escape | CERRADO | `engine.py:107-116`: `except SourceError: raise` → `HTTPStatusError` → `httpx.HTTPError` (cubre `RemoteProtocolError`, `ProxyError`, `DecodingError`, `TooManyRedirects`) → `except Exception` como red de seguridad final. Un caller con `except SourceError` ya no se come un 500 |
| CR-03 | `register()` dentro del try | CERRADO | `registry.py:108-114`. `_reject_broken_source` tolera factories sin `__name__` y no relanza en duplicado. **Directamente relevante a SC1** |
| CR-04 | `register()` rechaza capabilities que no sean `SourceCapabilities` | CERRADO | `registry.py:49-51`. Esto restaura el invariante del que depende `main.py`: `_reject` deja `source=None`, y `register()` solo guarda `source=source` tras pasar el `isinstance`. Por tanto `registration.source is not None` ⇒ capabilities validas ⇒ el `asdict()` de `main.py:1505` no puede reventar. El fix elegido es el que el propio review recomendaba como mejor («validar en `SourceRegistry.register()`, de modo que main.py pueda confiar en el invariante») |

### Cobertura de Requisitos

Todos los IDs de la fase estan reclamados por algun plan. Cero huerfanos.

| Requisito | Planes | Descripcion | Estado | Evidencia |
|-----------|--------|-------------|--------|-----------|
| SRC-04 | 02-01, 02-03 | Fuente rota/maliciosa no tumba el sidecar; version comprobada al registrar; rechazada visible en UI | SATISFECHO | SC1 + SC6. Constructor que revienta, `name` ausente, nombre duplicado y capabilities basura: todos salen como `rejected` y el registry sigue construyendo |
| SRC-05 | 02-01, 02-02, 02-03 | Cada fuente declara sus headers como dato; el fetcher sigue generico | SATISFECHO | SC5. Cero ramas `if source.name`. `/api/sources` expone capacidades como dato |
| SRC-06 | 02-02 | El presupuesto lo posee el motor, no sus llamadores; prefetch y cola beben del mismo cubo | SATISFECHO | SC4 + D-05/D-06 + D-07: el cubo es unico por fuente y el ritmo agregado respeta el presupuesto. Y desde `398404f` tambien se **reparte** bien (D-08): la cola de descargas ya no puede matar de hambre al prefetch del reader. Se cumplen las dos mitades: no exceder el presupuesto y repartirlo con prioridad |
| SRC-07 | 02-01, 02-02 | 0 resultados falla; un fallo nunca pisa una lista buena cacheada | SATISFECHO | SC3 |

### Trazabilidad de plan → ROADMAP

| Plan | Requisitos declarados | Cubiertos |
|------|----------------------|-----------|
| 02-01 | SRC-04, SRC-05, SRC-07 | Si |
| 02-02 | SRC-05, SRC-06, SRC-07 | Si (SRC-06 completo tras `398404f`) |
| 02-03 | SRC-04, SRC-05 | Si |

`.planning/REQUIREMENTS.md` mapea SRC-04..07 a Fase 2. Los 4 aparecen en las frontmatter de los
planes. **Cero requisitos huerfanos.**

### Prohibiciones

| Prohibicion | Estado | Evidencia |
|-------------|--------|-----------|
| D-15: nada de `pkgutil`/`importlib`/`__subclasses__` | RESPETADA (test-tier) | `grep` limpio en `sources/` y en `test_packaged_sources.py`. `test_sources_init_uses_explicit_list` + el test onedir dan la enforcement evidence |
| D-06: un modulo de fuente no importa `httpx`/`requests`/`urllib`/`aiohttp` | RESPETADA (test-tier) | Import-guard AST que descubre las fuentes desde el registry (no lista a mano) + test negativo `test_network_import_guard_fails_for_registered_source_with_httpx`. `engine.py` si importa `httpx`, y debe: es el fetcher generico, no una fuente |
| D-09: 0 resultados lanza, nunca `[]` | RESPETADA (test-tier) | SC3 |
| D-04: la app no persiste URLs de fuente | RESPETADA (test-tier) | `test_phase_2_does_not_add_source_persistence_columns` + `assert_no_persisted_urls`. Fase 2 no toca `database.py` |
| D-11 / D-14 / trampa A | RESPETADAS | Cache buena no se pisa; fuente rechazada no desaparece; `RateLimitedClient` no se reimplementa |
| **D-02: `LocalArchiveSource` no hace ordenacion natural** | **VIOLADA (deliberadamente)** | El fix de CR-01 anadio orden natural, adelantando RD-01 de Fase 3. Ver `accepted_deviations` en la frontmatter. CBZ y `ComicInfo.xml` siguen sin leerse |

### Anti-patrones

| Fichero | Patron | Severidad | Impacto |
|---------|--------|-----------|---------|
| — | `TODO`/`FIXME`/`XXX`/`TBD`/`HACK`/`PLACEHOLDER` | — | **Cero marcadores de deuda** en `sources/` y `http.py` |

### Spot-checks de comportamiento

| Comportamiento | Comando | Resultado | Estado |
|----------------|---------|-----------|--------|
| Suite completa (re-verificacion) | `pytest tests/ -q --ignore=tests/test_packaged_sources.py` | **407 passed** | PASS |
| Suite de fuentes | `pytest tests/test_sources.py tests/test_source_budget.py tests/test_source_engine.py tests/test_source_api.py tests/test_http.py tests/test_persisted_urls.py -q` | 73 passed | PASS |
| Build empaquetado (SC6) | `pytest tests/test_packaged_sources.py -q` | 1 passed en 72.06s | PASS |
| Registry arranca sin carpetas | `build_source_registry(library_folders=[])` | `[('local_archive','ok')]` | PASS |
| Sin autodiscovery | `grep pkgutil\|importlib\|__subclasses__ sources/` | limpio | PASS |
| Sin ramas por nombre de fuente | `grep "if source.name ==" sources/ main.py` | limpio | PASS |
| **Prioridad de lectura fuera de la ventana** (inicial) | Probe: 10 descargas despachadas + 1 lectura prioritaria a 60 req/min | descarga peor 9.0s, **lectura 10.0s** | FAIL → cerrado |
| **Prioridad de lectura, re-verificada** | `pytest tests/test_source_budget.py -q` con `http.py` revertido a `4851e0a` | `test_read_priority_overtakes_queued_downloads` FALLA (`adelantadas = 0`); con el `http.py` actual pasa | PASS (test con dientes) |
| Export de `SourceEngine` | `from nyanko_api.sources import SourceEngine` | `ImportError` | FAIL (warning) |

## Gap cerrado

### 1. D-08: la prioridad de lectura no adelantaba nada en produccion — RESUELTO en `398404f`

**Estado:** cerrado y **comprobado ejecutando**, no dado por bueno por estar commiteado.

**El fix:** los huecos se conceden de **uno en uno** y **en la salida**. `_grant_slot`
(`http.py:206-217`) saca UN waiter del heap, le asigna el deadline y vuelve; lo llama
`_release_slot` (`http.py:219-227`), de modo que quien acaba de salir es quien abre el siguiente
hueco. El reparto ocurre lo mas tarde posible, asi que el heap se consulta cuando la lectura
prioritaria ya esta dentro — en vez de cuando todas las descargas ya eran duenas de su hueco.

**La prueba de que el test tiene dientes:** `test_read_priority_overtakes_queued_downloads` se
reescribio para esperar a que una descarga haya **salido de verdad** (`while not salidas`) antes de
lanzar la lectura: el escenario de produccion (descargas en curso + lectura interactiva despues), no
la rafaga simultanea. Revertido `http.py` al dispatcher viejo (`git show 4851e0a`), el test **falla**
(`adelantadas = 0`); con el actual, la lectura adelanta >= 2 descargas ya encoladas. Suite completa:
**407 passed**.

El registro de por que existia el gap se conserva abajo, porque la leccion (un mecanismo con kwarg,
heap y test verde que no adelantaba nada) es justo la clase de trampa que esta fase se planifico
primero para desactivar.

<details>
<summary>Diagnostico original (pasada de verificacion inicial)</summary>

**Que se prometio:** «las peticiones de lectura tienen prioridad sobre descargas cuando compiten por
el mismo bucket» (must-have del plan 02-02). El plan incluso aviso contra la version cosmetica: «Un
kwarg `priority` que entra a la misma cola FIFO de `state.lock` no cumple D-08».

**Que hay:** la implementacion no es FIFO — es un heap `(-priority, sequence, future)`, que es mejor
que el hombre de paja que el plan prohibia. Pero `_dispatch_waiters` **drena el heap entero** en una
sola pasada:

```python
while state.waiters:
    _priority, _sequence, future = heapq.heappop(state.waiters)
    deadline = max(loop.time(), state.next_slot)
    state.next_slot = deadline + self._interval
    future.set_result(deadline)
```

Cada waiter drenado empuja `next_slot` hacia adelante. Una lectura que llega despues del drenaje
encuentra el heap vacio, entra sola, y recibe `deadline = max(now, next_slot)` — o sea, **detras de
todas las descargas ya despachadas**. El heap solo reordena entre peticiones que caen en la misma
ventana de agrupacion de 1 ms.

**Probe ejecutado** (60 req/min, `RateLimitedClient` real, sleeps grabados):

```
peor descarga espera : 9.0s
lectura tardia espera: 10.0s
→ la lectura prioritaria queda DETRAS de todas las descargas
```

**Por que el test verde no lo pillo:** `test_read_priority_overtakes_queued_downloads` hace busy-wait
(`while len(state.waiters) < 2`) hasta tener las descargas encoladas, y solo entonces mete las
lecturas — metiendo las 4 peticiones dentro de la ventana de 1 ms. Prueba la rafaga simultanea, que
es el caso que **no** ocurre. En produccion las descargas se despachan segun llegan y la lectura
interactiva llega despues.

**Por que no puede esperar a Fase 7/8:** el ROADMAP pone esta fase antes que el reader online y la
cola de descargas precisamente para cerrar Seam F («retrofittearlo despues obliga a reescribir todos
los adapters»). Hoy el arreglo son ~10 lineas en `http.py`. Con Fase 7 y Fase 8 encima, es un cambio
en el reparto de huecos con dos consumidores reales dependiendo de el.

**Fix:** que el reloj de salidas reparta **de uno en uno** en vez de drenar: sacar un waiter,
asignarle el slot, y re-programar el dispatch para `next_slot`, de modo que un waiter de mayor
prioridad que llegue entretanto entre por delante en el heap.

**Alternativa legitima:** si se decide que la prioridad justa es problema de Fase 7/8, hay que
(a) poner un `# ponytail:` que nombre el techo REAL — el actual (`http.py:200-202`) dice que la
ventana «permite que lectura adelante descargas ya encoladas», que es justo lo que el probe
falsifica — y (b) registrar un override en este fichero. Lo que no puede quedarse es un mecanismo que
parece funcionar, tiene test verde, y no adelanta nada.

_(Se eligio el fix, no la alternativa.)_

</details>

## Warnings (no bloquean el goal)

Del review original, deliberadamente no arreglados. Los peso contra el goal:

- **WR-01 — `SourceEngine` no exportado ni cableado.** Confirmado ejecutando:
  `from nyanko_api.sources import SourceEngine` → `ImportError`; hay que ir por
  `nyanko_api.sources.engine`. **No socava el goal.** El presupuesto SI esta en el motor:
  `build_source_fetcher` vive en `engine.py`, lo llama `build_source_registry`, y el `lifespan` lo
  cablea (`main.py:1408`). Ningun llamador construye un bucket de fuente. Y el goal dice literalmente
  «antes de que exista un solo consumidor», asi que que `SourceEngine` no tenga consumidor es *el
  diseno*, no un fallo. Lo que si es real es que la superficie publica del paquete miente: los otros
  cuatro modulos se re-exportan y `engine.py` no. Coste del arreglo: 4 lineas en `__init__.py`.
- **WR-03 — el fallback a cache traga `SourceRateLimitError` y `SourceNotFoundError`.** `engine.py:89`
  usa `except SourceError:` a secas. Devolver cache ante un 429 significa que el caller nunca se
  entera de que le estan limitando y sigue pegandole a la fuente. Es back-pressure perdida — la misma
  familia de fallo que SRC-06 existe para evitar. Barato de arreglar ahora
  (`except (SourceParseError, SourceNetworkError)`), y se vuelve un baneo de IP en Fase 7/8.
- **WR-06 — el registry se construye una sola vez en `lifespan`.** Las carpetas de biblioteca
  anadidas en caliente son invisibles para `LocalArchiveSource` hasta reiniciar. Latente hoy (nada
  consume el engine), bug de usuario en cuanto se cablee en Fase 3.
- **WR-08 — los `RateLimitedClient` por fuente nunca se cierran** (`aclose()` no se llama en el
  shutdown del `lifespan`).
- WR-04, WR-05, WR-07, WR-09..WR-12 e IN-01..IN-07: sin impacto sobre los 6 criterios del ROADMAP.

## Resumen

El contrato versionado existe, es testeable y esta empaquetado (verificado contra un onedir real de
PyInstaller, no contra el arbol de desarrollo). Los errores estan tipados con su mapeo a accion de UI
antes de que exista un consumidor, tal y como pedia el goal. El presupuesto **es del motor**: un
`RateLimitedClient` por fuente, creado en `engine.py`, acotado a un techo global, inyectado en la
fuente, y ningun llamador lo posee. Los 4 blockers del review estan realmente cerrados, no solo
commiteados.

Y el **reparto** de ese presupuesto entre los dos consumidores que la fase existe para anticipar
tambien se cumple, tras `398404f`: la prioridad de lectura era cosmetica fuera de una ventana de 1 ms
—con test verde encima, que es lo peor— y ahora adelanta de verdad, con un test que falla contra el
codigo viejo. Era el unico gap, costo ~10 lineas de `http.py` pagadas aqui y no en Fase 8, y era
exactamente el tipo de trampa armada-pero-no-disparada que esta fase se planifico primero para
desactivar.

Quedan warnings no bloqueantes (WR-01 export de `SourceEngine`, WR-03 fallback a cache ante 429,
WR-06 registry construido una sola vez, WR-08 clients sin cerrar). Ninguno toca los criterios del
ROADMAP; WR-06 y WR-03 se vuelven visibles al cablear el engine, asi que entran como contexto de la
Fase 3.

**Fase 2 cerrada: passed.**

---

_Verificado: 2026-07-13 · Re-verificado tras el fix de D-08: 2026-07-14_
_Verificador: Claude (gsd-verifier)_
