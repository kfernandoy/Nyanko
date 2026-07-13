# Phase 2: Motor de fuentes — contrato, presupuesto y taxonomía de errores - Context

**Gathered:** 2026-07-13
**Status:** Ready for planning

<domain>
## Phase Boundary

Existe un contrato de fuente **versionado** contra el que se puede construir, con el presupuesto de
peticiones **en el motor y no en sus llamadores**, y con los errores **tipados antes de que exista un
solo consumidor**. Entrega: el Protocol de fuente + registro + fetcher con presupuesto + taxonomía de
errores + `LocalArchiveSource` mínima como primer adapter que le da dientes al test de conformidad.

Requisitos: SRC-04, SRC-05, SRC-06, SRC-07.

**Fuera de esta fase:** el reader y el page pipe (Fase 3), el vínculo fuente↔tracker (Fase 4), la
instalación de fuentes de terceros y el trust gate (Fase 6), las fuentes online reales (Fase 7), la
cola de descargas y la persistencia de la caché (Fase 8).

</domain>

<decisions>
## Implementation Decisions

### Superficie del contrato

- **D-01: Contrato mínimo de lectura.** El Protocol expone `search()` / `chapters(serie)` /
  `pages(capítulo)` y nada más, más un `SourceCapabilities` (frozen dataclass, calcado de
  `ProviderCapabilities` en `providers.py:29`) donde cada fuente declara lo que **no** hace —
  `LocalArchiveSource` no busca online, y sin capacidades tendría que mentir o llenar el Protocol de
  `NotImplementedError`. Populares / novedades / ficha de serie (el espejo de Mihon) se rechazaron:
  son cuatro métodos sin un solo consumidor en las Fases 3, 5, 7 y 8.
  **Consecuencia asumida:** ampliar el contrato en la Fase 7 sube `SOURCE_API_VERSION` y expulsa a las
  fuentes ya escritas hasta que se actualicen. Quitar es gratis, añadir es caro — se eligió a
  sabiendas, porque hoy el autor escribe todas las fuentes.

- **D-02: `LocalArchiveSource` mínima nace en esta fase.** Sabe listar los capítulos de una carpeta y
  decir qué imágenes tiene cada uno. **No** lee CBZ, no ordena naturalmente, no interpreta
  `ComicInfo.xml` — eso es la Fase 3 (RD-01). Motivo: el test de conformidad del criterio 2 se prueba
  contra una fuente **real**; una fuente falsa de tests solo demuestra que el contrato es coherente
  consigo mismo. La Fase 3 se encuentra el enchufe puesto.

- **D-03: Tipos propios del motor.** La fuente devuelve `SourceSeries` / `SourceChapter` /
  `SourcePage` (nombres orientativos), **separados** de los modelos Pydantic del tracker
  (`models.py`). Una serie de una fuente NO es una entrada de tu AniList: confundirlas es exactamente
  el desastre que la Fase 4 existe para prevenir (leer el cap. 12 de la serie A y escribir progreso en
  la B). Tenerlas separadas hace ese error imposible de escribir por accidente.

- **D-04: Identidad = identificador opaco, nunca URL.** La fuente devuelve un id suyo (`"oneshot-42"`)
  y la app persiste `(source_name, source_id)` tal cual. La app **nunca ve ni guarda una URL**: para ir
  a la web le pasa el id a la fuente y ella sabrá. Razones, en orden: (a) no puede chocar con la
  guardia FND-05 de la Fase 1 (ninguna columna persistida empieza por `http`, ni contiene el sidecar);
  (b) si el sitio cambia de dominio, lo persistido sigue valiendo. Se rechazó el path relativo estilo
  Mihon (`/manga/berserk`): pasa la guardia por los pelos y acopla lo guardado a la estructura de URLs
  del sitio.

### Presupuesto de peticiones (SRC-06 — Seam F)

- **D-05: Un cubo por fuente.** El motor crea el `RateLimitedClient` **al registrar** la fuente y todo
  consumidor de esa fuente bebe de él. Esto es literalmente el criterio 4: prefetch del reader y cola
  de descargas → el mismo cubo. Se rechazó el cubo por dominio (más fiel a la realidad —quien banea es
  el host— pero deja sin dueño el presupuesto de un CDN compartido) y el cubo partido en dos (API vs
  imágenes); si las ráfagas de páginas ahogan la API, se parte entonces.

- **D-06: El fetcher se inyecta Y un test caza al que se lo salte.** La fuente recibe del motor el
  único medio que tiene de pedir cosas a la red (no puede fabricarse otro), **y** el test de
  conformidad recorre el módulo de cada fuente registrada y **falla** si importa `httpx` / `requests` /
  `urllib` / `aiohttp` por su cuenta. La inyección lo hace incómodo; el test lo hace imposible de colar
  en silencio. El bloqueo real de imports es el trust gate de la Fase 6 (código de terceros), no el
  contrato de hoy.

- **D-07: La fuente declara su ritmo; el motor lo acota a un techo.** Cada fuente declara sus
  peticiones/minuto **como dato** (junto a `Referer`/UA — SRC-05); el motor lo recorta contra un techo
  global. Es la misma lógica que la Fase 1 ya dejó escrita en el limitador (el número declarado es una
  petición, no una orden: `budget` acotado a `[1, techo]`), y evita que una fuente de terceros (Fase 6)
  declare 600/min y nos gane el baneo.

- **D-08: La lectura pasa delante de la descarga.** Las peticiones llevan prioridad; el prefetch del
  reader va primero y la cola de descargas usa lo que sobre. Motivo: el usuario ve congelarse la
  lectura, no ve ir despacio la descarga. Se decide **ahora** porque retrofittearlo en la Fase 8
  obliga a volver a tocar el motor — y esta fase existe precisamente para meter esa costura dentro.

### Errores y caché (SRC-07)

- **D-09: Familia de errores tipados.** `SourceError` base + hijos: red / parseo / rate limit / no
  existe / no soportado (nombres a fijar en el plan; la convención del árbol es `XError(RuntimeError)`
  por módulo). El motor decide por el **tipo**, no leyendo el mensaje — es lo único que permite
  reintentar un fallo de red y **no** reintentar un parseo roto. Un parseo con 0 resultados **lanza**
  (`ParseError`), nunca devuelve `[]`.

- **D-10: Reintenta el motor, nunca la fuente.** La fuente falla y ya. El motor reintenta la red con
  espera creciente (`retry_with_backoff` ya existe en `http.py:30`) y **jamás** reintenta un parseo:
  volver a pedirlo solo gasta presupuesto y acerca el baneo. Si cada fuente reintentase por su cuenta,
  los reintentos no contarían en el cubo de nadie.

- **D-11: Caché en memoria del motor, con la regla dura.** El motor guarda la última lista **buena** de
  capítulos por serie mientras la app esté abierta. Regla: **solo se escribe con un resultado válido;
  un error nunca borra ni pisa lo que había.** Esto es el criterio 3 (reto de Cloudflare que responde
  HTTP 200 con HTML → la lista cacheada sigue intacta). Persistirla en SQLite se **difiere a la Fase 8**
  (la necesita la lectura offline, no el contrato) — pero la regla, que es lo irreversible, queda
  escrita y testeada aquí.

- **D-12: Mensaje según el tipo de error.** Sin conexión → reintentar; fuente rota (el sitio cambió) →
  actualizar la fuente; te están limitando → esperar. Sale gratis en cuanto los errores están tipados,
  y es la diferencia entre que el usuario sepa si el problema es suyo o de la fuente.

### Registro, versionado y rechazo (SRC-04)

- **D-13: `SOURCE_API_VERSION` = entero, coincidencia exacta.** La app habla la 1; una fuente que no
  declare exactamente 1 se rechaza al registrar. Regla sin interpretaciones, y hoy barata (el autor
  escribe todas las fuentes). Coste asumido para cuando exista ecosistema: subir la versión expulsa a
  todas las fuentes hasta que su autor las actualice. Rango de compatibilidad y semver se rechazaron
  por expresividad sin ecosistema que la use.

- **D-14: La fuente rechazada sigue en la lista, marcada.** Existe una lista de fuentes que incluye
  **todas**: las buenas, y las rechazadas con su motivo (`hecha para la v2, esta app habla la v1`,
  `reventó al cargar`). Una fuente rechazada que simplemente desaparece produce exactamente la queja
  que la Fase 6 va a recibir: «instalé la fuente y no está». El sidecar **arranca igual**: una fuente
  rota no tumba la app.

- **D-15: El registro se monta al arrancar y se rehace entero.** Imports explícitos + lista `SOURCES`
  — **jamás** `pkgutil`/`importlib` autodiscovery, que en el build frozen encuentra cero y envía un
  catálogo vacío que en dev funcionaba (criterio 6; el precedente vivo es
  `nyanko_api/detectors/__init__.py`, imports explícitos + `__all__`). Cuando la Fase 6 instale una
  fuente nueva, el registro se **reconstruye entero**: sin altas/bajas individuales (maquinaria sin
  usuario hoy), pero **sin obligar a reiniciar la app** (congelar la lista al arrancar es una decisión
  cara de deshacer).

- **D-16: Sin desactivación automática de fuentes.** Una fuente que carga bien pero falla siempre en
  uso se reporta con su tipo de error y sigue viva; decide el usuario. No hay ni una fuente online
  contra la que calibrar cuántos fallos son «rota», y un circuit breaker mal calibrado apaga una fuente
  buena por un mal rato del servidor. Se reconsidera en la Fase 7, con fuentes reales delante.

### Claude's Discretion

- Nombres exactos de tipos, clases de error y módulos (`sources/` package vs módulo plano) — el plan
  decide, siguiendo la convención del árbol.
- El valor concreto del techo global de peticiones/minuto (D-07) y el `max_concurrency` por fuente.
- Cómo se expone la lista de fuentes con estado (D-14) al renderer: endpoint REST nuevo vs ampliar uno
  existente.
- Mecanismo del test de guardia de D-06 (AST vs grep sobre el módulo de la fuente).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requisitos y alcance
- `.planning/ROADMAP.md` § "Phase 2: Motor de fuentes" — goal, los 6 criterios de éxito, y qué cierra
  (Seam F, Pitfalls 4 y 5, la trampa de PyInstaller).
- `.planning/REQUIREMENTS.md` — SRC-04 (versión comprobada al registrar, fuente rechazada no tumba el
  sidecar), SRC-05 (headers como dato), SRC-06 (el presupuesto lo posee el motor), SRC-07 (0 resultados
  falla; un fallo no pisa caché buena).
- `.planning/STATE.md` § "Decisiones que fijan el diseño" — D-1 (cero fuentes enviadas), D-2 (las
  fuentes viven en `nyanko-extensions`), D-3 (el bundle es código → trust gate en la Fase 6), D-4.
- `.planning/PROJECT.md` § Constraints — semver estricto, seguridad de Electron, Windows.

### Precedente en el árbol (leer antes de inventar nada)
- `apps/backend/nyanko_api/providers.py` — `MediaProvider` (Protocol, línea 47), `ProviderCapabilities`
  (frozen dataclass, línea 29), `ProviderRegistry` (línea 351: `register()` revienta en duplicado),
  `build_provider_registry()` (línea 372: lista explícita). **Es la plantilla del contrato de fuente.**
- `apps/backend/nyanko_api/http.py` — `RateLimitedClient` tal como lo dejó la Fase 1: presupuesto de
  `X-RateLimit-Limit` acotado al techo del constructor (`_observe_budget`, línea 154), `_LoopState` por
  event loop (línea 141), semáforo = peticiones en vuelo y el sleep **fuera** del semáforo,
  `retry_with_backoff` (línea 30). **Es el cubo que el motor pasa a poseer — no se reimplementa.**
- `apps/backend/nyanko_api/detectors/__init__.py` — imports explícitos + `__all__`. El precedente
  anti-`pkgutil` que exige el criterio 6.
- `apps/backend/nyanko-api.spec` — `hiddenimports += collect_submodules('nyanko_api')`. Los módulos
  in-tree sí se congelan; la trampa de PyInstaller es el **descubrimiento en runtime**, no el empaquetado.

### Fase 1 (lo que este motor no puede romper)
- `apps/backend/tests/test_persisted_urls.py` + el helper `assert_no_persisted_urls` — la guardia FND-05
  (dos capas: prefijo `http`, y **nada** exime de persistir una URL al propio sidecar). D-04 existe para
  no chocar con ella; toda escritura nueva de esta fase debe llamarla.
- `apps/backend/tests/test_http.py` — los tests del limitador arreglado.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `ProviderRegistry` + `ProviderCapabilities` + `MediaProvider` (`providers.py`): la forma exacta del
  contrato + registro que esta fase necesita, ya escrita y en uso para AniList/MAL/Kitsu. El motor de
  fuentes es su gemelo, no un invento nuevo.
- `RateLimitedClient` (`http.py`): el cubo. El motor instancia uno por fuente con el ritmo declarado
  (acotado al techo) — no se escribe otro limitador.
- `retry_with_backoff` (`http.py:30`): el reintento del motor (D-10).
- Convención de errores del árbol: `AniListError(RuntimeError)`, `KitsuError`, `MyAnimeListError` — uno
  por módulo, sin jerarquía común. La familia de `SourceError` es la primera jerarquía real; que sea
  deliberada y no un accidente.

### Established Patterns
- Registro por lista explícita (`build_provider_registry`) y `register()` que revienta en duplicado.
- Paquete con imports explícitos + `__all__` (`detectors/__init__.py`), nunca autodiscovery.
- Backend plano: `nyanko_api/*.py` + un solo subpaquete (`detectors/`). Un subpaquete `sources/` sería
  el segundo — coherente con el precedente.
- Tests por módulo en `apps/backend/tests/test_*.py`, con `conftest.py` y `fixtures/`.

### Integration Points
- El registro de fuentes se construye al arrancar el sidecar (junto a `build_provider_registry`, en el
  arranque de `main.py`) y se expone al renderer por la API (D-14: lista con estado, incluidas las
  rechazadas).
- `LocalArchiveSource` necesita saber dónde están los archivos del usuario: se apoya en las carpetas de
  biblioteca ya existentes (`library_folders` / `scanner.py`), no inventa configuración nueva.
- El presupuesto (D-05..D-08) es la superficie que consumirán el prefetch del reader (Fase 3) y la cola
  de descargas (Fase 8). Ambos consumidores se **simulan** en el test del criterio 4 antes de existir.

</code_context>

<specifics>
## Specific Ideas

- El test del criterio 3 debe simular el reto de Cloudflare tal cual: **HTTP 200 con cuerpo HTML** (no
  un 403, no un timeout). Ese es el caso que convierte «este capítulo tiene 0 páginas» en algo
  cacheado para siempre.
- El test del criterio 6 tiene que correr contra el **build empaquetado** (PyInstaller onedir), no
  contra el árbol: la lista de fuentes registradas no puede estar vacía. En dev siempre funciona.
- El test del criterio 4 lanza **dos consumidores simultáneos** de la misma fuente y comprueba el ritmo
  **agregado** contra el presupuesto declarado. Dos limitadores individualmente correctos dan el doble
  de ritmo: eso es lo que el test tiene que ser capaz de fallar.

</specifics>

<deferred>
## Deferred Ideas

- **Persistir la caché de listas de capítulos en SQLite** (esquema v9) — la necesita la lectura offline;
  va con la cola de descargas, **Fase 8**. La regla de escritura (D-11) se escribe ahora; el almacén,
  no.
- **Desactivación automática de una fuente rota** (circuit breaker tras N fallos) — se calibra en la
  **Fase 7**, con fuentes online reales delante.
- **Cubo partido en dos por fuente** (API vs CDN de imágenes) — se parte si las ráfagas de páginas del
  reader ahogan las peticiones de listado. Reconsiderar en la **Fase 3/7** con números reales.
- **Bloqueo real de imports de red en el código de una fuente** — es el trust gate de código de
  terceros, **Fase 6**.
- **Ampliar el contrato** (populares / novedades / ficha de serie) — si la primera fuente online real lo
  pide, **Fase 7**, subiendo `SOURCE_API_VERSION`.

</deferred>

---

*Phase: 2-Motor de fuentes — contrato, presupuesto y taxonomía de errores*
*Context gathered: 2026-07-13*
