# Phase 3: Page pipe + lectura local — la piedra angular - Context

**Gathered:** 2026-07-14
**Status:** Ready for planning

<domain>
## Phase Boundary

Un capítulo del disco (CBZ / ZIP / carpeta de imágenes) se convierte en **páginas servibles** por el
sidecar, y el renderer las **lee**: tres modos, navegación de escritorio completa, reanudar por
página, encadenado de capítulos, y una ventana de decodificación acotada con un número de RSS que
falla el test si se supera. Cero red, cero rate limits, cero scraping en la superficie de depuración.

**Dentro:** RD-01..RD-09, la CSP (Seam G), y el evento «capítulo terminado» (que aquí **no lo consume
nadie** — nace para que la Fase 5 lo encuentre ya escrito).

**Fuera:** fuentes online (Fase 7), descargas (Fase 8), vínculo con el tracker (Fase 4), sync
(Fase 5). El reader local es el **primer adapter** del contrato de la Fase 2, no un camino paralelo.

</domain>

<decisions>
## Implementation Decisions

### El camino de los bytes (la decisión arquitectónica de la fase)

- **D-01: Las páginas se sirven por una RUTA DINÁMICA bajo el prefijo `/assets`, sin copiar nada a
  disco.** Un endpoint tipo `/assets/pages/{page_id}` devuelve `FileResponse` cuando la página es un
  fichero suelto en una carpeta, y `StreamingResponse(zipfile.open(...))` cuando vive dentro de un
  CBZ/ZIP. Un solo camino para las dos formas.

- **D-02: No hay `_stream/`, no hay caché de lectura, no hay limpieza al arrancar.** Esto **anula el
  «Techo declarado» del ROADMAP** para esta fase (que preveía extraer a `assets_dir/_stream/` y
  limpiarlo al arrancar y al cerrar capítulo). La desviación va en la dirección buena: sin caché no
  existe el bug «la caché de páginas se come el SSD», y no hay estado en disco que reconciliar tras un
  cierre brusco. **Menos código y menos superficie, no más.**

- **D-03: Funciona porque `normalizeAssetUrls` (`apps/desktop/src/api.ts:202`) reescribe CUALQUIER
  string que empiece por `/assets`** — no solo ficheros del mount `StaticFiles`. La URL persistida y
  emitida es relativa; el host y el puerto los pone el renderer al renderizar. FND-05 sigue en verde
  por construcción.

- **D-04 (trampa a evitar, va en el plan): la ruta dinámica tiene que registrarse ANTES del
  `app.mount("/assets", StaticFiles(...))` de `main.py:1442`,** o el mount se traga la ruta. Starlette
  casa rutas en orden. Un test debe fallar si alguien reordena.

- **D-05 (seguridad, no negociable): el endpoint NUNCA acepta una ruta del sistema de ficheros.**
  Acepta un `page_id` opaco que se resuelve **a través de la fuente**, que ya valida contención
  (`local_archive.py::_resolve_id` hace `candidate.relative_to(root)`). El mount `/assets` es
  **no autenticado**: una ruta bajo ese prefijo que aceptara paths sería lectura arbitraria de disco
  desde cualquier página del renderer. Test de traversal obligatorio (`../../`, rutas absolutas,
  raíces no registradas).

- **D-06: la Fase 8 (descargas) no necesita nada de esto.** Lo descargado ya vive dentro de
  `assets_dir` y lo sirve el mount `StaticFiles` de siempre. DL-03 («lo descargado se lee igual que lo
  local») se cumple porque el reader consume **URLs**, no sabe de dónde salen.

### Memoria del reader (RD-09 — el número va en los criterios de aceptación)

- **D-07: ventana de decodificación ±2 → como mucho 5 páginas vivas** (`n-1, n, n+1, n+2`). Fuera de
  la ventana, el bitmap se suelta.
- **D-08: criterio de aceptación: RSS del renderer < 500 MB** tras recorrer un capítulo de 200 páginas
  de punta a punta **y volver**. (~5 × 24 MB de bitmap = 120 MB sobre la línea base de Electron
  ~250 MB: 500 MB deja margen real y sigue apretando lo suficiente para que un leak de bitmaps falle
  el test.) «Se siente bien» no es un criterio.

### Qué se recuerda, y con qué clave (RD-03, RD-05)

- **D-09: la clave es la identidad de la FUENTE (`source_name` + id), nunca `media_id`.** El vínculo
  con el tracker no existe hasta la Fase 4; keyear por `media_id` aquí obligaría a adivinar el defecto
  de los usuarios existentes cuando llegue.

- **D-10: dos tablas, cada una con su granularidad natural** (schema **v9**, aditivo, sin tocar nada
  existente):

  ```
  reader_prefs      (source_name, series_id)  PK
      mode TEXT        -- 'rtl' (defecto del manga) | 'ltr' | 'vertical'
      fit TEXT, double_page INTEGER, double_page_offset INTEGER

  reader_progress   (source_name, chapter_id) PK
      page INTEGER, updated_at TEXT
  ```

  El **modo es de la serie**; la **página es del capítulo**. RD-05 dice «reanuda **un** capítulo», no
  «el último capítulo», así que el progreso tiene que ser por capítulo.

- **D-11: el zoom y el paneo NO se persisten** — son transitorios, por sesión.
- **D-12: RTL es el defecto.** Abrir un manga L→R está roto de nacimiento.

### El evento «capítulo terminado» (RD-06 — la costura con la Fase 5)

- **D-13: tabla propia `reading_events`, calcada del patrón de `playback_events`** (que es el trato que
  la app ya le da a la detección de reproducción, y por tanto lo que hace que SYN-02
  proponer/confirmar/deshacer salga **gratis** en la Fase 5):

  ```
  reading_events
      id, detected_at, source_name
      series_id TEXT, chapter_id TEXT
      chapter REAL          -- 12.5 CABE. playback_events.episode es INTEGER y no
      status TEXT DEFAULT 'pending'
      media_id INTEGER      -- NULL hasta la Fase 4 (el vínculo)
      progress_before REAL, progress_after REAL
  ```

- **D-14: NO se reutiliza `playback_events`.** Parece lo perezoso, pero `episode` es `INTEGER` y el
  modelo de progreso de la Fase 1 es `REAL` **a propósito** (FND-04: `floor()` solo al enviar al
  proveedor). Un capítulo `12.5` se perdería ahí — y ahí es exactamente donde se corrompe el tracker.

- **D-15: en esta fase se escribe la fila y no la lee nadie. Eso es el diseño, no un cabo suelto.** El
  ROADMAP pone esta fase antes que el sync para que el evento exista **antes** que su consumidor.

### Claude's Discretion

- **CBZ/ZIP en `LocalArchiveSource`:** hoy la fuente **solo lee carpetas de imágenes**. Hay que
  enseñarle `zipfile` (stdlib) y `ComicInfo.xml` (RD-08: si viene, sus metadatos **mandan** sobre el
  nombre del fichero). El orden natural ya está (`_natural_key`, adelantado en la Fase 2).
- **CBR/RAR:** fuera de scope por decisión de licencia (REQUIREMENTS §Future). Se **detecta la
  extensión** y se dice «conviértelo a CBZ». No se intenta leer.
- **Entrada en la UI:** vista de lectura a pantalla completa, nueva. El ROADMAP marca `UI hint: yes`
  → conviene `/gsd-ui-phase 3` antes de planificar si se quiere contrato visual.
- **CSP:** `img-src 'self' http://127.0.0.1:* blob: data:`, en la ventana principal **y en la splash**
  (`electron/main/index.ts:42`, `electron/main/splash.ts:62` — las dos declaran las mismas
  `webPreferences` seguras). `webSecurity` sigue en `true`. Hoy no hay CSP en toda la app: si no
  aterriza aquí, no aterriza (Seam G).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### El contrato de fuente (la Fase 3 es su primer adapter)
- `apps/backend/nyanko_api/sources/contract.py` — `Source` Protocol (3 métodos), `SourcePage`,
  `SOURCE_API_VERSION`. El reader local NO inventa un camino paralelo.
- `apps/backend/nyanko_api/sources/local_archive.py` — la fuente a extender (hoy: solo carpetas).
- `.planning/phases/02-motor-de-fuentes-contrato-presupuesto-y-taxonom-a-de-errores/02-VERIFICATION.md`
  — qué quedó verificado y los 4 warnings que se vuelven reales al cablear el engine (WR-06: el
  registry se construye una sola vez en `lifespan` → una carpeta añadida en caliente es invisible
  hasta reiniciar. **Esta fase lo cablea, así que esta fase lo paga.**)

### La trampa del puerto efímero (ya nos costó todas las portadas)
- `.planning/research/STACK.md` §«The ephemeral-port trap» — `normalizeAssetUrls` + `resolveApiUrl`.
- `apps/desktop/src/api.ts:202` — `normalizeAssetUrls`, la reescritura que hace legal a D-01.
- `apps/backend/nyanko_api/main.py:1442` — el mount `/assets`. La ruta dinámica va **antes**.
- La guardia de la Fase 1 (`assert_no_persisted_urls`) es un **helper importable**: esta fase debe
  llamarlo tras SUS escrituras (decisión de la Fase 1, no opcional).

### Modelo de progreso (por qué `chapter` es REAL)
- `.planning/REQUIREMENTS.md` §FND-04, §RD-01..09 — los 9 requisitos de esta fase, literales.
- `apps/backend/nyanko_api/progress.py` — `effective_chapter`, `floor()` al enviar.
- `.planning/ROADMAP.md` §«Phase 3» — goal, 7 criterios de éxito, y el techo declarado que D-02 anula.

### Arquitectura y trampas
- `.planning/research/ARCHITECTURE.md` — `manga.py` estaba previsto como el módulo NUEVO del page pipe.
- `.planning/research/PITFALLS.md` — Pitfall 9 (memoria del reader), Pitfall 4 (URLs persistidas).
- `.planning/CODEX-RULES.md` — **Codex ejecuta los planes.** No corre tests, no commitea, no toca
  `conftest.py`. El orquestador corre la suite y commitea.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `normalizeAssetUrls` (`api.ts:202`): reescribe cualquier string `/assets…` con el `apiUrl` vivo.
  **Cero cambios** — es lo que permite servir páginas sin persistir host ni puerto.
- Mount `StaticFiles` en `/assets` → `settings.assets_dir` (`main.py:1442`, `config.py:88`): sirve lo
  descargado (Fase 8) sin código nuevo.
- `LocalArchiveSource._natural_key` / `_resolve_id`: orden natural y **contención de rutas** ya
  resueltos. El endpoint de páginas se apoya en `_resolve_id`, no en paths crudos.
- `playback_events` + su flujo proponer/confirmar/deshacer: el patrón que `reading_events` calca.
- Tabla `settings` (key/value): existe, pero **no** se usa para datos de dominio (D-10).

### Established Patterns
- Frontend plano: una vista = un fichero en `apps/desktop/src/` (`LocalLibraryView.tsx`,
  `TorrentsView.tsx`…). No hay carpeta `components/`. El reader sigue esa forma.
- Migraciones aditivas de esquema (v8 → v9). SQLite no tiene `ALTER COLUMN TYPE`: nada de rebuilds.
- Código y comentarios en **español**; mensajes de commit en **inglés**.

### Integration Points
- `main.py` `lifespan`: construye el registry de fuentes (`build_source_registry`). Aquí se cablea el
  engine por primera vez → WR-06 (registry estático) deja de ser latente.
- `electron/main/index.ts` + `splash.ts`: donde aterriza la CSP.
- `database.py`: schema v9 (`reader_prefs`, `reader_progress`, `reading_events`).

</code_context>

<specifics>
## Specific Ideas

- «El bug nº1 de los lectores locales» es el orden (`2.jpg` antes que `10.jpg`) — ya está pagado.
- El techo de memoria se escribe como **número** (RSS < 500 MB) porque «se siente bien» es lo que
  permite que un leak de bitmaps llegue a producción.
- La caché de páginas **no existe**: lo más barato de mantener es lo que no se escribe.

</specifics>

<deferred>
## Deferred Ideas

- **LRU / caché de lectura en disco:** no se construye. Si algún día servir desde el ZIP en cada
  página se mide como lento, se añade **con la medición delante**, no antes.
- **CBR / RAR:** decisión de licencia (cláusula de unRAR), no técnica. v0.3.x+, con presupuesto para
  `THIRD-PARTY-NOTICES`.
- **EPUB / PDF:** otro renderizador entero. v0.4+.
- **WR-01 (`SourceEngine` sin exportar) y WR-08 (`RateLimitedClient` sin cerrar):** deuda de la Fase 2,
  4 líneas cada una. Se pagan cuando se cablee el engine si el plan las toca de paso; si no, Fase 9.

</deferred>

---

*Phase: 3 - Page pipe + lectura local — la piedra angular*
*Context gathered: 2026-07-14*
