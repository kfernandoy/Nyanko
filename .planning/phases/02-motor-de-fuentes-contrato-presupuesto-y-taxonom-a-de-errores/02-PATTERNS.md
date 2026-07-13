# Phase 2: Motor de fuentes — contrato, presupuesto y taxonomía de errores - Pattern Map

**Mapped:** 2026-07-13
**Files analyzed:** 13 (11 nuevos, 2 modificados)
**Analogs found:** 10 / 13
**Todas las líneas citadas están verificadas contra el árbol en `main` (HEAD).**

Nombres de módulo (`sources/contract.py`, `sources/engine.py`, ...) son **orientativos** — CONTEXT.md
D-Discretion deja los nombres al plan. Lo que no es orientativo es el **analog** de cada uno.

---

## File Classification

| Fichero nuevo/modificado | Rol | Flujo de datos | Analog más cercano | Calidad |
|---|---|---|---|---|
| `nyanko_api/sources/contract.py` (Protocol + `SourceCapabilities` + `SOURCE_API_VERSION` + `SourceSeries`/`SourceChapter`/`SourcePage`) | contract/protocol | request-response | `nyanko_api/providers.py:28-102` | exacto |
| `nyanko_api/sources/errors.py` (`SourceError` + hijos) | utility | transversal | `anilist.py:476-479`, `kitsu.py:62-63` | role-match |
| `nyanko_api/sources/registry.py` (registro + versión + rechazadas) | registry/config | batch (arranque) | `providers.py:351-373` | exacto |
| `nyanko_api/sources/__init__.py` (imports explícitos + `__all__` + `SOURCES`) | package index | batch | `nyanko_api/detectors/__init__.py:1-29` | exacto |
| `nyanko_api/sources/engine.py` (dueño del cubo por fuente + reintento + prioridad) | service | request-response (rate-limited) | `nyanko_api/http.py:92-209` | exacto (se **reutiliza**, no se reimplementa) |
| Caché en memoria de listas de capítulos (D-11) | store (in-memory) | CRUD | **sin analog** — ver § Sin analog | — |
| `nyanko_api/sources/local_archive.py` (`LocalArchiveSource`) | adapter/source | file-I/O | `providers.py:282-294` (forma) + `scanner.py:22-52` (paseo de FS) + `database.py:624-627` (carpetas) | role-match |
| `nyanko_api/models.py` (**modificado**: `SourceInfo`, `SourceCapabilitiesResponse`, estado/motivo) | model | request-response | `models.py:13-30` | exacto |
| `nyanko_api/main.py` (**modificado**: `GET /api/sources`) | route | request-response | `main.py:1468-1488` (`GET /api/providers`) | exacto |
| `tests/test_sources.py` (conformidad parametrizada, criterio 2) | test | — | `tests/test_providers.py:1-36` + `@parametrize` de `test_persisted_urls.py:369-378` | role-match |
| `tests/test_sources.py::import_guard` (D-06: la fuente no importa httpx/requests/urllib/aiohttp) | test | AST/estático | **sin analog directo** — la filosofía es la de `test_persisted_urls.py` (descubrir en runtime, cero listas a mano) | parcial |
| `tests/test_source_budget.py` (criterio 4: dos consumidores, un cubo) | test | — | `tests/test_http.py:87-115` + fixture `real_rate_limit_sleep` (`conftest.py:36-55`) | exacto |
| Test del criterio 6 (build empaquetado, lista no vacía) | test | subprocess | **sin analog** — no hay ni un test contra el onedir. Ver § Sin analog | — |

---

## Pattern Assignments

### `nyanko_api/sources/contract.py` (contract/protocol, request-response)

**Analog:** `apps/backend/nyanko_api/providers.py`

**Capacidades = frozen dataclass con defaults** (`providers.py:28-42`) — cada fuente declara lo que **no**
hace sobreescribiendo un default (D-01). Nota que `AniListProvider` (línea 108) solo nombra lo que activa:

```python
@dataclass(frozen=True, slots=True)
class ProviderCapabilities:
    library: bool = True
    search: bool = True
    details: bool = True
    batch_details: bool = False
    ...
```

**Protocol con atributos de clase + métodos async** (`providers.py:47-56`) — la forma exacta del contrato.
Los atributos (`name`, `display_name`, `capabilities`) son de **clase**, no de instancia, y las
implementaciones los declaran como tales (`providers.py:105-108`):

```python
class MediaProvider(Protocol):
    name: str
    display_name: str
    capabilities: ProviderCapabilities

    async def library(self, credential: str) -> list[MediaItem]: ...

    async def search(
        self, credential: str, query: str, limit: int = 10
    ) -> list[SearchResult]: ...
```

**Para el contrato de fuente:** mismos tres atributos + `api_version: int` + `capabilities:
SourceCapabilities` + los headers como **dato** (SRC-05 / criterio 5: un dict `headers` o
`requests_per_minute: int` en el propio `SourceCapabilities` o en un `SourceInfo` de clase — el fetcher
genérico los aplica sin saber de quién son; ver el precedente `kitsu.py:118`, `headers={"User-Agent":
_USER_AGENT}` pasado al cliente genérico).

**Tipos de dominio propios (D-03):** `providers.py:9-23` importa los modelos Pydantic desde `.models`.
La Fase 2 hace lo contrario a propósito: `SourceSeries`/`SourceChapter`/`SourcePage` viven en el módulo
del contrato o en `sources/types.py`, y **no** se importan de `models.py`. La separación es la feature.

---

### `nyanko_api/sources/errors.py` (utility, transversal)

**Analog:** la convención del árbol, `XError(RuntimeError)` por módulo. Es una convención de **base**, no
de jerarquía — la Fase 2 escribe la primera jerarquía real, deliberadamente (D-09).

`anilist.py:476-479` — el único que lleva payload (útil para `RateLimitError`, que querrá `retry_after`):

```python
class AniListError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code
```

`kitsu.py:62-63` y `myanimelist.py:54` — la forma mínima:

```python
class KitsuError(RuntimeError):
    pass
```

**Encadenar siempre con `from error`** (`kitsu.py:143`, `providers.py:366`):

```python
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise KitsuError("Invalid Kitsu credential") from error
```

**Para la Fase 2:** `class SourceError(RuntimeError)` base + hijos (red / parseo / rate-limit / no existe /
no soportado). El motor discrimina por **tipo** (`except SourceNetworkError` se reintenta,
`except SourceParseError` no) — nunca leyendo el mensaje.

---

### `nyanko_api/sources/registry.py` (registry, batch)

**Analog:** `providers.py:351-373`

**Registro completo** (`providers.py:351-369`) — `register()` revienta en duplicado, `get()` revienta en
desconocido, `all()` devuelve la lista:

```python
class ProviderRegistry:
    def __init__(self, providers: Iterable[MediaProvider] = ()):
        self._providers: dict[str, MediaProvider] = {}
        for provider in providers:
            self.register(provider)

    def register(self, provider: MediaProvider) -> None:
        if provider.name in self._providers:
            raise ValueError(f"Provider already registered: {provider.name}")
        self._providers[provider.name] = provider

    def get(self, name: str) -> MediaProvider:
        try:
            return self._providers[name]
        except KeyError as error:
            raise KeyError(f"Unknown provider: {name}") from error

    def all(self) -> list[MediaProvider]:
        return list(self._providers.values())
```

**Builder de lista explícita** (`providers.py:372-373`) — cero autodiscovery, cero `pkgutil`:

```python
def build_provider_registry(settings: Settings) -> ProviderRegistry:
    return ProviderRegistry([AniListProvider(settings), MyAnimeListProvider(settings), KitsuProvider(settings)])
```

**Diferencias obligatorias de la Fase 2 (D-13/D-14/D-15/criterio 1), donde el analog NO sirve tal cual:**

1. `register()` de fuentes **no puede lanzar** por versión incorrecta ni por reventón al cargar: tiene que
   **capturar** y guardar la fuente rechazada con su motivo. El sidecar arranca igual (criterio 1). El
   `raise ValueError` de arriba solo se conserva para el **duplicado** (bug del autor, no de la fuente).
2. `all()` devuelve las **buenas**; hace falta un segundo acceso (`rejected()` / `status()`) que devuelva
   todas con estado + motivo — es lo que consume `GET /api/sources`.
3. El registro se **reconstruye entero** (`build_source_registry()` se vuelve a llamar), sin altas/bajas
   individuales y sin reiniciar la app.
4. Al registrar, el motor crea **el `RateLimitedClient` de esa fuente** y se lo inyecta (D-05/D-06).

---

### `nyanko_api/sources/__init__.py` (package index, batch)

**Analog:** `nyanko_api/detectors/__init__.py:1-29` — el precedente anti-`pkgutil` que exige el criterio 6.
Es el **único** subpaquete del backend hoy; `sources/` sería el segundo.

```python
from .base import Detector, DetectorInfo, DetectorManager, looks_finished
from .browser import BrowserDetector
from .mpc_hc import MpcHcDetector
...

__all__ = [
    "Detector",
    "DetectorInfo",
    "DetectorManager",
    "BrowserDetector",
    ...
]
```

**Por qué basta con esto en el frozen** (`apps/backend/nyanko-api.spec:2,5`): PyInstaller congela los
módulos in-tree porque el `.spec` los recolecta. Lo que el frozen **no** tiene es un directorio que
recorrer en runtime.

```python
from PyInstaller.utils.hooks import collect_submodules
...
hiddenimports += collect_submodules('nyanko_api')
```

**Regla para la Fase 2:** la lista `SOURCES` es un `from .local_archive import LocalArchiveSource` +
`SOURCES = [LocalArchiveSource]` escrito a mano. Ni `pkgutil.iter_modules`, ni `importlib`, ni
`__subclasses__()`.

---

### `nyanko_api/sources/engine.py` (service, request-response rate-limited)

**Analog:** `apps/backend/nyanko_api/http.py` — **el cubo ya existe y no se reimplementa**. La Fase 2 solo
cambia **quién lo posee**.

**El antipatrón que la Fase 2 corrige** (`anilist.py:485`, `kitsu.py:109`, `myanimelist.py:105`): hoy cada
módulo de proveedor tiene su **singleton de módulo**, y el cliente lo agarra él mismo (`kitsu.py:111-113`):

```python
_client = RateLimitedClient(requests_per_minute=50)


class KitsuClient:
    def __init__(self):
        self.client = _client          # <- la fuente se fabrica su medio de red
```

En fuentes esto es exactamente lo prohibido (D-05/D-06): el motor crea el cliente **al registrar** y lo
**inyecta** — `LocalArchiveSource(fetcher)` / `source.bind(fetcher)`. La fuente no importa `httpx` ni ve
el módulo `http`.

**El techo y el presupuesto declarado (D-07)** — `http.py:92-116`. El `requests_per_minute` del
constructor es **valor inicial y techo**, no presupuesto; el motor lo usa para acotar el ritmo que declara
la fuente: `RateLimitedClient(requests_per_minute=min(source.requests_per_minute, GLOBAL_CEILING))`.

```python
class RateLimitedClient:
    def __init__(
        self,
        *,
        requests_per_minute: int = 90,
        max_concurrency: int = 8,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
        timeout: float = 15.0,
    ):
        self._ceiling = requests_per_minute
        self._budget = requests_per_minute
        self._interval = 60.0 / requests_per_minute if requests_per_minute > 0 else 0.0
        self._max_concurrency = max(1, max_concurrency)
```

**La lógica de acotado que D-07 replica** (`http.py:154-175`, `_observe_budget`) — el número anunciado es
una petición, no una orden. `budget = min(announced, self._ceiling)`:

```python
    def _observe_budget(self, response: httpx.Response) -> None:
        """Ajusta el ritmo al presupuesto que ACABA de anunciar el proveedor."""
        if self._ceiling <= 0:
            return
        raw = getattr(response, "headers", {}).get(RATE_LIMIT_HEADER)
        if raw is None:
            return
        try:
            announced = int(str(raw).strip())
        except ValueError:
            return  # vacía o no numérica: el presupuesto no se toca
        if announced <= 0:
            return
        # ponytail: el techo es deliberado. Un proveedor roto, comprometido o un MITM que
        # anuncie 999999 NO puede desactivar el limitador y ganarnos un baneo.
        budget = min(announced, self._ceiling)
        if budget != self._budget:
            self._budget = budget
            self._interval = 60.0 / budget
```

**El reloj de salidas — dónde encaja la prioridad de D-08** (`http.py:187-209`). El punto de inserción de
la prioridad es el `async with state.lock` (el reparto de huecos), **no** el semáforo (que es tope de
peticiones en vuelo). El sleep va **fuera** de todo y así debe seguir:

```python
    @retry_with_backoff(max_retries=3, base_delay=1.0, max_delay=30.0)
    async def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        loop = asyncio.get_running_loop()
        state = self._state_for(loop)

        if self._interval:
            async with state.lock:
                deadline = max(loop.time(), state.next_slot)
                state.next_slot = deadline + self._interval
            await asyncio.sleep(deadline - loop.time())

        async with state.semaphore:  # tope de peticiones EN VUELO, no mecanismo de ritmo
            response = await self._client_for(loop).request(method, url, **kwargs)
            self._observe_budget(response)
            response.raise_for_status()
            return response
```

**AVISO para D-08:** el reparto de huecos es FIFO por llegada al lock. Una cola de prioridad (lectura antes
que descarga) es la única modificación estructural que esta fase le hace a `RateLimitedClient`, y toca el
bloque de arriba. Cualquier cambio ahí debe dejar verdes los tests de `test_http.py` (el sleep fuera del
semáforo, deadlines distintos por petición, `_LoopState` por event loop). **No** se copia el limitador a
otro módulo: se extiende éste o se envuelve.

**El reintento del motor (D-10)** — `http.py:30-36` ya existe y **ya está aplicado** dentro de `request()`.
El motor no vuelve a reintentar la red por su cuenta; lo que sí hace es **no** reintentar nunca un
`SourceParseError` (que no es un `httpx.HTTPStatusError` y por tanto el decorador ya lo deja pasar):

```python
def retry_with_backoff(
    *,
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    retryable_statuses: frozenset[int] = frozenset({429, 502, 503, 504}),
) -> Callable[[Callable[ParamT, Awaitable[ReturnT]]], Callable[ParamT, Awaitable[ReturnT]]]:
```

**Traducción de errores httpx → `SourceError`:** el motor es quien envuelve. Los tipos que el decorador ya
distingue (`http.py:46`, `http.py:64`) son el mapa exacto: `httpx.HTTPStatusError` con 429 →
`SourceRateLimitError`; `httpx.ConnectError`/`TimeoutException`/`NetworkError` → `SourceNetworkError`; 404
→ `SourceNotFoundError`.

---

### Caché en memoria de listas de capítulos (D-11) — **sin analog**

No existe ninguna caché en memoria en el árbol. Lo único parecido:
- `config.py:130` — `@lru_cache` sobre `get_settings()`. No sirve: `lru_cache` **cachea la excepción no**,
  pero tampoco distingue «resultado válido» de «error» a la hora de escribir, y no se puede invalidar por
  clave con la regla dura.
- `database.py:930/975/1051` — `get_cache` / `set_cache` / `invalidate_cache`, pero es **SQLite**, y D-11
  difiere la persistencia a la Fase 8.

**Lo que hay que escribir es un `dict[tuple[str, str], list[SourceChapter]]` y la regla dura:**

```python
# ponytail: dict a secas, sin TTL ni LRU. La caché muere con el proceso (D-11: persistir es Fase 8).
# LA REGLA: solo escribe un resultado VÁLIDO. Un error nunca borra ni pisa lo que había.
async def chapters(self, source_name: str, series_id: str) -> list[SourceChapter]:
    key = (source_name, series_id)
    try:
        fresh = await self._registry.get(source_name).chapters(series_id)
    except SourceError:
        if key in self._chapters:
            return self._chapters[key]   # la lista buena sobrevive al fallo
        raise
    self._chapters[key] = fresh          # única escritura, y solo en el camino feliz
    return fresh
```

El criterio 3 (Cloudflare responde **HTTP 200 con HTML**) llega aquí como `SourceParseError` lanzado por la
fuente — nunca como `[]`. Ese es el motivo entero de que 0 resultados **lance**.

---

### `nyanko_api/sources/local_archive.py` (adapter/source, file-I/O)

**Analog de forma:** `providers.py:282-294` — un proveedor concreto: atributos de clase, capacidades
declarando lo que **no** hace, `__init__` que recibe su dependencia:

```python
class KitsuProvider:
    name = "kitsu"
    display_name = "Kitsu"
    capabilities = ProviderCapabilities(
        search=True,
        details=True,
        mutations=True,
        preferences=True,
        preferences_editable=True,
    )

    def __init__(self, settings: Settings):
        self.client = KitsuClient()
```

Para `LocalArchiveSource`: `capabilities = SourceCapabilities(search=False)` (D-01: no busca online) y
`__init__(self, fetcher, folders)` — el fetcher entra inyectado aunque no lo use (D-06).

**Analog de paseo de sistema de ficheros:** `scanner.py:10-12` y `scanner.py:22-52`. Extensiones como
`frozenset`, folder = `{"path": str, "recursive": bool}`, y **carpeta ilegible se salta en silencio** (un
disco desconectado no aborta el escaneo):

```python
VIDEO_EXTENSIONS = frozenset(
    ".mkv .mp4 .avi .webm .mov .ts .m2ts .wmv .flv .ogm .mpg .mpeg".split()
)


def iter_video_files(folders: list[dict]) -> Iterator[str]:
    seen: set[str] = set()
    for folder in folders:
        root = folder.get("path")
        if not root or not os.path.isdir(root):
            continue
        recursive = bool(folder.get("recursive", True))
        if recursive:
            for dirpath, _dirs, files in os.walk(root):
                ...
        else:
            try:
                entries = os.scandir(root)
            except OSError:
                continue
```

**De dónde salen las carpetas (no se inventa configuración):** `database.py:624-627`, ya en uso desde
`main.py:1348`:

```python
    def get_library_folders(self) -> list[dict]:
        ...
                "SELECT id, path, recursive FROM library_folders ORDER BY path"
```

**D-04 (id opaco, nunca URL) sobre file-I/O:** el id de una serie/capítulo local **no puede ser la ruta
absoluta** si la ruta se persiste — la guardia FND-05 exime `local_files.path` y `library_folders.path`,
pero `test_persisted_urls.py:445-459` prohíbe exentar **cualquier** columna nueva acabada en `path` o
`_local`. El id opaco (p. ej. hash o `carpeta/capítulo` relativo al root) es lo que evita el choque.
`IMAGE_EXTENSIONS` (jpg/png/webp/gif/avif) es el gemelo de `VIDEO_EXTENSIONS`; sin orden natural, sin CBZ,
sin ComicInfo (D-02).

---

### `nyanko_api/models.py` (**modificado**) — `SourceInfo` / `SourceCapabilitiesResponse`

**Analog:** `models.py:13-30` — el espejo Pydantic del dataclass frozen, ya en uso:

```python
class ProviderCapabilitiesResponse(BaseModel):
    library: bool
    search: bool
    details: bool
    mutations: bool
    ...
    preferences: bool = False
    preferences_editable: bool = False


class ProviderInfo(BaseModel):
    name: str
    display_name: str
    authenticated: bool
    capabilities: ProviderCapabilitiesResponse
```

Para D-14 `SourceInfo` añade `status: Literal["ok", "rejected"]` y `rejection_reason: str | None`.

---

### `nyanko_api/main.py` (**modificado**) — `GET /api/sources`

**Analog:** `main.py:1461-1488`. El backend es **plano**: `@app.get(...)` directamente sobre `app`, sin
`APIRouter` ni `include_router` en ninguna parte del árbol. `Depends(get_settings)` /
`Depends(get_database)` para las dependencias, y `asdict()` para pasar del dataclass frozen al modelo
Pydantic:

```python
@app.get("/api/providers", response_model=list[ProviderInfo])
def providers(
    settings: Settings = Depends(get_settings), database: Database = Depends(get_database)
) -> list[ProviderInfo]:
    registry = build_provider_registry(settings)
    stored_accounts = database.get_accounts()
    return [
        ProviderInfo(
            name=provider.name,
            display_name=provider.display_name,
            authenticated=...,
            capabilities=ProviderCapabilitiesResponse.model_validate(
                asdict(provider.capabilities)
            ),
        )
        for provider in registry.all()
    ]
```

**Ojo:** `build_provider_registry(settings)` se llama **dentro del endpoint** (y también en `main.py:930`),
es decir, se reconstruye en cada petición. Para fuentes eso es lo que **no** se quiere (el registro posee
los cubos de rate limit: reconstruirlo por petición tiraría el presupuesto acumulado). El registro de
fuentes se construye **una vez al arrancar** (lifespan / estado de app) y se **reconstruye entero** solo
cuando la Fase 6 instale una fuente (D-15). El endpoint **lee** ese registro; itera sobre buenas +
rechazadas (D-14).

---

### `tests/test_sources.py` (conformidad parametrizada, criterio 2)

**Analog:** `tests/test_providers.py:1-36` — stub mínimo + aserciones del registro:

```python
class StubProvider:
    name = "stub"
    display_name = "Stub"
    capabilities = None

    async def library(self, credential: str) -> list[MediaItem]:
        return []


def test_provider_registry_rejects_duplicates():
    provider = StubProvider()

    with pytest.raises(ValueError, match="already registered"):
        ProviderRegistry([provider, provider])
```

**Parametrización** (`test_persisted_urls.py:369-378`, `test_http.py:88`):

```python
@pytest.mark.parametrize(
    "poisoned",
    [
        "http://127.0.0.1:8765/assets/anilist/99/cover.jpg",
        ...
    ],
)
def test_loopback_url_fails_even_in_an_allowlisted_column(tmp_path, poisoned):
```

**Para el criterio 2:** `@pytest.mark.parametrize("source", SOURCES, ids=lambda s: s.name)` — la lista
`SOURCES` real, no una fabricada en el test. Y una fuente que no cumple el Protocol tiene que **romper** el
test: `isinstance(source, SourceProtocol)` requiere `@runtime_checkable` en el Protocol, pero eso solo
comprueba **presencia** de métodos, no firmas. El gate de firmas es `inspect.signature` contra el Protocol,
o dejarlo en manos de mypy — el plan decide.

---

### Guardia de imports de D-06 (test) — **sin analog directo**

Ningún test del árbol inspecciona AST. Lo más cercano en **filosofía** es `test_persisted_urls.py:92-110`
(`_columns`), que descubre el esquema en runtime y no mantiene ninguna lista a mano — el comentario que
explica por qué es exactamente el argumento que aplica aquí:

```python
    """El esquema, descubierto EN RUNTIME: (tabla, columna) de toda la BD.

    Cero listas escritas a mano: por construcción, esto cubre las columnas del esquema v8 y
    las que llegue a añadir cualquier fase futura. La guardia que hay que actualizar a mano
    es la guardia que un día no se actualiza.
    """
```

**Traducción:** la guardia recorre el módulo de **cada fuente registrada** (`inspect.getsourcefile(type(
source))` → `ast.parse`), no una lista de módulos escrita a mano. `ast.Import`/`ast.ImportFrom` contra
`{"httpx", "requests", "urllib", "aiohttp"}`. `ast` es stdlib; un grep sobre el fuente también valdría y es
más corto, pero acierta el nombre dentro de un comentario o un string.

---

### `tests/test_source_budget.py` (criterio 4: dos consumidores, un cubo)

**Analog:** `tests/test_http.py:87-115` — la forma exacta del test de ritmo agregado. **No mide a reloj de
pared**: graba lo que el limitador *pide* dormir. Determinista e instantáneo.

```python
@pytest.mark.asyncio
@pytest.mark.parametrize("budget", [120, 45, 12])
async def test_pacing_follows_provider_header(monkeypatch, real_rate_limit_sleep, budget):
    client = RateLimitedClient(requests_per_minute=200, max_concurrency=50)
    _install_fake_provider(monkeypatch, headers={RATE_LIMIT_HEADER: str(budget)})

    await client.get("https://example.test/warmup")
    assert client.budget == budget
    client._loop_state[asyncio.get_running_loop()].next_slot = 0.0
    real_rate_limit_sleep.clear()

    requests = 5
    await asyncio.gather(
        *(client.get(f"https://example.test/{i}") for i in range(requests))
    )

    interval = 60.0 / budget
    # Calendario ACUMULATIVO, no "cada sleep vale el intervalo": esa segunda forma sería
    # verde para el bug (N corrutinas durmiendo lo mismo y saliendo todas en el mismo tick).
    assert real_rate_limit_sleep == pytest.approx(
        [i * interval for i in range(requests)], abs=0.01
    )
```

**El fixture obligatorio** (`conftest.py:36-55`, `real_rate_limit_sleep`): hay un **autouse** que anula
`asyncio.sleep` (`conftest.py:30-34`, `_fast_rate_limit_sleep`). Un test de ritmo que no pida
`real_rate_limit_sleep` es **verde y vacío**: el limitador nunca duerme y no hay nada que medir.

```python
@pytest.fixture
def real_rate_limit_sleep(monkeypatch):
    """Anula el noop autouse de _fast_rate_limit_sleep con un GRABADOR."""
    recorded: list[float] = []

    async def _record_sleep(delay: float = 0.0, *args, **kwargs):
        recorded.append(delay)
        return None

    monkeypatch.setattr("nyanko_api.http.asyncio.sleep", _record_sleep)
    return recorded
```

**Lo que el criterio 4 añade:** los dos consumidores (prefetch simulado + cola simulada) piden a **la misma
fuente** a la vez, y el calendario agregado es UNA progresión acumulativa `[0, i, 2i, ...]`. Si cada
consumidor tuviera su cubo, saldrían **dos** progresiones intercaladas (cada duración repetida dos veces).
`assert len(set(recorded)) == len(recorded)` es la aserción que distingue un cubo de dos —el mismo truco
que `test_http.py:132-133`.

---

### Test del criterio 6 (build empaquetado) — **sin analog**

No existe ni un test que ejecute el onedir de PyInstaller. El plan tiene que decidir el mecanismo
(subprocess contra `nyanko-api.exe` + `GET /api/sources` y afirmar lista no vacía, o un script de CI). El
material disponible: `apps/backend/nyanko-api.spec` (líneas 2 y 5) y el precedente `detectors/__init__.py`.

---

## Shared Patterns

### 1. Presupuesto: el cubo se reutiliza, no se reescribe
**Fuente:** `apps/backend/nyanko_api/http.py:92-221`
**Aplica a:** motor, todas las fuentes, tests de presupuesto.
Regla: la Fase 1 arregló **tres** bugs en este fichero (el número horneado, el semáforo retenido durante el
sleep, el singleton compartido entre loops). Cualquier código de la Fase 2 que instancie su propio
limitador, o que copie la lógica de ritmo a `sources/`, los rearma. Lo que la Fase 2 cambia es **el dueño**
(módulo → motor, uno por fuente) y, si D-08 lo exige, **el orden del reparto de huecos** dentro de
`request()`.

### 2. Headers como dato
**Fuente:** `kitsu.py:34` (`_USER_AGENT`), `kitsu.py:118`, `kitsu.py:145`
**Aplica a:** contrato de fuente (SRC-05, criterio 5).
El cliente genérico ya acepta `headers=` y no sabe de quién son:
```python
        response = await self.client.get(f"{API_URL}/users?filter[self]=true", headers=headers)
```
La fuente los declara (`headers = {"Referer": ..., "User-Agent": ...}` como atributo de clase); el fetcher
del motor los mete en cada `request()`. Cero `if source.name == "x"` en el fetcher.

### 3. Errores: `RuntimeError` de base, `from error` siempre
**Fuente:** `anilist.py:476`, `kitsu.py:62`, `myanimelist.py:54`
**Aplica a:** `sources/errors.py` y a todo `except` del motor.

### 4. Guardia FND-05 tras cualquier escritura nueva
**Fuente:** `apps/backend/tests/test_persisted_urls.py:156` (`assert_no_persisted_urls`)
**Aplica a:** cualquier test de la Fase 2 que persista algo.
```python
from tests.test_persisted_urls import assert_no_persisted_urls
assert_no_persisted_urls(connection)   # después de tus escrituras, no antes
```
El docstring del módulo (líneas 21-33) nombra explícitamente a las Fases 3/7/8. La Fase 2 persiste
`(source_name, source_id)` (D-04) y no debería tener ninguna columna nueva que empiece por `http` — llamar
a la guardia es lo que lo **demuestra** en vez de suponerlo. Y ojo con `test_persisted_urls.py:445-459`:
ninguna columna acabada en `path` o `_local` puede entrar en la lista blanca. Nunca.

### 5. Autodiscovery = prohibido
**Fuente:** `nyanko_api/detectors/__init__.py:1-29`, `nyanko-api.spec:2,5`
**Aplica a:** `sources/__init__.py`, registro, cualquier tentación de `pkgutil`.

### 6. Backend plano, FastAPI sin routers
**Fuente:** `main.py` (4.405 líneas, `@app.get` directo; **cero** `APIRouter`/`include_router` en el árbol)
**Aplica a:** el endpoint de D-14. Sigue la convención aunque duela: un `APIRouter` nuevo sería el primero
del proyecto y es fuera de alcance.

### 7. Comentarios `ponytail:` para simplificaciones deliberadas
**Fuente:** `http.py:110`, `http.py:169`
**Aplica a:** la caché en memoria (sin TTL/LRU), el techo global, `max_concurrency` por fuente. El
comentario nombra el **techo conocido** y el camino de subida.

---

## Sin analog

| Fichero | Rol | Flujo | Motivo |
|---|---|---|---|
| Caché en memoria de capítulos (D-11) | store | CRUD | No hay ninguna caché en memoria en el árbol. `config.py:130` usa `@lru_cache` (no vale: no distingue válido de error al escribir) y `database.py:930-1051` es SQLite (diferido a Fase 8). Se escribe un `dict` + la regla dura. |
| Guardia de imports D-06 | test | AST | Ningún test inspecciona AST. Se hereda la **filosofía** de `test_persisted_urls.py` (descubrir en runtime, cero listas a mano), no su código. |
| Test del criterio 6 (onedir) | test | subprocess | Ningún test corre contra el build empaquetado. Mecanismo a decidir en el plan. |

---

## Metadata

**Ámbito de búsqueda:** `apps/backend/nyanko_api/` (20 módulos + `detectors/`), `apps/backend/tests/`
(20 tests + `conftest.py` + `fixtures/`), `apps/backend/nyanko-api.spec`.
**Ficheros leídos íntegros:** `providers.py`, `http.py`, `detectors/__init__.py`, `scanner.py`,
`test_persisted_urls.py`, `test_http.py`.
**Ficheros leídos por rango:** `main.py` (1455-1504), `anilist.py` (470-500), `kitsu.py` (55-150),
`models.py` (13-30), `config.py` (1-60), `conftest.py` (1-70), `test_providers.py` (1-50).
**Fecha de extracción:** 2026-07-13
