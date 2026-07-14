# Phase 3: Page pipe + lectura local — la piedra angular - Pattern Map

**Mapped:** 2026-07-14
**Files analyzed:** 16 (5 nuevos, 11 modificados)
**Analogs found:** 13 / 16
**Research:** none (research_enabled: false — «todo tiene precedente en el árbol»). Confirmado: hay
precedente para todo excepto tres cosas, listadas en § No Analog Found.

---

## Hallazgos que cambian el plan (leer antes que nada)

Tres cosas descubiertas leyendo el árbol que contradicen o completan el CONTEXT. Las tres son
baratas si el plan las conoce, y caras si las descubre el ejecutor.

### H-1 — Un test de la Fase 2 PROHÍBE `APIRouter` en `main.py`

`apps/backend/tests/test_source_api.py:155-162`:

```python
def test_sources_endpoint_is_flat_and_handler_does_not_build_registry():
    main_source = (BACKEND_DIR / "nyanko_api" / "main.py").read_text(encoding="utf-8")
    assert "@app.get(\"/api/sources\"" in main_source
    assert "APIRouter" not in main_source      # ← esto
    assert "include_router" not in main_source  # ← y esto
```

`ARCHITECTURE.md` preveía un módulo `manga.py` con su router. **Ese camino está cerrado por un test
verde.** Y da igual: el patrón del árbol es `@app.get` plano sobre `app` (58 rutas así en
`main.py`). El page pipe sigue esa forma o rompe la suite.

**Consecuencia sobre D-04 (que es el punto entero de la fase):** `app` nace en `main.py:1440` y el
mount `/assets` está en `main.py:1442`. Starlette casa rutas **en orden de la lista**, y un `Mount`
devuelve `Match.FULL` para cualquier path bajo su prefijo. Sin `include_router`, solo queda una
forma de que la ruta dinámica gane al mount: **declarar el handler entre la línea 1440 y la 1442**.

```python
app = FastAPI(title="Nyanko API", version="0.1.0", lifespan=lifespan)   # main.py:1440
settings = get_settings()                                               # main.py:1441

# ── LA RUTA DINÁMICA VA AQUÍ, ANTES DEL MOUNT (D-04) ──
@app.get("/assets/pages/{page_id:path}")
async def read_page(...): ...

app.mount("/assets", StaticFiles(directory=settings.assets_dir, check_dir=False), name="assets")
```

La alternativa (mover el `app.mount` al final del fichero) también funciona pero deja la trampa a
1.400 líneas de distancia del sitio donde muerde. El test de regresión que pide D-04 se escribe
sobre `app.router.routes`: el índice de la ruta `/assets/pages/...` tiene que ser **menor** que el
del `Mount` de `/assets`.

### H-2 — El esquema v9 rompe un test de la Fase 2 A PROPÓSITO

`apps/backend/tests/test_source_api.py:165-184`, `test_phase_2_does_not_add_source_persistence_columns`:

```python
    names = {column for _table, column in columns}
    assert "source_name" not in names
    assert "source_id" not in names
    ...
    assert "source_name" not in database_module.SCHEMA
```

D-10 y D-13 añaden `reader_prefs(source_name, series_id)`, `reader_progress(source_name, chapter_id)`
y `reading_events(source_name, ...)`. **Ese test se pone rojo por construcción el día que se escribe
la migración v9.** No es un bug del plan: el test se llama literalmente `test_phase_2_...` y existía
para afirmar que la Fase 2 no persistía nada. **La Fase 3 es la fase que lo retira** (o lo reescribe
como «las columnas de identidad de fuente son `source_name`/`source_id`, y ninguna lleva `url`,
`path` ni `_local`» — que es la mitad que sigue teniendo sentido, líneas 180-184). Un plan que no
lo toque deja la suite roja y el ejecutor decidiendo solo qué borrar.

### H-3 — La CSP literal del ROADMAP deja la app sin portadas

El criterio 7 del ROADMAP y el CONTEXT dicen `img-src 'self' http://127.0.0.1:* blob: data:`.
Aplicado tal cual, **borra todas las portadas de Descubrir, Temporadas, Búsqueda y el avatar de la
cuenta**: esas imágenes son URLs del CDN del proveedor que llegan crudas al renderer
(`anilist.py:613,652,679` → `cover_image=item["coverImage"]["large"]`, renderizadas en
`DiscoveryView.tsx:281`, `App.tsx:1185,1614,1927,2100,2205`). Solo las de la card de detalle pasan
por `_localize_media_details_assets` y se vuelven `/assets/...`.

La CSP que hay que escribir necesita, como mínimo:

| Directiva | Por qué |
|-----------|---------|
| `img-src 'self' http://127.0.0.1:* https: blob: data:` | `https:` → portadas del CDN. `data:` → el favicon de `index.html:6`. `http://127.0.0.1:*` → las páginas del reader y los assets locales. |
| `connect-src 'self' http://127.0.0.1:* ws://127.0.0.1:*` | **Sin `ws:` muere `playbackSocket()` (`api.ts:489-492`)**, y sin `http://127.0.0.1:*` muere la API entera. |
| `style-src 'self' 'unsafe-inline'` | Todo el árbol usa `style={{...}}` (atributo inline). |
| dev | El renderer vive en `http://localhost:5173` con HMR por WebSocket: la CSP de dev necesita ese origen o se rompe el desarrollo. |

**Y el vehículo no puede ser `onHeadersReceived`:** en prod la ventana carga por `file://`
(`index.ts:83`, `win.loadFile(...)`) y el splash por `data:text/html` (`splash.ts:71`). Ninguno de
los dos es una respuesta HTTP. La CSP tiene que ser un `<meta http-equiv="Content-Security-Policy">`
en `apps/desktop/index.html` y en el `<head>` de `SPLASH_HTML`. Por eso `index.ts` **no es** el
fichero donde aterriza (el CONTEXT lo nombra, pero ahí no hay dónde ponerla).

**Trampa del splash:** `splash.ts:47-49` usa manejadores `onclick=` **inline**. Cualquier
`script-src` sin `'unsafe-inline'` (o sin hash) deja los botones Reintentar / Abrir logs / Salir
muertos — y el splash es justo la pantalla que aparece cuando algo ya ha fallado.

---

## File Classification

| Fichero (nuevo/modificado) | Rol | Data flow | Analog más cercano | Match |
|---|---|---|---|---|
| `apps/backend/nyanko_api/sources/local_archive.py` (M) | source adapter | file-I/O | él mismo (carpetas) + `scanner.py` | exact |
| `apps/backend/nyanko_api/main.py` (M) — ruta `/assets/pages/{page_id}` | controller | streaming | `main.py:1442` (mount) + `main.py:2394` (`Response`) | partial |
| `apps/backend/nyanko_api/main.py` (M) — endpoints `/api/manga/*` | controller | request-response / CRUD | `main.py:1497` (`list_sources`), `main.py:1901-1940` (folders CRUD) | exact |
| `apps/backend/nyanko_api/database.py` (M) — schema v9 | model / migration | CRUD | `database.py:275-355` (ladder) + `playback_events` | exact |
| `apps/backend/nyanko_api/database.py` (M) — `insert_reading_event` etc. | model | CRUD | `database.py:2307-2445` (`playback_events` CRUD) | exact |
| `apps/backend/nyanko_api/models.py` (M) | model (pydantic) | request-response | `models.py:33-45` (`SourceInfo`) | exact |
| `apps/backend/nyanko_api/sources/contract.py` (M?) | contract | — | — | **decisión abierta, ver § No Analog** |
| `apps/backend/nyanko_api/sources/__init__.py` (M) | config | — | `sources/__init__.py` (lista `SOURCES` + `__all__`) | exact |
| `apps/desktop/src/ReaderView.tsx` (N) | view | event-driven (teclado/rueda) | `LocalLibraryView.tsx` (forma) + `ContextMenu.tsx:96-114` (teclado) | role-match |
| `apps/desktop/src/App.tsx` (M) | view router | — | `App.tsx:46,180-184,1262-1263` | exact |
| `apps/desktop/src/api.ts` (M) | service (cliente HTTP) | request-response | `api.ts:275-487` (objeto `api`) | exact |
| `apps/desktop/src/types.ts` (M) | model | — | `types.ts` (`LocalSeries`) | exact |
| `apps/desktop/src/i18n.tsx` (M) | config | — | `i18n.tsx` (claves `local.*`) | exact |
| `apps/desktop/src/styles.css` (M) | style | — | `styles.css` (`.local-library`…) | exact |
| `apps/desktop/index.html` (M) | config | — | — | **no analog (no hay CSP en el árbol)** |
| `apps/desktop/electron/main/splash.ts` (M) | config | — | — | **no analog** |
| `apps/backend/tests/test_sources.py` (M) | test | file-I/O | `test_sources.py:219-271` | exact |
| `apps/backend/tests/test_manga_pages.py` (N) | test | streaming | `test_source_api.py:61-120` (`_installed_registry` + TestClient) | exact |
| `apps/backend/tests/test_source_api.py` (M) | test | — | ver H-2: hay que retirar `test_phase_2_...` | — |

---

## Pattern Assignments

### `sources/local_archive.py` — CBZ/ZIP + ComicInfo (source adapter, file-I/O)

**Analog:** él mismo. La fuente ya tiene las tres piezas que la fase necesita; solo le falta el
`zipfile`. **Copiar la forma, no reinventarla.**

**Contención de rutas — el patrón que la ruta de páginas DEBE reutilizar** (`local_archive.py:123-147`):

```python
    def _resolve_id(self, source_id: str) -> tuple[str, Path, Path]:
        root_key, relative = self._split_id(source_id)
        try:
            root = self._roots[root_key]
        except KeyError as error:
            raise SourceNotFoundError("Raiz local no registrada") from error

        candidate = (root / (relative or ".")).resolve()
        try:
            candidate.relative_to(root)      # ← D-05 vive aquí y en ningún otro sitio
        except ValueError as error:
            raise SourceNotFoundError("Identificador local fuera de la biblioteca") from error
        return root_key, root, candidate

    def _make_id(self, root_key: str, root: Path, path: Path) -> str:
        return f"{root_key}:{path.relative_to(root).as_posix()}"   # id OPACO: "0:Serie/Cap 1/002.jpg"
```

El id que sale de `_make_id` es `{root_key}:{ruta relativa}` — **nunca** una ruta del sistema, nunca
absoluta. El test que lo afirma ya existe (`test_sources.py:228-229`).

**Orden natural — ya pagado** (`local_archive.py:21-28`):

```python
_DIGITS = re.compile(r"(\d+)")

def _natural_key(name: str) -> tuple[object, ...]:
    """Ordena '2.jpg' antes que '10.jpg': el orden de cadena rompe la paginacion."""
    return tuple(int(part) if part.isdigit() else part.lower() for part in _DIGITS.split(name))
```

El CBZ ordena sus miembros con **esta misma función** sobre `ZipFile.namelist()`. No se escribe una
segunda.

**Listado de páginas — la forma que el CBZ tiene que producir igual** (`local_archive.py:78-105`):

```python
    async def pages(self, chapter: SourceChapter | str) -> list[SourcePage]:
        chapter_id = chapter.source_id if isinstance(chapter, SourceChapter) else chapter
        root_key, root, chapter_path = self._resolve_id(chapter_id)
        if not chapter_path.is_dir():
            raise SourceNotFoundError("Capitulo local no encontrado")
        try:
            page_paths = sorted(
                (p for p in chapter_path.iterdir()
                 if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS),
                key=lambda path: _natural_key(path.name),
            )
        except OSError as error:
            raise SourceParseError("No se pudo listar el capitulo local") from error
        if not page_paths:
            raise SourceParseError("El capitulo local no tiene paginas")   # SRC-07: 0 páginas LANZA
        return [
            SourcePage(source_id=self._make_id(root_key, root, path), chapter_id=..., index=index,
                       filename=path.name, source_name=self.name)
            for index, path in enumerate(page_paths, start=1)
        ]
```

Lo que cambia para el CBZ: `chapter_path.is_dir()` pasa a ser «es dir **o** es fichero con sufijo
`.cbz`/`.zip`», y el listado sale de `zipfile.ZipFile(chapter_path).namelist()` filtrado por
`IMAGE_EXTENSIONS` (que ya existe, línea 19) y ordenado por `_natural_key`. El `source_id` de una
página dentro de un ZIP necesita un separador propio para el miembro (p. ej. `0:Serie/Cap1.cbz!002.jpg`),
porque `_resolve_id` resuelve hasta el **fichero** y el miembro va aparte — y así el mismo id sirve
para las dos formas, que es D-01.

**Errores tipados — la taxonomía ya está** (`sources/errors.py:8-31`): `SourceNotFoundError` (no
existe), `SourceParseError` (existe pero no se puede interpretar / 0 resultados),
`SourceUnsupportedError` (**el CBR/RAR: «conviértelo a CBZ»**, no se intenta leer).

**Test analog** (`test_sources.py:233-245`) — el CBZ copia esta forma exacta, con un `zipfile.ZipFile`
escrito en el `tmp_path` en vez de ficheros sueltos:

```python
@pytest.mark.asyncio
async def test_local_archive_lists_only_images_in_natural_order():
    with _workdir("pages") as root:
        chapter_dir = root / "Cap 1"; chapter_dir.mkdir()
        for name in ["2.jpg", "10.jpg", "1.jpg", "ComicInfo.xml", "extra.cbz", "nota.txt"]:
            (chapter_dir / name).write_text("x", encoding="utf-8")
        source = LocalArchiveSource(_Fetcher(), [{"id": "0", "path": str(root)}])
        pages = await source.pages("0:Cap 1")
        assert [page.filename for page in pages] == ["1.jpg", "2.jpg", "10.jpg"]
        assert [page.index for page in pages] == [1, 2, 3]
```

Y el de traversal, que la ruta nueva tiene que replicar **a nivel HTTP** (`test_sources.py:259-270`).

---

### `main.py` — la ruta de páginas (controller, streaming)

**Analog:** ninguno exacto (no hay un solo `FileResponse`/`StreamingResponse` en el árbol). Lo que sí
hay es el contrato de URL relativa, y es lo que hace legal a D-01.

**El patrón de URL — copiarlo literal** (`main.py:316-326`):

```python
def _asset_url(settings: Settings, provider: str, external_id: int | str, filename: str) -> str:
    # RELATIVA a propósito, y esto es el arreglo de D-I-02: estas URLs se PERSISTEN en
    # media_details_cache. Si llevan el host:puerto dentro, el día que el sidecar arranca en
    # otro puerto (basta que algo ocupe el 8765) la biblioteca se queda sin una sola portada,
    # de forma permanente y silenciosa. El renderer la compone contra la base de API que ya
    # resuelve en vivo (`normalizeAssetUrls` en api.ts), así que una ruta relativa no caduca.
    return f"/assets/{provider}/{external_id}/{filename}"
```

La URL de página es **exactamente igual de relativa**: `/assets/pages/{page_id}`. Un `_page_url()`
gemelo de este, con este comentario, y FND-05 se cumple por construcción.

**Por qué funciona (D-03)** — `api.ts:202-215`:

```typescript
function normalizeAssetUrls<T>(value: T, apiUrl: string): T {
  if (typeof value === "string") {
    return (value.startsWith("/assets/") ? `${apiUrl}${value}` : value) as T;
  }
  if (Array.isArray(value)) return value.map((item) => normalizeAssetUrls(item, apiUrl)) as T;
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, normalizeAssetUrls(v, apiUrl)])) as T;
  }
  return value;
}
```

Reescribe **cualquier** string que empiece por `/assets/` (con barra final — `"/assets/pages/…"`
casa), venga del mount o no, y se aplica a toda respuesta JSON (`api.ts:249`, `api.ts:257`). Cero
cambios en `api.ts` para que las páginas se resuelvan solas.

**El orden de registro (D-04, H-1)** — `main.py:1440-1442`:

```python
app = FastAPI(title="Nyanko API", version="0.1.0", lifespan=lifespan)
settings = get_settings()
app.mount("/assets", StaticFiles(directory=settings.assets_dir, check_dir=False), name="assets")
```

**El handler va entre la 1441 y la 1442.** Ver H-1.

**El registry vivo, no reconstruido** (`main.py:1497-1500`) — el patrón que el handler de páginas copia:

```python
@app.get("/api/sources", response_model=list[SourceInfo])
def list_sources(request: Request) -> list[SourceInfo]:
    registry: SourceRegistry = request.app.state.source_registry
    return [_source_info(registration) for registration in registry.registrations()]
```

Se lee de `request.app.state.source_registry` (lo siembra `lifespan`, `main.py:1408`). **Nunca** se
llama a `build_source_registry()` dentro de un handler — hay un test que lo prohíbe
(`test_source_api.py:105-120`). Consecuencia conocida y aceptada: **WR-06** — una carpeta añadida en
caliente es invisible hasta reiniciar. Esta fase la cablea, así que esta fase la paga (o la declara).

**Mapeo error → HTTP** — el analog es `raise_provider_http_error` (`main.py:1001-1038`), que es
exactamente esta forma:

```python
def raise_provider_http_error(error: Exception, provider: str) -> None:
    if isinstance(error, httpx.HTTPStatusError):
        status = error.response.status_code
        if status in {401, 403}: raise HTTPException(status_code=401, detail=...) from error
        if status == 429:        raise HTTPException(status_code=429, detail=...) from error
        raise HTTPException(status_code=502, detail=...) from error
    ...
    logger.exception("Unexpected %s provider error", display_name)
    raise HTTPException(status_code=502, detail=...) from error
```

El gemelo para fuentes (`SourceNotFoundError` → 404, `SourceUnsupportedError` → 415/422,
`SourceParseError` → 502, `SourceRateLimitError` → 429, `SourceNetworkError` → 503) se apoya en que
`SourceEngine._call_source` (`engine.py:103-116`) **ya garantiza que nada sale sin tipar**:

```python
    async def _call_source(self, call):
        # El contrato es que el caller solo tiene que atrapar SourceError. Nada de lo que
        # lance una fuente — httpx exotico o un IndexError parseando HTML ajeno — puede
        # escapar de aqui sin tipar, o el caller se come un 500.
        try:
            return await call()
        except SourceError:
            raise
        except httpx.HTTPStatusError as error:
            raise _source_error_from_http_status(error) from error
        except httpx.HTTPError as error:
            raise SourceNetworkError("No se pudo conectar con la fuente") from error
        except Exception as error:
            raise SourceParseError("La fuente devolvio algo que no se pudo interpretar") from error
```

→ el handler pasa por el **engine**, no por `registry.get(...)` a pelo. Eso además paga **WR-01**
(`SourceEngine` no está exportado en `sources/__init__.py:22-43`: añadirlo a los imports y a
`__all__` son 2 líneas).

**Streaming del ZIP:** el `zipfile.ZipFile.open(member)` devuelve un file-like binario; va tal cual
a `StreamingResponse(..., media_type=...)`. **El ZipFile no se puede cerrar antes de que el stream se
agote** — si se abre con `with`, el response emite bytes de un fichero ya cerrado. Es el único
gotcha real de D-01 y no tiene precedente en el árbol que copiar.

---

### `database.py` — schema v9 (model, migración aditiva)

**Analog:** la propia escalera. Y **no es una escalera numerada**: es un `SCHEMA` idempotente
(`CREATE TABLE IF NOT EXISTS`) + `_add_column` + un `CANONICAL_SCHEMA_VERSION` que solo dispara el
backup. Tres tablas nuevas = tres `CREATE TABLE IF NOT EXISTS` en la constante `SCHEMA` + bump a 9.
**Cero código de migración nuevo.**

**La tabla que `reading_events` calca** (`database.py:24-35`):

```sql
CREATE TABLE IF NOT EXISTS playback_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    detected_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    source TEXT NOT NULL,
    raw_title TEXT NOT NULL,
    anime_title TEXT,
    episode INTEGER,              -- ← D-14: por esto NO se reutiliza. El 12.5 no cabe.
    status TEXT NOT NULL DEFAULT 'pending',
    media_id INTEGER,
    progress_before INTEGER,
    progress_after INTEGER
);
```

**El bump de versión + el backup** (`database.py:275`, `298-304`, `562-589`):

```python
CANONICAL_SCHEMA_VERSION = 8       # → 9

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self._requires_canonical_migration():
            self._backup_before_migration()     # el único rollback que existe
        with self.connect() as connection:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.executescript(SCHEMA)    # ← las tablas v9 entran AQUÍ, sin más
            ...
            connection.execute(
                "INSERT OR IGNORE INTO schema_migrations(version) VALUES (?)",
                (CANONICAL_SCHEMA_VERSION,),
            )
```

**El comentario de la v8, que es el modelo de comentario para la v9** (`database.py:344-346`):

```python
            # v8: el capítulo con decimal (10.5). NULL para anime y para el manga que
            # nunca pasó por el reader. Ver docs/specs/progress-model.md.
            self._add_column(connection, "library_entries", "chapter_progress", "REAL")
```

**El CRUD que `reading_events` copia** (`database.py:2307-2334`, `2402-2432`):

```python
    def insert_playback_event(self, source: str, raw_title: str, anime_title: str | None,
                              episode: int | None, status: str = "pending", ...) -> int:
        with self.connect() as connection:
            cursor = connection.execute(
                "INSERT INTO playback_events "
                "(source, raw_title, anime_title, episode, status, provider_id, account_id, "
                "canonical_media_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (source, raw_title, anime_title, episode, status, provider_id, account_id,
                 canonical_media_id),
            )
            return int(cursor.lastrowid)
```

`insert_reading_event(...)` es esta función con `chapter: float | None` en vez de
`episode: int | None`. **Un `insert_*` + un `get_recent_*` bastan para la Fase 3** (D-15: nadie lo
lee todavía; el `update_*`/`undo` los escribe la Fase 5, que es quien los necesita).

`reader_prefs` / `reader_progress` son upserts: el patrón está en `set_setting`
(`database.py:612-618`), `ON CONFLICT(key) DO UPDATE SET value = excluded.value`.

---

### `ReaderView.tsx` (NEW) — vista a pantalla completa (view, event-driven)

**Analog de forma:** `LocalLibraryView.tsx` (238 líneas). Frontend plano: una vista = un fichero en
`apps/desktop/src/`, exporta una función con nombre, recibe callbacks del padre (`onBack`,
`onSelect`), usa `useApp()` para i18n, `api.*` para datos, clases CSS con prefijo propio
(`.local-library`, `.local-assoc-*`).

**Imports + firma + persistencia de la preferencia** (`LocalLibraryView.tsx:1-19`):

```typescript
import { useEffect, useMemo, useState } from "react";
import { native } from "./native";
import { useApp, mediaFormatLabel } from "./i18n";
import { api } from "./api";
import { useContextMenu, type CtxItem } from "./ContextMenu";
import { useCompact } from "./hooks";
import type { LocalSeries, SearchResult } from "./types";

export function LocalLibraryView({ onBack, onSelect }: { onBack: () => void; onSelect: (series: LocalSeries) => void }) {
  const { t, titleLanguage } = useApp();
  const [items, setItems] = useState<LocalSeries[]>([]);
  const [loading, setLoading] = useState(true);
  const [layout, setLayout] = useState<LocalLayout>(() => (localStorage.getItem("local-layout") as LocalLayout) || "grid");
  const setLayoutPersist = (next: LocalLayout) => { setLayout(next); localStorage.setItem("local-layout", next); };
```

**Ojo:** `localStorage` es el patrón para prefs de **presentación** (layout, sort). El **modo de
lectura NO va ahí**: D-03/D-10 dicen que se recuerda **por serie**, en `reader_prefs`, en la BD. El
zoom/paneo sí es transitorio (D-11) y ni siquiera necesita `localStorage`.

**Teclado — el único patrón de teclado global del árbol** (`ContextMenu.tsx:96-114`):

```typescript
  useEffect(() => {
    const onDown = (event: MouseEvent) => { if (!ref.current?.contains(event.target as Node)) onClose(); };
    const onKey = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    window.addEventListener("blur", close);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
      window.removeEventListener("blur", close);
    };
  }, [onClose]);
```

RD-04 (←/→, AvPág/RePág, Espacio, Inicio/Fin) es **este** `useEffect` con un `switch (event.key)` y
su `removeEventListener` en el cleanup. No hay librería de atajos en el árbol, y no hace falta.

**Ventana de decodificación (RD-09 / D-07):** no hay analog. Es `<img>` normal montado solo para
`n-1..n+2`; React desmonta el resto y el bitmap se suelta. **No usar `new Image()` guardado en un
`useRef`/Map** — eso es exactamente el leak que el criterio de 500 MB de RSS existe para cazar.

**Ruta de la vista** (`App.tsx:46`, `180-184`, `1262-1263`):

```typescript
type View = "library" | "manga" | "now-playing" | ... | "local-library";

  const [view, setView] = useState<View>(() => {
    const requested = window.location.hash.slice(1) as View;
    const views: View[] = ["library", "manga", ..., "local-library"];
    return views.includes(requested) ? requested : "library";
  });
...
        ) : view === "local-library" ? (
          <LocalLibraryView onBack={() => setView("now-playing")} onSelect={(s) => void openDetails(...)} />
```

El reader es **a pantalla completa**: no encaja dentro de `<main>` (que vive bajo `.app-shell` con la
sidebar, `App.tsx:1155-1214`). Se renderiza **fuera** del `.app-shell`, hermano de `<Titlebar/>`
(`App.tsx:1153-1155`), con un estado propio (`readerChapter: string | null`) en vez de una entrada más
del union `View` — la sidebar no debe existir mientras se lee.

---

### `api.ts` (M) — cliente (service, request-response)

**Analog:** el objeto `api` (`api.ts:275-487`). Una línea por endpoint, `request<T>` para JSON,
`cachedGet<T>` para lo cacheable. Ejemplos a copiar (`api.ts:304-319`):

```typescript
  libraryFolders: () => request<LibraryFolder[]>("/api/library/folders"),
  getLocalLibrary: () => request<LocalSeries[]>("/api/library/local"),
  setScanSettings: (scanOnStartup: boolean, watchFolders: boolean) =>
    request<...>("/api/library/scan-settings", { method: "PUT", body: JSON.stringify({ ... }) }),
```

`request<T>` ya aplica `normalizeAssetUrls` (`api.ts:245-250`). **No se toca nada más de `api.ts`.**

---

## Shared Patterns

### Guardia FND-05 — `assert_no_persisted_urls` (obligatoria, no opcional)

**Source:** `apps/backend/tests/test_persisted_urls.py:156` (helper importable).
**Apply to:** **todo test de la Fase 3 que escriba una fila** (`reader_progress`, `reading_events`,
`reader_prefs`). Ya hay precedente de import cruzado: `test_source_api.py:25`.

```python
from tests.test_persisted_urls import assert_no_persisted_urls
assert_no_persisted_urls(connection)   # después de tus escrituras, no antes
```

Del docstring del módulo (líneas 23-33), literal: *«sobre una tabla vacía, un `SELECT ... LIKE
'http%'` no encuentra nada y el test es verde SIN HABER MIRADO NADA. Si la Fase 3 no invoca la
guardia después de sus propias escrituras, la guardia se queda verde mientras el reader persiste URLs
absolutas»*. Y hay un test que ya simula **este** fallo con una columna de página
(`test_guard_covers_columns_it_never_names`, línea ~330: `episodes.page_image_local =
'http://127.0.0.1:49876/assets/...'`).

### Tests de ruta — sustituir el registry en `app.state`

**Source:** `apps/backend/tests/test_source_api.py:61-75`.
**Apply to:** todo test HTTP del page pipe (orden de rutas, traversal, streaming del ZIP).

```python
@contextmanager
def _installed_registry(registry: SourceRegistry):
    missing = object()
    previous = getattr(app.state, "source_registry", missing)
    app.state.source_registry = registry
    try:
        yield
    finally:
        if previous is missing:
            try: delattr(app.state, "source_registry")
            except AttributeError: pass
        else:
            app.state.source_registry = previous
```

Con `TestClient(app)` + `_installed_registry(SourceRegistry([LocalArchiveSource(_Fetcher(), [{"id": "0", "path": str(tmp)}])]))`
se prueba la ruta contra un CBZ real de `tmp_path` sin tocar `lifespan`.

El test de **D-04** (orden) no necesita HTTP: se lee de `app.router.routes` y se compara el índice de
la ruta con el del `Mount`. El de **D-05** (traversal) sí: `GET /assets/pages/0:../../etc/passwd`,
`GET /assets/pages/0:C:\Windows\win.ini`, `GET /assets/pages/raiz-no-registrada:x.jpg` → 404, nunca 200.

### Registry construido una sola vez (WR-06)

**Source:** `main.py:1408-1410` (`lifespan`), `test_source_api.py:123-152`.
**Apply to:** cualquier endpoint nuevo que necesite una fuente.

```python
    app.state.source_registry = build_source_registry(
        library_folders=database.get_library_folders()
    )
```

Una carpeta añadida en caliente por `POST /api/library/folders` (`main.py:~1920`) **no aparece en el
registry hasta reiniciar el sidecar**. Es WR-06 y la Fase 3 es la que lo hace visible. La paga con
una línea (reconstruir el registry en el handler que añade/borra carpeta) o la declara como techo.

### Comentario que explica el porqué, no el qué

Convención transversal del árbol (`database.py:344`, `main.py:321`, `local_archive.py:25`,
`engine.py:104`, `api.ts:96`): los comentarios explican **la trampa** y **el bug real que ocurrió**,
en español. Los mensajes de commit, en inglés.

---

## No Analog Found

| Fichero / pieza | Rol | Data flow | Por qué no hay analog |
|---|---|---|---|
| `main.py` — `StreamingResponse(zipfile.open(...))` | controller | streaming | **No existe un solo `FileResponse` ni `StreamingResponse` en todo el backend** (verificado por grep sobre `apps/backend/nyanko_api/`). Todas las respuestas son JSON o el mount `StaticFiles`. Es stdlib + FastAPI: no hay que aprender nada, pero tampoco hay a quién copiar. Gotcha: el `ZipFile` no puede cerrarse antes de que el stream se agote. |
| `sources/contract.py` — obtener **bytes** de una página | contract | streaming | El `Source` Protocol tiene **3 métodos** (`search`/`chapters`/`pages`) y `SourcePage` **no lleva URL ni bytes** (`contract.py:32-38`). Nadie sabe hoy convertir un `page_id` en contenido. **Decisión de arquitectura que el planner tiene que tomar, y no es cosmética:** (a) un 4º método en el Protocol (`open_page`) → toca `SOURCE_API_VERSION` (hoy `1`), y `registry.register` **rechaza** toda fuente cuya `api_version` no case exactamente (`registry.py:35-42`), o (b) mantener el contrato en 3 métodos y que la ruta haga `isinstance(source, LocalArchiveSource)` → funciona hoy y **revienta en la Fase 7** (una fuente online no puede servir sus páginas). El precedente que empuja hacia (a): `SourceCapabilities` ya declara los `headers` que un CDN exige (SRC-05) — o sea, el contrato ya asume que **el sidecar** trae los bytes, no el renderer (ON-05). |
| `apps/desktop/index.html` + `splash.ts` — CSP | config | — | **No hay una sola CSP en el árbol** (grep sobre `apps/desktop/electron/` y `index.html`: cero). Seam G. Ver **H-3**: `img-src` necesita `https:`, `connect-src` necesita `ws://127.0.0.1:*`, el vehículo es `<meta http-equiv>` (no `onHeadersReceived`: prod es `file://`, el splash es `data:`), y el `script-src` del splash choca con los `onclick=` inline de `splash.ts:47-49`. |
| `ComicInfo.xml` (RD-08) | parser | file-I/O | Cero uso de `xml.etree` en el árbol (solo el RSS de torrents, que va por otro camino). Es `ElementTree.fromstring(zf.read("ComicInfo.xml"))` de stdlib; los campos que mandan sobre el nombre del fichero son `Number`, `Title`, `Series`, `PageCount`. |
| RSS del renderer < 500 MB (D-08) | test | — | No hay ningún test de memoria en el árbol. Necesita un capítulo sintético de 200 páginas y `process.memoryUsage()` / `webContents.getProcessMemoryInfo()` desde el main, o Playwright/Electron en CI. **Es el criterio de aceptación más caro de la fase y no tiene precedente**: conviene que sea su propio plan. |

---

## Metadata

**Analog search scope:** `apps/backend/nyanko_api/` (main, database, sources/, models, config,
progress), `apps/backend/tests/`, `apps/desktop/src/`, `apps/desktop/electron/main/`,
`apps/desktop/index.html`.
**Files scanned:** 22 leídos, ~40 grepeados. `main.py` (4.432 líneas) y `database.py` (2.816) leídos
por rangos dirigidos, nunca enteros.
**Pattern extraction date:** 2026-07-14
