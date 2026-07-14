---
phase: 02-motor-de-fuentes-contrato-presupuesto-y-taxonom-a-de-errores
reviewed: 2026-07-13T00:00:00Z
depth: standard
files_reviewed: 14
files_reviewed_list:
  - apps/backend/nyanko_api/sources/__init__.py
  - apps/backend/nyanko_api/sources/contract.py
  - apps/backend/nyanko_api/sources/errors.py
  - apps/backend/nyanko_api/sources/registry.py
  - apps/backend/nyanko_api/sources/local_archive.py
  - apps/backend/nyanko_api/sources/engine.py
  - apps/backend/nyanko_api/http.py
  - apps/backend/nyanko_api/models.py
  - apps/backend/nyanko_api/main.py
  - apps/backend/tests/test_sources.py
  - apps/backend/tests/test_source_budget.py
  - apps/backend/tests/test_source_engine.py
  - apps/backend/tests/test_source_api.py
  - apps/backend/tests/test_packaged_sources.py
findings:
  critical: 4
  warning: 12
  info: 7
  total: 23
status: issues_found
---

# Fase 2: Informe de Code Review

**Revisado:** 2026-07-13
**Profundidad:** standard
**Archivos revisados:** 14
**Estado:** issues_found

## Summary

Las tres trampas nombradas del proyecto están **limpias**: `http.py` no ha regresado
(el presupuesto sigue leyéndose de `X-RateLimit-Limit` en `_observe_budget`, el
`asyncio.sleep` del ritmo ocurre **fuera** del semáforo, y los primitivos asyncio se
crean por-loop en `_state_for`, no en `__init__`). No hay ninguna URL con
`127.0.0.1`/`localhost` persistida, la caché del engine es en memoria y
`test_phase_2_does_not_add_source_persistence_columns` deja el diente puesto.

El problema no está ahí. Está en que **la única fuente real que se entrega sirve las
páginas en orden incorrecto** (CR-01), y en que las tres promesas estructurales del
motor —taxonomía de errores total, registry que aísla fuentes rotas, endpoint que no
se cae por una fuente mala— tienen agujeros demostrables (CR-02, CR-03, CR-04). El
`SourceEngine`, que es el entregable nominal de la fase, no está cableado a nada ni
exportado del paquete (WR-01).

## Critical Issues

### CR-01: `LocalArchiveSource` ordena páginas y capítulos lexicográficamente: la página 10 sale antes que la 2

**Archivo:** `apps/backend/nyanko_api/sources/local_archive.py:74-95` (y `50-66` para capítulos)

**Issue:** El `sorted(..., key=lambda path: path.name)` es un orden de cadena, no
numérico. Verificado ejecutando: `sorted(['2.jpg','10.jpg','1.jpg'])` →
`['1.jpg', '10.jpg', '2.jpg']`. Los nombres sin padding (`1.jpg`, `2.jpg`, … `10.jpg`)
son el caso **normal** en archivos de manga, no el raro.

Consecuencias, en cadena:
1. El lector muestra las páginas desordenadas.
2. `index=index` del `enumerate(page_paths, start=1)` hereda el orden roto, así que el
   `SourcePage.index` queda **mal** — no es solo un problema de presentación, el número
   de página que emite el contrato es incorrecto.
3. Lo mismo en `chapters()`: "Cap 10" se lista antes de "Cap 2".

Y el test **consagra el bug como comportamiento esperado**
(`test_sources.py:210`):
```python
assert [page.filename for page in pages] == ["1.jpg", "10.jpg", "2.jpg"]
```
Esa aserción hay que invertirla, no defenderla.

**Fix:** clave de orden natural, compartida por ambos métodos:
```python
import re

def _natural_key(name: str) -> tuple:
    # Trocea en dígitos / no-dígitos: "Cap 10" -> ('cap ', 10, '')
    return tuple(
        int(part) if part.isdigit() else part.casefold()
        for part in re.split(r"(\d+)", name)
    )
```
y usar `key=lambda path: _natural_key(path.name)` en los dos `sorted()`.
Actualizar `test_sources.py:210` a `["1.jpg", "2.jpg", "10.jpg"]`.

---

### CR-02: `_call_source` no cubre la taxonomía que la fase promete: errores httpx muy comunes escapan sin traducir

**Archivo:** `apps/backend/nyanko_api/sources/engine.py:103-111`

**Issue:** El `except` solo atrapa `HTTPStatusError`, `ConnectError`, `TimeoutException`
y `NetworkError`. Verificado contra la jerarquía real de httpx instalada:

| Excepción | ¿La atrapa `_call_source`? |
|---|---|
| `RemoteProtocolError` (servidor corta la respuesta a medias) | **NO** |
| `ProxyError` | **NO** |
| `DecodingError` (gzip/br corrupto) | **NO** |
| `TooManyRedirects` | **NO** |

`RemoteProtocolError` es de los fallos más frecuentes contra un scraper. Todos ellos
son `TransportError`/`RequestError`, no `NetworkError`.

Además, **cualquier** excepción no-httpx que lance una fuente (`ValueError`, `KeyError`,
`AttributeError`, `json.JSONDecodeError` — el pan de cada día al parsear HTML ajeno)
también escapa cruda.

El punto entero de la fase es que **todo fallo de fuente sale como `SourceError` con
una acción asociada** (`source_error_action`). Un caller que haga `except SourceError`
—que es el contrato— recibe un 500 en su lugar. La taxonomía tiene un boquete del
tamaño de la mayoría de fallos reales.

**Fix:**
```python
    async def _call_source(self, call):
        try:
            return await call()
        except SourceError:
            raise
        except httpx.HTTPStatusError as error:
            raise _source_error_from_http_status(error) from error
        except httpx.TransportError as error:
            # TransportError cubre Connect/Timeout/Network/Protocol/Proxy/Unsupported.
            raise SourceNetworkError("No se pudo conectar con la fuente") from error
        except (httpx.DecodingError, httpx.TooManyRedirects) as error:
            raise SourceParseError("Respuesta ilegible de la fuente") from error
        except Exception as error:
            # Red de seguridad: una fuente de terceros NO puede filtrar excepciones
            # crudas al caller — ese es el contrato de la taxonomía.
            raise SourceParseError(f"La fuente falló de forma inesperada: {error}") from error
```

---

### CR-03: Una sola fuente mal formada tumba el arranque completo del sidecar

**Archivo:** `apps/backend/nyanko_api/sources/registry.py:98-109`

**Issue:** El `try/except` envuelve la instanciación, pero `registry.register(source)`
está **fuera** de él (línea 108):

```python
        except Exception as error:
            ...
            registry.reject(name, display_name, f"No se pudo cargar la fuente: {error}")
            continue
        registry.register(source)     # <-- fuera del try
```

`register()` sí lanza, por dos caminos:
- `_source_attr(source, "name")` → `AttributeError("Source missing name")` si la
  instancia no expone `name` (registry.py:132).
- `raise ValueError(f"Source already registered: {name}")` si dos fuentes declaran el
  mismo `name` (registry.py:34).

Cualquiera de las dos **propaga fuera de `build_source_registry`**, y
`build_source_registry` se llama en el `lifespan` (`main.py:1408`). Resultado: el
sidecar **no arranca**. Eso es exactamente lo contrario de lo que el registry existe
para hacer ("mantener la fuente rota visible, no caerse").

Segundo agujero, dentro del propio manejador de errores: `registry.reject()` (línea 106)
**también** lanza `ValueError` si el nombre ya está registrado (registry.py:56) — una
excepción dentro del `except`, sin red debajo. Y `_source_attr(source_factory, "name",
source_factory.__name__)` (línea 104) revienta con `AttributeError` si la factory no
tiene `__name__` (un `functools.partial`, una instancia invocable).

**Fix:** meter el `register` dentro del try y hacer el rechazo idempotente:
```python
    for source_factory in sources:
        name = display_name = None
        try:
            source_fetcher = fetcher or build_source_fetcher(_source_capabilities(source_factory))
            source = _instantiate_source(source_factory, source_fetcher, library_folders)
            _inject_fetcher(source, source_fetcher)
            registry.register(source)
        except Exception as error:
            name = _factory_name(source_factory)          # tolerante a falta de __name__
            display_name = _source_attr(source_factory, "display_name", name)
            registry.force_reject(name, display_name, f"No se pudo cargar la fuente: {error}")
```
con `force_reject` = `_reject` sin el chequeo de duplicado (sobrescribe), o un
`reject(..., replace=True)`. Añadir test: una fuente sin `name` y dos fuentes con el
mismo `name` **no** deben impedir que el resto se registre.

---

### CR-04: Una fuente con `capabilities` no-dataclass devuelve 500 en todo `/api/sources`

**Archivo:** `apps/backend/nyanko_api/main.py:1503-1508`

**Issue:**
```python
    capabilities = (
        SourceCapabilitiesResponse.model_validate(asdict(registration.source.capabilities))
        if registration.source is not None
        else None
    )
```
`dataclasses.asdict()` lanza `TypeError` si el argumento no es una instancia de
dataclass. Y la guardia del registry **no impide** que llegue algo que no lo sea:
`isinstance(source, Source)` contra un `Protocol` runtime_checkable solo comprueba
**presencia** de atributos (`hasattr`), no su tipo. Una fuente con
`capabilities = {"search": True}` (un dict) o `capabilities = None` pasa el registro
como `status="ok"` y hace estallar el serializador.

Que el autor ya sabía que esto podía pasar lo prueba `registry.py:136-140`, donde
`_source_capabilities()` **sí** hace `isinstance(capabilities, SourceCapabilities)` y cae
a un default. `main.py` no replica esa defensa.

El fallo no es local a la fuente mala: `list_sources` construye la lista entera en un
solo comprehension, así que **una** fuente rota 500ea el endpoint completo — se pierde
también la lista de las fuentes buenas y de las rechazadas. Es el escenario exacto que
el `status: rejected` existía para evitar.

Peor: el mismo `asdict` + `model_validate` revienta con `ValidationError` si un valor de
`headers` no es `str` (p. ej. `{"X-Retry": 3}`), porque `SourceCapabilitiesResponse.headers`
es `dict[str, str]`.

**Fix:** reutilizar la guardia que ya existe, y aislar el fallo por fuente:
```python
from .sources.registry import _source_capabilities  # o exponerla como pública

def _source_info(registration: SourceRegistration) -> SourceInfo:
    capabilities = None
    if registration.source is not None:
        try:
            capabilities = SourceCapabilitiesResponse.model_validate(
                asdict(_source_capabilities(registration.source))
            )
        except Exception:
            # Una fuente con capabilities basura se degrada a rejected; NO tumba la lista.
            return SourceInfo(
                name=registration.name,
                display_name=registration.display_name,
                status="rejected",
                rejection_reason="Capabilities inválidas",
            )
    return SourceInfo(...)
```
Mejor aún: validar `capabilities` en `SourceRegistry.register()` (rechazar ahí si no es
`SourceCapabilities`), de modo que main.py pueda confiar en el invariante.

---

## Warnings

### WR-01: `SourceEngine` no está cableado a nada ni exportado — el entregable central de la fase es código muerto

**Archivo:** `apps/backend/nyanko_api/sources/engine.py:67`, `apps/backend/nyanko_api/sources/__init__.py:24-44`

**Issue:** `grep -rn SourceEngine` en todo `apps/backend/` solo devuelve su definición y
`tests/test_source_engine.py`. No lo usa `main.py`, no está en `sources/__init__.py`, no
está en `__all__`. `from nyanko_api.sources import SourceEngine` **falla** — hay que
alcanzarlo por `nyanko_api.sources.engine`. Lo mismo para `DefaultSourceFetcher`,
`build_source_fetcher` y `SOURCE_RATE_LIMIT_CEILING`.

`/api/sources` solo lee el registry; nada consume el engine. Igual `source_error_action`:
solo aparece en tests.

Si es andamiaje deliberado para la fase 3, vale, pero entonces dilo en el summary de la
fase. Tal como está, la superficie pública del paquete miente sobre lo que exporta.

**Fix:** exportar `SourceEngine` / `build_source_fetcher` desde `sources/__init__.py` y
`__all__`, o dejar constancia explícita de que el engine se cablea en la fase 3.

---

### WR-02: La prioridad de lectura solo funciona dentro de la ventana de 1 ms; en producción no adelanta nada

**Archivo:** `apps/backend/nyanko_api/http.py:213-224`

**Issue:** `_dispatch_waiters` **drena el heap entero** en una pasada, asignando deadline
a *todos* los waiters pendientes y avanzando `state.next_slot` por cada uno. Una lectura
prioritaria que llegue **después** de ese drenaje encuentra el heap con un solo elemento
(ella misma) y recibe `deadline = max(now, next_slot)` — es decir, se pone **detrás** de
las 100 descargas ya despachadas. El heap de prioridad solo reordena entre peticiones que
coinciden en la misma ventana de 1 ms.

O sea: `SOURCE_READ_PRIORITY` resuelve exactamente el caso que **no** ocurre (ráfaga
simultánea) y no resuelve el que sí ocurre (descargas en curso, lectura interactiva
después).

`test_read_priority_overtakes_queued_downloads` pasa porque está construido para meter
las 4 peticiones dentro de la ventana (busy-wait hasta tener 2 waiters encolados). Prueba
el caso fácil.

**Fix:** el reloj de salidas debe repartir **de uno en uno**, no drenar. `_dispatch_waiters`
debería sacar un waiter, asignarle el slot, y re-programarse para `next_slot`, de modo que
un waiter de mayor prioridad que llegue mientras tanto entre por delante en el heap. Si no
se quiere pagar eso ahora, al menos deja un `# ponytail:` con el techo real ("la prioridad
solo aplica dentro de la ventana de agrupación") y un test que lo documente.

---

### WR-03: El fallback a caché stale traga `SourceRateLimitError` y `SourceNotFoundError` — se pierde la back-pressure

**Archivo:** `apps/backend/nyanko_api/sources/engine.py:85-94`

**Issue:** `except SourceError:` es demasiado ancho. Atrapa **todo**, incluido:
- `SourceRateLimitError` → la acción de la taxonomía es `"esperar"`. Al devolver la caché
  el caller nunca se entera de que está limitado y **seguirá pegándole a la fuente**. Es
  la receta para un baneo.
- `SourceNotFoundError` → la serie ya no existe en la fuente, pero seguimos sirviendo
  capítulos cacheados indefinidamente.

El fallback tiene sentido para `SourceParseError` (Cloudflare devolvió HTML) y
`SourceNetworkError` (offline momentáneo). Para los otros dos, no.

**Fix:**
```python
        except (SourceParseError, SourceNetworkError):
            if key in self._chapters:
                return list(self._chapters[key])
            raise
```
(`SourceRateLimitError` y `SourceNotFoundError` propagan sin tocar la caché.)

---

### WR-04: `_inject_fetcher` traga el fallo en silencio y registra la fuente como `ok` sin fetcher

**Archivo:** `apps/backend/nyanko_api/sources/registry.py:143-147`

**Issue:**
```python
def _inject_fetcher(source: Source, fetcher: SourceFetcher) -> None:
    try:
        setattr(source, "fetcher", fetcher)
    except (AttributeError, TypeError):
        return
```
Si la fuente usa `__slots__` sin `fetcher`, o es frozen, el `setattr` falla, se traga la
excepción, y la fuente **se registra igualmente con `status="ok"`**. En la primera
petición de red hace `AttributeError: 'X' object has no attribute 'fetcher'` (o
`NoneType.request`), y eso ya no aparece en `/api/sources` como rechazo — sale como un
500 opaco en tiempo de uso.

**Fix:** si no se puede inyectar el fetcher, la fuente **no está lista**: rechazarla.
```python
    try:
        setattr(source, "fetcher", fetcher)
    except (AttributeError, TypeError) as error:
        raise SourceError("La fuente no admite inyección de fetcher") from error
```
(dentro del `try` de `build_source_registry`, ya cae a `reject()`.)

---

### WR-05: `isinstance(source, Source)` es prácticamente desdentado, y no hay test que lo cubra

**Archivo:** `apps/backend/nyanko_api/sources/registry.py:43-45`

**Issue:** `isinstance()` contra un `Protocol` runtime_checkable comprueba
**únicamente la presencia** de los atributos, vía `hasattr`. No comprueba firmas, no
comprueba que `search`/`chapters`/`pages` sean corrutinas, no comprueba tipos. Una clase
con `search = None` pasa. Una con `def search(self)` síncrona pasa. Una con
`capabilities = 42` pasa (y de ahí sale CR-04).

Además, `test_sources.py` no tiene **ni un solo test** para la rama
`"La fuente no cumple el contrato Source"` — solo cubre el rechazo por `api_version`
(línea 145) y por error de carga (línea 160). La rama de rechazo por contrato está sin
ejercitar.

**Fix:** validar explícitamente lo que importa, y testearlo:
```python
        for method in ("search", "chapters", "pages"):
            if not inspect.iscoroutinefunction(getattr(type(source), method, None)):
                self._reject(name, display_name, f"'{method}' no es una corrutina")
                return
        if not isinstance(getattr(source, "capabilities", None), SourceCapabilities):
            self._reject(name, display_name, "capabilities no es un SourceCapabilities")
            return
```

---

### WR-06: El registry se construye una sola vez en `lifespan` — las carpetas añadidas en caliente nunca llegan a la fuente local

**Archivo:** `apps/backend/nyanko_api/main.py:1408-1410`, `apps/backend/nyanko_api/sources/local_archive.py:97-111`

**Issue:** `build_source_registry(library_folders=database.get_library_folders())` solo
corre en el arranque. `LocalArchiveSource._load_roots` congela las raíces ahí mismo. No
hay ningún camino que reconstruya el registry cuando el usuario añade o quita una carpeta
de biblioteca (verificado: `build_source_registry` solo aparece en el import y en el
lifespan).

Consecuencia: **cualquier carpeta añadida después del arranque es invisible para la
fuente local hasta reiniciar la app.** Y `_load_roots` descarta silenciosamente
(`if path.is_dir()`) las carpetas cuya ruta no existe en ese instante — un disco externo
o una unidad de red no montada al arrancar queda huérfana permanentemente, sin ninguna
señal en `/api/sources`.

Hoy es latente (nada consume el engine todavía, WR-01), pero se vuelve un bug de usuario
en cuanto se cablee.

**Fix:** o reconstruir `app.state.source_registry` en el endpoint que muta
`library_folders`, o —más barato— que `LocalArchiveSource` lea las raíces de la BD en
cada llamada en vez de cachearlas en `__init__`. Y registrar como
`rejection_reason` / warning las carpetas descartadas por no existir en lugar de
silenciarlas.

---

### WR-07: `/api/sources` publica `capabilities.headers` verbatim, sin auth y con CORS abierto a cualquier extensión

**Archivo:** `apps/backend/nyanko_api/models.py:33-36`, `apps/backend/nyanko_api/main.py:1497-1515`

**Issue:** `SourceCapabilitiesResponse.headers: dict[str, str]` se serializa tal cual en
la respuesta. `SourceCapabilities.headers` es, por diseño, **el sitio donde una fuente
declara sus cabeceras HTTP** — que es exactamente donde acabará viviendo un
`Authorization: Bearer …` o un `X-API-Key` el día que se añada una fuente que lo
necesite.

Y el endpoint:
- No tiene ninguna dependencia de auth (`def list_sources(request: Request)`).
- Está detrás de un CORS que acepta **cualquier** origen de extensión
  (`allow_origin_regex=r"^(?:chrome|moz)-extension://[a-zA-Z0-9_-]+$"`, main.py:1446).

Es decir: cualquier extensión instalada en el navegador del usuario puede
`fetch('http://127.0.0.1:PORT/api/sources')` y leerse las cabeceras de todas las fuentes.
Hoy no hay secretos ahí (Referer, User-Agent). Mañana sí. Es una superficie que no cuesta
nada cerrar ahora y que sale caro cerrar después.

**Fix:** no serializar los valores. El consumidor necesita saber *si* la fuente manda
cabeceras, no *cuáles*:
```python
class SourceCapabilitiesResponse(BaseModel):
    search: bool
    requests_per_minute: int
    header_names: list[str] = Field(default_factory=list)   # solo las claves
```
Si algún día hace falta el valor, que sea una decisión consciente, no el default.

**Relacionado (menor):** `rejection_reason` incorpora `str(error)` crudo, que en el camino
de `LocalArchiveSource` puede contener rutas absolutas del disco del usuario. Sale por el
mismo endpoint abierto.

---

### WR-08: Los `RateLimitedClient` / `httpx.AsyncClient` por fuente nunca se cierran

**Archivo:** `apps/backend/nyanko_api/sources/engine.py:58-64`, `apps/backend/nyanko_api/main.py:1408`

**Issue:** `build_source_fetcher` crea **un `RateLimitedClient` nuevo por fuente**, cada
uno con su propio `httpx.AsyncClient` perezoso. Nadie llama a `aclose()`: ni el shutdown
del `lifespan` ni ningún otro sitio. Las conexiones y los contextos SSL quedan colgando
hasta que el GC los finaliza (con el warning de httpx correspondiente).

Con una sola fuente es ruido. Con el catálogo de fuentes que esta arquitectura pretende
soportar, y si algún día se reconstruye el registry en caliente (WR-06), es una fuga real.

**Fix:** guardar los clientes en el registry y cerrarlos en el shutdown del `lifespan`:
```python
# en lifespan, tras el yield:
for source in app.state.source_registry.all():
    fetcher = getattr(source, "fetcher", None)
    client = getattr(fetcher, "client", None)
    if client is not None:
        await client.aclose()   # añadir aclose() a RateLimitedClient
```

---

### WR-09: `_instantiate_source` despacha por posición y puede pasar los argumentos al revés

**Archivo:** `apps/backend/nyanko_api/sources/registry.py:112-126`

**Issue:**
```python
    if len(parameters) >= 2:
        return source_factory(fetcher, library_folders)
    if len(parameters) == 1:
        return source_factory(fetcher)
```
Las dos primeras ramas (por nombre de parámetro) son sólidas. Las dos últimas son
adivinación posicional:
- `__init__(self, library_folders, fetcher)` (orden invertido, sin usar los nombres que
  busca la heurística) → recibe los argumentos **cruzados**, en silencio.
- `__init__(self, *args, **kwargs)` → `len(parameters) == 2` → entra por la rama
  posicional.
- Un `functools.partial` como factory → `inspect.signature` puede no reflejar nada útil.

Para una API de plugins de terceros, "adivinamos cómo se construye tu clase" es una
fuente de bugs remotos indepurables.

**Fix:** exigir kwargs y punto. El contrato de la fuente pasa a ser explícito:
```python
def _instantiate_source(source_factory, fetcher, library_folders):
    parameters = inspect.signature(source_factory).parameters
    kwargs = {}
    if "fetcher" in parameters:
        kwargs["fetcher"] = fetcher
    if "library_folders" in parameters:
        kwargs["library_folders"] = library_folders
    return source_factory(**kwargs)
```
Una factory que no declare esos nombres se construye sin argumentos — determinista, y si
está mal, falla en el `try` y sale como `rejected`, que es lo correcto.

---

### WR-10: El `source_id` empotra el id de fila de `library_folders` — el mismo patrón que costó las carátulas

**Archivo:** `apps/backend/nyanko_api/sources/local_archive.py:136-137`

**Issue:**
```python
    def _make_id(self, root_key: str, root: Path, path: Path) -> str:
        return f"{root_key}:{path.relative_to(root).as_posix()}"
```
`root_key` viene de `folder.get("id", index)`, es decir, el **AUTOINCREMENT de
`library_folders`**. Es un handle interno y efímero: si el usuario quita una carpeta y la
vuelve a añadir, obtiene un id nuevo y todos los `source_id` anteriores apuntan a la nada.
Con `index` como fallback es peor: depende del orden de la query.

Es estructuralmente el **mismo patrón** que el incidente que dejó la biblioteca sin
carátulas (un handle efímero horneado dentro de un identificador estable).

Hoy no hay daño real porque nada persiste `source_id` (la caché de `SourceEngine` es en
memoria, y `test_phase_2_does_not_add_source_persistence_columns` lo blinda). Pero el
`source_id` es, por su nombre y su forma, **exactamente lo que alguien va a persistir en
la fase 3 o la 8**, y ese día se repite el incidente.

**Fix:** o usar la **ruta de la carpeta** como clave de raíz (estable frente a
re-inserciones), o dejar un comentario de bloqueo explícito en `_make_id`:
```python
    # ponytail: root_key es el id de fila de library_folders — EFÍMERO. Este source_id
    # NO se persiste (ver assert_no_persisted_urls / test_phase_2_...). Si alguna vez hay
    # que guardarlo, la clave de raíz pasa a ser la RUTA, no el id. Ya nos costó las
    # carátulas una vez.
```

---

### WR-11: Varios tests dependen del cwd y solo pasan si pytest se lanza desde `apps/backend/`

**Archivo:** `apps/backend/tests/test_sources.py:61,77,96,131,138`, `test_source_budget.py:170-173`, `test_source_engine.py:125`

**Issue:** `Path("nyanko_api/sources/contract.py").read_text(...)` es una ruta **relativa
al cwd**. Lanzar `pytest` desde la raíz del repo (o desde un IDE con otro working dir)
hace que estos tests fallen con `FileNotFoundError`, no con un fallo de aserción — o sea,
un fallo que parece de infraestructura y que la gente aprende a ignorar.

`test_source_api.py` sí lo hace bien (`BACKEND_DIR = Path(__file__).resolve().parents[1]`,
línea 27). La inconsistencia dentro de la misma fase es el problema.

**Fix:** usar el mismo `BACKEND_DIR` anclado a `__file__` en los cuatro archivos de test.

---

### WR-12: `SourceCapabilities` es `frozen=True` pero su `headers` es un dict mutable — la inmutabilidad es cosmética

**Archivo:** `apps/backend/nyanko_api/sources/contract.py:10-14`

**Issue:** `headers: Mapping[str, str] = field(default_factory=dict)`. El dataclass es
frozen, pero el dict que guarda no lo es: `source.capabilities.headers["X-Evil"] = "1"`
funciona perfectamente y muta la capability compartida de la clase (recordemos que
`capabilities` es un **atributo de clase** en `LocalArchiveSource`, línea 31 — la mutación
afecta a todas las instancias).

Segundo efecto: `frozen=True, eq=True` genera `__hash__`, pero `hash(SourceCapabilities())`
lanza `TypeError: unhashable type: 'dict'`. Un `set[SourceCapabilities]` o un dict con
capabilities como clave revienta.

**Fix:** congelar el mapping de verdad.
```python
from types import MappingProxyType

@dataclass(frozen=True, slots=True)
class SourceCapabilities:
    search: bool = True
    headers: Mapping[str, str] = field(default_factory=lambda: MappingProxyType({}))
    requests_per_minute: int = 60

    def __post_init__(self):
        object.__setattr__(self, "headers", MappingProxyType(dict(self.headers)))
```
(`asdict()` sigue funcionando con `MappingProxyType`; comprobar que `deepcopy` no se
queja, si lo hace, guardar `tuple[tuple[str,str], ...]` y exponer un property.)

---

## Info

### IN-01: `SOURCE_DOWNLOAD_PRIORITY` es código muerto

**Archivo:** `apps/backend/nyanko_api/sources/engine.py:25`
Definida y nunca usada (`grep` en todo `apps/backend/`). Los callers pasan `priority=0`
literal (`test_source_budget.py:112,141`). O se usa la constante, o se borra.

### IN-02: Superficie pública del paquete inconsistente

**Archivo:** `apps/backend/nyanko_api/sources/__init__.py:1-44`
`engine.py` no aporta **nada** a `__init__` ni a `__all__`: `SourceEngine`,
`DefaultSourceFetcher`, `build_source_fetcher`, `SOURCE_RATE_LIMIT_CEILING` hay que
importarlos por el submódulo. Los otros cuatro módulos sí se re-exportan. Elegir una.

### IN-03: `test_read_priority_overtakes_queued_downloads` pide un fixture y lo pisa acto seguido

**Archivo:** `apps/backend/tests/test_source_budget.py:120-128`
Recibe `real_rate_limit_sleep`, hace `real_rate_limit_sleep.clear()` (línea 121) y a
continuación vuelve a monkeypatchear `nyanko_api.http.asyncio.sleep` con su propio
`_record_sleep` (línea 128). El fixture y el `.clear()` son ruido: la lista nunca se
vuelve a leer. Quitar el parámetro del fixture.

### IN-04: El test de traversal ensucia `%TEMP%` y no limpia

**Archivo:** `apps/backend/tests/test_sources.py:216-217`
```python
outside = root.parent / "outside"
outside.mkdir(exist_ok=True)
```
`root.parent` es el directorio temporal **del sistema**, no el `TemporaryDirectory` del
test. Crea `%TEMP%/outside` y no lo borra nunca (el `exist_ok=True` delata que ya se
notó). Usar `tmp_path` de pytest, que sí se limpia.

### IN-05: `test_registry_builds_one_rate_limited_fetcher_per_source` no prueba lo que su nombre dice

**Archivo:** `apps/backend/tests/test_source_budget.py:56-61`
Construye el registry con **una sola** fuente. No hay ninguna aserción de que dos fuentes
obtengan clientes/presupuestos **distintos** — que es justo el invariante que el nombre
promete y el que hay que proteger.

### IN-06: `from . import SOURCES` diferido dentro de la función para esquivar el ciclo

**Archivo:** `apps/backend/nyanko_api/sources/registry.py:92-95`
`sources/__init__.py` importa `registry` (línea 20) **antes** de definir `SOURCES`
(línea 22), así que el import tiene que ser perezoso o revienta. Funciona, pero es una
dependencia circular latente: cualquiera que mueva el `SOURCES = [...]` o llame a
`build_source_registry()` a nivel de módulo la despierta. Mover `SOURCES` a
`registry.py` (o a un `catalog.py`) elimina el ciclo en vez de esquivarlo.

### IN-07: `LocalArchiveSource` no valida el `source_name` de los objetos de dominio que recibe

**Archivo:** `apps/backend/nyanko_api/sources/local_archive.py:45,69`
`series.source_id if isinstance(series, SourceSeries) else series` — acepta un
`SourceSeries` **de cualquier fuente** sin comprobar `series.source_name == self.name`.
Un id de otra fuente se interpreta como una ruta local. Hoy es inofensivo (el guard de
traversal lo para), pero es un cruce de identificadores que el contrato debería impedir.

---

_Reviewed: 2026-07-13_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
