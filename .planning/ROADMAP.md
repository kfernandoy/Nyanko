# Roadmap: Nyanko

## Milestones

- ✅ **v0.2 Tauri → Electron** — Fases 1-5 (shipped 2026-07-13) — [archivo](milestones/v0.2-ROADMAP.md)
- 🚧 **v0.3 «Nyanko lee manga»** — Fases 1-9 (planificado 2026-07-13)

## Phases

<details>
<summary>✅ v0.2 Tauri → Electron (Fases 1-5) — SHIPPED 2026-07-13</summary>

Engine-swap del shell de escritorio: `src-tauri` (Rust) → electron-vite (main + preload + renderer),
sin tocar el renderer React, el backend Python sidecar ni la extensión. Regla dura: paridad con
0.1.15, cero features nuevas.

- [x] Fase 1: Electron shell scaffold + data-dir lock (2/2 plans) — 2026-07-10
- [x] Fase 2: Main core — sidecar lifecycle + logging (2/2 plans) — 2026-07-10
- [x] Fase 3: Native boundary + Tauri removal (2/2 plans) — 2026-07-11
- [x] Fase 4: Native feature parity (3/3 plans) — 2026-07-11
- [x] Fase 5: Packaging + auto-update (6/6 plans) — 2026-07-12

Detalle completo (goals, success criteria, waves): [milestones/v0.2-ROADMAP.md](milestones/v0.2-ROADMAP.md)

</details>

### 🚧 v0.3 «Nyanko lee manga»

- [x] **Phase 1: Fundaciones — limitador, esquema y modelo de progreso** - Nada hace una ráfaga ni escribe una fila hasta que el limitador limita de verdad y el modelo de progreso está decidido y migrado contra la BD real (completed 2026-07-13)
- [ ] **Phase 2: Motor de fuentes — contrato, presupuesto y taxonomía de errores** - Existe un contrato de fuente versionado contra el que construir, con el presupuesto de peticiones en el motor y no en sus llamadores
- [ ] **Phase 3: Page pipe + lectura local — la piedra angular** - Nyanko lee la colección de CBZ del disco: sin red, sin rate limits, sin scraping en la superficie de depuración
- [ ] **Phase 4: Identidad y vínculo — fuente ↔ entrada del tracker** - El vínculo es explícito, almacenado y confirmado por el usuario; el sync podrá asumirlo o negarse
- [ ] **Phase 5: Sync de progreso — la tesis del milestone** - Última página → el progreso sube solo al proveedor, con confirmar/deshacer y en el timeline
- [ ] **Phase 6: Distribución de extensiones — repo, instalación y trust gate** - La app se instala sin catálogo; el usuario pega la URL de un repo y ninguna extensión se ejecuta hasta que acepta su huella
- [ ] **Phase 7: Lectura online — el camino de la app hasta una fuente instalada** - Buscar, explorar y leer manga online, verificado en build empaquetado (los adapters los escribe el autor, fuera de GSD)
- [ ] **Phase 8: Cola de descargas** - Lectura offline: lo descargado se lee exactamente como lo local, y una descarga sobrevive a un cierre brusco
- [ ] **Phase 9: AnimeThemes, deuda de 0.2 y auditoría de costuras** - OP/ED en las cards, la deuda saldada, y el único control que en 0.2 encontró un blocker que todas las fases habían aprobado

## Phase Details

### Phase 1: Fundaciones — limitador, esquema y modelo de progreso

**Goal**: Nada en el milestone hace una ráfaga ni escribe una fila hasta que el limitador limita de verdad y el modelo de progreso está escrito, decidido y migrado contra una copia de la BD real.

**Depends on**: Nada (primera fase)

**Requirements**: FND-01, FND-02, FND-03, FND-04, FND-05, FND-06

**Success Criteria** (qué tiene que ser VERDAD):

  1. Una ráfaga de 50 peticiones concurrentes lanzada **desde los dos event loops** (el de uvicorn y el de `MutationWorker`) no produce `RuntimeError` ni se cuelga, y el ritmo observado respeta el `X-RateLimit-Limit` **que devolvió el proveedor** — no un número horneado en el código.
  2. Tras un 429, el limitador se adapta al presupuesto degradado (AniList: 30/min) y vuelve al normal (90/min) cuando el proveedor lo anuncia. Ningún test pasa por el hecho de haber hardcodeado ninguno de los dos números.
  3. La migración a schema v8 corre contra una **copia de la BD de producción real** (2.761 `library_entries`, 25.727 `episodes`) y sale con `integrity_check: ok` y los mismos recuentos por tabla; el backup pre-migración se dispara (es el único rollback que existe).
  4. El capítulo 10.5 se guarda `REAL` en local y se envía `floor()`eado (10) al proveedor; la guarda monotónica compara contra el valor *del tracker* y `progress_before` se graba en cada sync.
  5. Un test de guardia falla si **cualquier** columna persistida empieza por `http` — extendido a las columnas nuevas del esquema v8.

**Cierra**: Pitfall 1 (el limitador son **tres** bugs: el número, el semáforo retenido durante el sleep, y el singleton compartido entre loops — arreglar solo el 90→30 es lo que *arma* los otros dos). Pitfall 6 (`progress` es `INTEGER` y el capítulo 10.5 no tiene dónde ir). Pitfall 10. Seams A, C, E.

**Deuda saldada**: D-I-03 de 0.2, **promovida de limpieza a prerrequisito**.

**No hay tarea de updater aquí**: D-2 saca la superficie de takedown (las fuentes) fuera del repo de la app, así que el feed se queda en GitHub Releases. El «desacoplar el feed» que pedía el research se consigue por el otro extremo, y sin tocar el updater.

**Research pass**: No. Precedente en el árbol, citado: `_clients` ya está keyed por event loop y con el comentario que explica por qué — el semáforo nunca recibió el mismo trato. `_backup_before_migration` ya existe.

**Plans**: 4/4 plans complete

- [x] 01-04-PLAN.md

**Wave 1**

- [x] 01-01-PLAN.md — Limitador: los tres bugs a la vez (presupuesto de la cabecera, sleep fuera del semáforo, estado por event loop) — FND-01, FND-02, FND-03 — wave 1
- [x] 01-02-PLAN.md — Modelo de progreso escrito + esquema v8 aditivo, migrado contra copia de la BD real — FND-04, FND-06 — wave 1

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 01-03-PLAN.md — Guardia de URLs persistidas, genérica por `PRAGMA table_info` — FND-05 — wave 2

---

### Phase 2: Motor de fuentes — contrato, presupuesto y taxonomía de errores

**Goal**: Existe un contrato de fuente versionado contra el que se puede construir, con el presupuesto
de peticiones **en el motor y no en sus llamadores**, y con los errores tipados antes de que exista un
solo consumidor.

**Depends on**: Fase 1 (el limitador arreglado es precisamente lo que el motor pasa a poseer)

**Requirements**: SRC-04, SRC-05, SRC-06, SRC-07

**Success Criteria** (qué tiene que ser VERDAD):

  1. Una fuente que declara una versión de API distinta de `SOURCE_API_VERSION` se **rechaza al registrar** y se reporta en la UI; el sidecar arranca igual. Una fuente rota no tumba la app.
  2. Un test de conformidad **parametrizado sobre todas las fuentes registradas** pasa (incluida `LocalArchiveSource`); añadir una fuente que no cumple el Protocol rompe el test. Eso es lo que convierte «API versionada» de docstring en gate.
  3. Un parseo que encuentra 0 resultados **lanza** (`ParseError`), nunca devuelve `[]`; y un fallo de fuente **no pisa** una lista de capítulos buena ya cacheada (test: cachear lista → simular reto de Cloudflare con HTTP 200 y cuerpo HTML → la lista cacheada sigue intacta).
  4. Dos consumidores simultáneos de la misma fuente (prefetch del reader + cola de descargas, simulados) beben del **mismo cubo**: el ritmo agregado no supera el presupuesto declarado por la fuente.
  5. Una fuente declara sus headers (`Referer`/UA) **como dato** y el fetcher genérico los aplica sin saber nada de esa fuente.
  6. En **build empaquetado** (PyInstaller onedir) la lista de fuentes registradas **no está vacía**: imports explícitos + lista `SOURCES`, jamás autodiscovery por `pkgutil`/`importlib` (que en el frozen encuentra cero y envía un catálogo vacío que en dev funcionaba).

**Cierra**: Seam F (dos limitadores individualmente correctos dan el doble de ritmo y un baneo de IP — el presupuesto tiene que ser del motor **antes** de que existan la cola y el prefetch; retrofittearlo después obliga a reescribir todos los adapters). Pitfalls 4 y 5. La trampa de PyInstaller.

**Nota**: `LocalArchiveSource` es el primer adapter y vive **en el árbol de la app**. No scrapea nada, así que no es superficie de takedown — D-1 prohíbe enviar el catálogo de nadie, no tener un adapter para los ficheros del propio usuario.

**Research pass**: No. El contrato está completamente investigado (forma del Protocol, versionado, taxonomía de errores, la trampa de PyInstaller) y la decisión abierta que el research dejaba aquí (bundled vs runtime-loadable) ya está **tomada por el humano**: D-1/D-2/D-3.

**Plans**: 1/3 plans executed

- [ ] 02-01-PLAN.md
- [x] 02-02-PLAN.md
- [ ] 02-03-PLAN.md

---

### Phase 3: Page pipe + lectura local — la piedra angular

**Goal**: «Nyanko lee mi colección de CBZ.» Aquí la arquitectura de entrega de páginas se vuelve
verdadera o falsa, y se prueba con **cero red, cero rate limits y cero fragilidad de scraping** en la
superficie de depuración. Todo lo de aguas abajo (fuentes online, descargas, sync) es un productor que
se enchufa a un pipe que ya corre.

**Depends on**: Fase 1 (esquema), Fase 2 (el contrato; el reader local es su primer adapter)

**Requirements**: RD-01, RD-02, RD-03, RD-04, RD-05, RD-06, RD-07, RD-08, RD-09

**Success Criteria** (qué tiene que ser VERDAD):

  1. Un CBZ / ZIP / carpeta con `2.jpg … 10.jpg` se lee en **orden natural** (`2` antes que `10`). Si trae `ComicInfo.xml`, sus metadatos mandan sobre el nombre del fichero.
  2. Los tres modos funcionan — paginado **RTL por defecto** (abrir un manga L→R está roto de nacimiento), paginado LTR, y continuo vertical / webtoon — y el modo elegido **se recuerda por serie** y sobrevive a reiniciar la app. Doble página con offset manual ajustable.
  3. Navegación de escritorio completa: teclado (←/→, AvPág/RePág, Espacio, Inicio/Fin), rueda, zonas de click, pantalla completa, contador de página, modos de ajuste, zoom y paneo. Se reanuda por la página donde se dejó.
  4. Encadenar al siguiente/anterior capítulo con pantalla de transición — y esa transición **emite el evento «capítulo terminado»**, aunque en esta fase todavía no lo consuma nadie. Ahí es donde nace el trigger del sync.
  5. El RSS del renderer se mantiene **por debajo de un número escrito en los criterios de aceptación** tras recorrer un capítulo de 200 páginas de punta a punta y volver (ventana de decodificación acotada — una página es un JPEG de 200 KB en disco y un bitmap de 24 MB en RAM; «se siente bien» no es un criterio).
  6. Ninguna URL de página persiste con host o puerto dentro: las páginas se sirven como `/assets/…` **relativo** por el mount `StaticFiles` existente y se resuelven al renderizar con `normalizeAssetUrls`. El test de guardia de la Fase 1 sigue en verde.
  7. Existe una **CSP** (`img-src 'self' http://127.0.0.1:* blob: data:`) — hoy no hay ninguna en toda la app — y `webSecurity` sigue en `true`.

**Cierra**: Pitfall 9 (memoria del reader). Pitfall 4 (**este proyecto ya perdió todas las portadas de la biblioteca por persistir el puerto efímero dentro de una URL**; el reader es una superficie diez veces mayor). Seam G (la CSP no tiene otro dueño: si no aterriza aquí, no aterriza).

**Techo declarado**: la caché de lectura `_stream/` se limpia al arrancar y al cerrar capítulo. Sin LRU. Se añade si alguien se queja — pero el techo se escribe aquí, o «caché de páginas sin límite se come el SSD» se convierte en un bug real.

**Research pass**: No. Todo tiene precedente en el árbol: el mount `/assets`, `normalizeAssetUrls` (`api.ts:202`), `zipfile`/`pathlib`/`re` de stdlib. No hay nada que aprender, solo precedente que seguir.

**Plans**: TBD

**UI hint**: yes

---

### Phase 4: Identidad y vínculo — fuente ↔ entrada del tracker

**Goal**: Existe un vínculo **explícito, almacenado y confirmado por el usuario** entre una serie de una
fuente y una entrada del tracker — para que el sync pueda asumirlo, y **negarse** cuando no lo hay.

**Depends on**: Fase 3 (hay algo que leer, y por tanto algo que vincular)

**Requirements**: LNK-01, LNK-02, LNK-03, LNK-04

**Success Criteria** (qué tiene que ser VERDAD):

  1. `matcher.py` **propone** un vínculo con un score de confianza; nada queda vinculado sin que el usuario lo confirme; la corrección del usuario se guarda y manda sobre la propuesta.
  2. El vínculo se **almacena** (mirror de `media_mappings`, con su `chapter_offset`, igual que el `episode_offset` que ya está enviado) — nunca se calcula en el momento del sync.
  3. `ChapterRecognition` es un componente **propio, puro y unitariamente testeable**, con su tabla de casos escrita **antes** que el código (`extra` = .99, `omake` = .98, `12a` → 12.1) y en verde. Si no se le pone nombre, se embadurna entre el motor y el sync y no se testea en ninguno de los dos.
  4. Un intento de sync sobre una serie **sin vínculo confirmado falla cerrado**: se lo dice al usuario, no escribe, no encola. Verificado como test, no como intención.

**Cierra**: Pitfalls 3 y 7. Seam D.

**Por qué es fase propia**: es el peor fallo posible del milestone y se trata como **corrupción de datos, no como UX**. Leo el capítulo 12 de la serie A → el matcher difuso lo vincula a la serie B → la app escribe progreso en la serie B de mi AniList real → `pending_mutations` lo **reintenta de forma duradera** → no hay deshacer, porque nadie se enteró de nada. Un 5% de fallo es invisible en una demo y devastador en una lista de 2.761 entradas. Doblarlo como «paso 1 del sync» es *exactamente* como acaba siendo implícito y ansioso.

**Research pass**: No. Precedentes: `media_mappings` (la tabla que este problema necesita, con columna de offset y todo, construida para la extensión de navegador), `matcher.py`, `match_corrections`, el flujo detectar→proponer→confirmar→deshacer de `playback_events`.

**Plans**: TBD

---

### Phase 5: Sync de progreso — la tesis del milestone

**Goal**: Leo la última página de un capítulo y el progreso **sube solo** al proveedor, con
confirmar/deshacer y apareciendo en el timeline — el mismo trato que la detección de reproducción ya
le da al anime. Aquí el core value queda **probado**, antes de que empiecen los dos trozos caros.

**Depends on**: Fases 3 y 4 (duro — un roadmap que pone el sync antes del vínculo está planificando una fase falsa)

**Requirements**: SYN-01, SYN-02, SYN-03, SYN-04, SYN-05

**Success Criteria** (qué tiene que ser VERDAD):

  1. Llegar a la última página del capítulo encola una mutación por el **camino existente** (`enqueue_mutation` → `MutationWorker` → `providers.edit_entry(media_type="MANGA")`). **No hay un segundo camino de sync en el árbol** — verificable por grep, porque construirlo es el anti-patrón nº1 de esta fase.
  2. El capítulo 10.5 sube como `10`; la guarda monotónica compara contra el valor **del tracker**, no contra el local; `progress_before` queda grabado en cada sync.
  3. Una entrada `COMPLETED` cuyo capítulo leído es menor que el progreso ofrece `REPEATING` — **jamás** empuja un `1` encima de una serie terminada.
  4. La lectura aparece en el timeline de actividad, con confirmar y deshacer.
  5. Sin vínculo confirmado (Fase 4), no sube nada: falla cerrado.
  6. Con la red caída, el capítulo terminado se sincroniza solo **al reconectar** — gratis, por reusar la cola. Y el worker drena 10 cada 3 s, así que el reader es **estructuralmente incapaz** de martillear AniList.
  7. El sync es **de una sola dirección** (Nyanko → tracker). No existe código que lea progreso del tracker para escribirlo en local.

**Cierra**: AP-1 (el segundo camino de sync). Es ~15 líneas + una guarda de idempotencia: poner la tesis del milestone *después* de dos fases HIGH-cost es como un milestone se alarga y se envía sin su punto.

**Research pass**: No. El camino ya funciona de punta a punta: el manga pasó a ser first-class en `edit_entry` antes de la 0.3.

**Plans**: TBD

---

### Phase 6: Distribución de extensiones — repo, instalación y trust gate

**Goal**: Nyanko se instala **sin catálogo**. El usuario pega la URL de un repo de extensiones, ve sus
fuentes, y **ninguna se ejecuta** hasta que acepta su huella explícitamente.

**Depends on**: Fase 2 (el contrato que las extensiones cumplen)

**Requirements**: SRC-01, SRC-02, SRC-03

**Success Criteria** (qué tiene que ser VERDAD):

  1. Una instalación limpia trae **cero** fuentes de manga (D-1). La pantalla de extensiones está vacía y explica cómo añadir un repo.
  2. El usuario pega la URL de un repo, la app resuelve su `index.json` y lista las fuentes con nombre, versión y estado (no instalada / instalada / actualizable).
  3. Instalar, actualizar y desinstalar una fuente funciona. El bundle descargado se verifica contra el `sha256` fijado en el índice, y **una huella que no cuadra aborta la instalación** en vez de continuar.
  4. Una extensión **no confiada no se importa**: se muestra su huella y, hasta que el usuario la acepta, su código **no llega al intérprete**. Test: una extensión con un `raise` a nivel de módulo; sin aceptar la huella, el sidecar ni se entera. (En Mihon el APK lo instala Android, que verifica la firma y pide permiso. Nyanko no tiene esa puerta: un módulo Python que el sidecar importa es ejecución de código arbitrario con los permisos del usuario. Sin este gate, un repo pegado en un foro es RCE.)
  5. Revocar la confianza descarga la fuente y vuelve a bloquearla.

**Restricción dura (D-2)**: `nyanko-extensions` **nunca** se fusiona con el repo de la app, y el índice **nunca** se sirve desde él. El feed del auto-updater se queda en GitHub Releases — y eso solo es seguro *porque* la superficie de takedown ya no comparte repo con el feed. Precedente propio: v0.2.1 y v0.2.2 ya dan 404; un takedown sobre el repo de la app no rompería una descarga, dejaría sin auto-update a toda la base instalada, de forma permanente y sin canal para avisarles.

**Cierra**: Pitfall 12, resuelto por arquitectura (D-1/D-2) y no por config. D-3: el bundle es **código**, luego la confianza es explícita — el gate no es pulido, es el requisito (SRC-03).

**Research pass**: No. D-1/D-2/D-3 ya deciden el diseño; el modelo de repo+índice+huella es el de Mihon, y está documentado.

**Plans**: TBD

**UI hint**: yes

---

### Phase 7: Lectura online — el camino de la app hasta una fuente instalada

**Goal**: El usuario busca, explora y **lee manga online** desde fuentes instaladas — con el reader, el
pipe, el esquema y el sync ya hechos y sin tocar. Esto es «solo adapters», y es donde aparece la
fragilidad real (HTML que cambia, Cloudflare, headers de hotlink).

**Depends on**: Fase 1 (el limitador), Fase 2 (el motor), Fase 3 (el pipe), Fase 6 (el canal de instalación)

**Requirements**: ON-01, ON-02, ON-03, ON-04, ON-05

**Entrada humana — no la produce esta fase (D-4)**: los adapters los **escribe el autor a mano**, en el
repo `nyanko-extensions`, fuera del flujo GSD. Portar una extensión de Mihon es reescribirla (Kotlin/APK
→ Python), no convertirla. Esta fase entrega el **lado app**: el camino completo hasta una fuente ya
instalada, y su verificación. **Un ejecutor no escribe adapters de catálogos reales.** Lo que sí produce
la fase es la fuente de conformidad (fixture, servida por un servidor local) contra la que se testea el
camino sin depender de un sitio vivo — que es también lo que hace que estos tests no se rompan cuando un
sitio cambie su HTML.

**Gate**: la fase no puede cerrar su verificación hasta que exista **al menos un adapter real del autor**
instalable — el criterio 5 (build empaquetado, `file://`, hotlink) solo es verdad contra una fuente viva.

**Success Criteria** (qué tiene que ser VERDAD):

  1. El camino app→fuente funciona contra cualquier adapter que cumpla el contrato de la Fase 2: se instala por el flujo de la Fase 6 y queda utilizable sin tocar código de la app.
  2. El usuario busca, explora (popular / recientes) y abre una serie de una fuente online.
  3. Lista de capítulos con número, **scanlator**, idioma, fecha de subida, estado de lectura y estado de descarga; ordenar/filtrar; «marcar anteriores como leídos».
  4. Lectura online con prefetch **acotado** (±2-3 páginas, nunca «el capítulo entero»), bebiendo del mismo cubo de presupuesto que posee el motor (Fase 2).
  5. **Verificado en build empaquetado (`file://`), no en dev**: ni una sola petición sale del renderer; todo byte de página va renderer → sidecar → fuente. En dev el renderer tiene origen real (`http://localhost:5173`); en producción es `file://` y su origen es `null` — **un reader perfecto durante todo el desarrollo devuelve un muro de imágenes rotas el día que se empaqueta**.
  6. Un capítulo licenciado (MangaDex devuelve `externalUrl` + `pages: 0`) se muestra como no legible, no como «este capítulo tiene 0 páginas».

**Cierra**: Pitfall 2 (el origen `file://` en producción).

**Research pass**: **Ligero.** La pregunta que el research dejaba abierta («qué 2-3 fuentes», y la postura por sitio: Cloudflare, hotlink/`Referer`, forma del HTML, ToS) **deja de ser de esta fase**: la resuelve el autor al escribir los adapters. Lo que queda para la app es la costura `file://` en build empaquetado, que ya está documentada y no necesita investigación.

**Plans**: TBD

**UI hint**: yes

---

### Phase 8: Cola de descargas

**Goal**: El usuario descarga capítulos y los lee offline — y **lo descargado se lee exactamente igual
que lo local**, porque el pipe no puede distinguirlos.

**Depends on**: Fase 2 (el presupuesto), Fase 3 (el pipe), Fase 7 (no hay nada que valga la pena descargar de un archivo local)

**Requirements**: DL-01, DL-02, DL-03, DL-04, DL-05, DL-06

**Success Criteria** (qué tiene que ser VERDAD):

  1. Encolar en lote, pausar, reanudar y cancelar; el progreso se observa **por polling** de `GET /api/manga/downloads`, como el backfill ya hace. Ni SSE, ni WebSocket, ni librería de jobs.
  2. **Serie por fuente, paralelo entre fuentes**, verificado con dos fuentes descargando a la vez. Restricción dura para no comerse un baneo de IP — no una perilla de ajuste.
  3. Las URLs de página se resuelven **al descargar, no al encolar**. Test: un capítulo que espera en cola más que la caducidad de la URL firmada **aun así descarga** (encolar las URLs es el diseño obvio, y es el que devuelve 404s).
  4. Matar la app a lo bruto en mitad de una descarga (que es literalmente lo que hace `killSidecar()`: `taskkill /T /F`, cero oportunidad de vaciar buffers) y arrancar: la fila `downloading` se resetea, el `.part` se borra, y **un capítulo a medias nunca parece legible**. `.part` + `fsync` + rename atómico + verificación del archivo antes de marcar completo. Un solo mecanismo cubre cuatro bugs: el kill del updater, un crash, el Administrador de tareas y un corte de luz.
  5. Lo descargado se lee por el **mismo endpoint y el mismo código** que lo local — la prueba es que **no existe una segunda ruta** (grep). No es una feature: es la ausencia de una.
  6. El updater **avisa y reanuda**: con 3 capítulos descargando, la actualización lo dice («seguirán tras la actualización») y al volver siguen.

**Cierra**: Pitfall 8. **Seam B** — DL-06 vive **aquí**, no en una fase posterior de «pulido»: esa es exactamente la costura donde se pierde. El updater pasó su gate en 0.2 contra un sidecar que no tenía cola de descargas.

**Research pass**: **Ligero — `/gsd-plan-phase 8 --research-phase 8`.** La mecánica está mapeada (rename atómico, reconciliación al arrancar, `MAX_PATH` de Windows, serial-por-fuente). Lo único abierto es **ejercitar la costura del updater** contra una cola que no existía cuando el updater pasó su gate.

**Plans**: TBD

**UI hint**: yes

---

### Phase 9: AnimeThemes, deuda de 0.2 y auditoría de costuras

**Goal**: Los OP/ED suenan desde la card, la deuda de 0.2 queda saldada, y el milestone **no se cierra
hasta que la auditoría cruzada de costuras pasa** — con el milestone entero en el árbol, no fase a
fase.

**Depends on**: AnimeThemes y la deuda no dependen de nada (se pueden adelantar). La auditoría depende, por definición, de todas.

**Requirements**: AT-01, AT-02, AT-03, DBT-01, DBT-02, DBT-03

**Success Criteria** (qué tiene que ser VERDAD):

  1. Las cards listan sus openings/endings y se reproducen desde la card, con **un solo `<audio>` global**: así «solo suena uno a la vez» es verdad **por construcción**, y son menos líneas que uno por card.
  2. La búsqueda es **por ID directo** contra `external_identities` (AniList/MAL/Kitsu — los tres `filter[site]` verificados en vivo): **cero matching difuso**. Se cachea el metadato, **nunca la URL del CDN**. La consulta ocurre al **abrir la card**, no al renderizar la biblioteca.
  3. Se respetan las banderas `spoiler` y `nsfw` que la API devuelve. (Y las trampas ya resueltas: nada de `HEAD` — devuelve 403 y haría parecer que **ningún** tema existe; nada de `crossOrigin`, Web Audio ni `fetch()` — la API **no manda cabeceras CORS**; el `.ogg` de 3,7 MB sobre el `.webm` de 30 MB.)
  4. **W-3**: el tray refleja el estado real cuando la detección se pausa desde la UI.
  5. `RELEASING.md` está trackeado en git y deja de vivir solo en la máquina del autor (`docs/extra/` está gitignorado).
  6. **La auditoría cruzada de costuras** corre con la tabla de seams de `research/PITFALLS.md` **como checklist literal**, sobre el milestone completo, y ninguna costura queda abierta antes de cerrar.

**Por qué la auditoría no es sobrecoste**: en 0.2 fue **el único control que funcionó**. El audit cruzado es lo único que encontró B-1 — y lo encontró *después* de que las cinco fases hubieran pasado su verificación. Una fase verificada no es una fase segura; los fallos viven en las costuras.

**Nota de corte**: si el milestone se alarga, **lo que se corta es AnimeThemes. La auditoría no.**

**Research pass**: No. Todas las trampas de la API de AnimeThemes ya se comprobaron en vivo (2026-07-13).

**Plans**: TBD

---

## Cobertura de requisitos

**48/48 requisitos v0.3 mapeados. Cero huérfanos, cero duplicados.**

| Categoría | Requisitos | Fase |
|-----------|------------|------|
| FND (Fundaciones) | FND-01 … FND-06 (6) | 1 |
| SRC (Motor de fuentes) — contrato | SRC-04, SRC-05, SRC-06, SRC-07 (4) | 2 |
| RD (Reader) | RD-01 … RD-09 (9) | 3 |
| LNK (Identidad y vínculo) | LNK-01 … LNK-04 (4) | 4 |
| SYN (Sync de progreso) | SYN-01 … SYN-05 (5) | 5 |
| SRC (Motor de fuentes) — distribución | SRC-01, SRC-02, SRC-03 (3) | 6 |
| ON (Fuentes online) | ON-01 … ON-05 (5) | 7 |
| DL (Descargas) | DL-01 … DL-06 (6) | 8 |
| AT (AnimeThemes) + DBT (Deuda) | AT-01…AT-03, DBT-01…DBT-03 (6) | 9 |

## Restricciones de orden (duras)

Violar cualquiera de estas es cómo este milestone envía su propio B-1.

1. **El limitador (Fase 1) antes del reader, las descargas y el sync.** Estaba archivado como «deuda de
   0.2»; es un **prerrequisito**. Son tres bugs, y arreglar solo el número (90→30) es lo que *arma* los
   otros dos. (Seam A)

2. **Las decisiones de esquema y modelo de progreso (Fase 1) antes de que nada escriba una fila.**
   Cambiar la semántica de `progress` después de que los usuarios hayan escrito filas es migrar una
   biblioteca real de 2.761 entradas.

3. **El motor con su presupuesto y su taxonomía de errores (Fase 2) antes del reader online y de la
   cola de descargas.** Retrofittear un presupuesto compartido cuando la cola ya existe significa
   reescribir todos los adapters. (Seam F)

4. **El vínculo (Fase 4) antes del sync (Fase 5).** Fase propia, no «paso 1 del sync» — que es
   exactamente como acaba siendo ansioso e implícito. (Seam D)

5. **La lectura local (Fase 3) antes de las fuentes online (Fase 7).** El pipe de páginas es la piedra
   angular y es más barato probarlo sin red, sin rate limits y sin scraping en la superficie de
   depuración. Además envía una porción útil por sí sola.

6. **El sync (Fase 5) pronto, no al final.** Son ~15 líneas y es la tesis del milestone: probar el core
   value **antes** de que empiecen los dos trozos caros (fuentes online y descargas) es el punto.

## Nota de granularidad

`granularity: coarse` (2-4 fases). Este roadmap tiene **9**, y la desviación es deliberada: 48
requisitos y **seis restricciones de orden duras** ponen el suelo. La compresión que sí se aplicó:
AnimeThemes y la deuda/auditoría, que el research proponía como fases 8 y 9 separadas, van juntas en
la Fase 9; y la distribución de extensiones (Fase 6), que D-1/D-2/D-3 añaden como trabajo nuevo que el
research no tenía, se separó del contrato del motor (Fase 2) en vez de inflar una sola fase con el
backend, el cliente HTTP, la verificación sha256, el gate de seguridad y una UI.

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Electron shell scaffold + data-dir lock | v0.2 | 4/4 | Complete    | 2026-07-13 |
| 2. Main core — sidecar lifecycle + logging | v0.2 | 1/3 | In Progress|  |
| 3. Native boundary + Tauri removal | v0.2 | 2/2 | Complete | 2026-07-11 |
| 4. Native feature parity | v0.2 | 3/3 | Complete | 2026-07-11 |
| 5. Packaging + auto-update | v0.2 | 6/6 | Complete | 2026-07-12 |
| 1. Fundaciones — limitador, esquema y modelo de progreso | v0.3 | 0/? | Not started | - |
| 2. Motor de fuentes — contrato, presupuesto y taxonomía | v0.3 | 0/? | Not started | - |
| 3. Page pipe + lectura local | v0.3 | 0/? | Not started | - |
| 4. Identidad y vínculo | v0.3 | 0/? | Not started | - |
| 5. Sync de progreso | v0.3 | 0/? | Not started | - |
| 6. Distribución de extensiones — repo, instalación y trust gate | v0.3 | 0/? | Not started | - |
| 7. Fuentes online — 2-3 fuentes propias | v0.3 | 0/? | Not started | - |
| 8. Cola de descargas | v0.3 | 0/? | Not started | - |
| 9. AnimeThemes, deuda de 0.2 y auditoría de costuras | v0.3 | 0/? | Not started | - |
