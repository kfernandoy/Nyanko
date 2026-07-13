# Requirements: v0.3 «Nyanko lee manga»

**Milestone:** v0.3
**Core value:** Nyanko deja de ser solo un tracker y pasa a ser **donde consumes**: el manga se lee
dentro de la app, y el tracking ocurre solo — el mismo trato que la detección de reproducción ya le
da al anime.
**Defined:** 2026-07-13
**Research:** `.planning/research/SUMMARY.md` (confidence: HIGH)

---

## Decisiones que fijan el diseño

Tomadas antes de planificar, porque ninguna se puede retrofittear después.

### D-1 — Nyanko no envía ninguna fuente (modelo Mihon)

La app se instala **sin catálogo**. El usuario añade la URL de un repo de extensiones y de ahí salen
las fuentes. Nyanko no distribuye el catálogo de nadie.

**Por qué:** Tachiyomi fue cerrado en enero de 2024 por una C&D de Kakao dirigida a sus
contribuidores *personalmente*; su concesión fue **quitar la lista de extensiones precargada**. Mihon
hoy no envía ninguna fuente, y eso no es una preferencia de empaquetado: es arquitectura legal que
sostiene el proyecto. Nyanko con scrapers propios compilados en un binario firmado, con auto-update,
publicado por un autor con nombre, sería estrictamente peor en todos los ejes que el proyecto que sí
cerraron.

### D-2 — Las fuentes propias viven en un repo aparte (`nyanko-extensions`)

Las 2-3 fuentes de estreno son de Nyanko, pero **no viven en el repo de Nyanko**. Repo separado,
índice `index.json` propio.

**Por qué:** el feed del auto-updater se queda en GitHub Releases (decisión del autor). Eso solo es
seguro si la superficie de takedown (las fuentes) **no comparte repo con el feed**. Si el índice
viviera en el repo de la app, un takedown no rompería una descarga: dejaría sin auto-update a toda la
base instalada, de forma permanente y sin canal para avisarles. Precedente propio: v0.2.1 y v0.2.2 ya
dan 404. Con los repos separados, el desacople que pedía el research se consigue por el otro extremo,
y sin tocar el updater.

**Restricción dura:** `nyanko-extensions` nunca se fusiona con el repo de la app, ni el índice se
sirve desde él.

### D-3 — El bundle es código, y por tanto la confianza es explícita

Formato de extensión: módulo Python descargado en runtime, con `sha256` fijado en el índice. No
declarativo: para que la comunidad pueda portar extensiones de Mihon hace falta código real (lógica
de descifrado de imágenes, Cloudflare, etc. no se expresan en JSON).

**Consecuencia que no se puede omitir:** en Mihon el APK lo instala **Android**, que verifica la firma
y le pide permiso al usuario. Nyanko no tiene esa puerta — un módulo Python que el sidecar importa es
ejecución de código arbitrario con los permisos del usuario. Por tanto se porta también el gate que
Mihon sí tiene: **una extensión no confiada no se carga** hasta que el usuario acepta su huella
explícitamente. Sin ese gate, un repo pegado en un foro es RCE.

### D-4 — Portar una extensión de Mihon es reescribirla a mano

Las extensiones de Mihon son Kotlin compilado a APK. **No hay conversión, ni parcial.** «Portar el
repo de keiyoushi» no existe como operación: existe reescribir fuentes una a una. v0.3 estrena 2-3
propias; el formato queda público para que la comunidad añada más.

**Quién las escribe:** el autor, a mano, en `nyanko-extensions`, **fuera del flujo GSD**. Ningún
ejecutor escribe adapters de catálogos reales. Lo que la app tiene que entregar es el *camino* hasta
una fuente instalada (ON-01) y el contrato contra el que se escriben (SRC-04..07).

---

## v0.3 Requirements

### Fundaciones (FND) — antes de que nada escriba una fila

- [x] **FND-01**: El limitador de peticiones respeta el presupuesto real del proveedor — lee
      `X-RateLimit-Limit` de la respuesta en vez de hardcodear un número (AniList: 90/min normal,
      30/min es un estado degradado *temporal*; hardcodear cualquiera de los dos está mal).

- [x] **FND-02**: El limitador limita de verdad — suelta el semáforo *antes* de dormir el intervalo,
      en vez de retenerlo durante la espera (hoy `value=90` admite 90 peticiones simultáneas sin
      ritmo alguno).

- [x] **FND-03**: El limitador es seguro entre bucles de eventos — semáforo por *event loop*, como
      `_clients` ya hace. Hoy es un singleton compartido entre el loop de uvicorn y el de
      `MutationWorker`; sobrevive solo porque nunca contiende.

- [x] **FND-04**: El modelo de progreso está escrito y es a prueba de decimales — número de capítulo
      `REAL` en local, `floor()` al enviarlo al proveedor, guarda monotónica contra el valor *del
      tracker*, y `progress_before` grabado en cada sync.

- [ ] **FND-05**: Nada que contenga host o puerto se persiste jamás — solo rutas relativas o IDs
      opacos, resueltos al renderizar. Con test de guardia que falla si alguna columna persistida
      empieza por `http`.

- [x] **FND-06**: La migración de esquema se ejercita contra una **copia de la base de datos real**
      (`integrity_check` + recuento de filas), no contra un fixture.

> FND-01/02/03 son la deuda D-I-03 de 0.2, **promovida de limpieza a prerrequisito**: son tres bugs,
> no uno, y arreglar solo el número (90→30) es lo que *arma* los otros dos.

### Motor de fuentes (SRC)

- [ ] **SRC-01**: El usuario puede añadir la URL de un repo de extensiones y ver las fuentes que trae.
- [ ] **SRC-02**: El usuario puede instalar, actualizar y desinstalar una fuente desde un repo añadido.
- [ ] **SRC-03**: Una extensión sin confiar **no se carga**: se muestra su huella y el usuario la
      acepta explícitamente antes de que su código llegue a ejecutarse (D-3).

- [ ] **SRC-04**: Una fuente rota o maliciosa no tumba el sidecar — versión de API comprobada al
      registrar, y una fuente rechazada se reporta en la UI en vez de reventar el arranque.

- [ ] **SRC-05**: Cada fuente declara los headers (`Referer`/UA) que su CDN exige, **como dato**, para
      que el fetcher siga siendo genérico y el conocimiento de la fuente no se filtre fuera de ella.

- [ ] **SRC-06**: El presupuesto de peticiones lo posee el motor, **no sus llamadores** — el prefetch
      del reader y la cola de descargas beben del *mismo* cubo (dos limitadores individualmente
      correctos dan el doble de ritmo y un baneo de IP).

- [ ] **SRC-07**: Un parseo que encuentra 0 resultados **falla**, nunca devuelve lista vacía — y un
      fallo nunca pisa una lista de capítulos buena ya cacheada (así es como una página de reto de
      Cloudflare, que responde HTTP 200, se convierte en «este capítulo tiene 0 páginas» y se cachea).

### Reader (RD)

- [ ] **RD-01**: El usuario lee CBZ / ZIP / carpeta de imágenes de su disco, con **orden natural**
      (`2.jpg` antes que `10.jpg` — el bug nº1 de los lectores locales).

- [ ] **RD-02**: Modos de lectura: paginado RTL (el defecto del manga), paginado LTR, y continuo
      vertical / webtoon.

- [ ] **RD-03**: El modo de lectura se recuerda **por serie** (una biblioteca tiene manga y webtoon a
      la vez; retrofittearlo obliga a adivinar el defecto de los usuarios existentes).

- [ ] **RD-04**: Navegación de escritorio: teclado (←/→, AvPág/RePág, Espacio, Inicio/Fin), rueda,
      zonas de click, pantalla completa, contador de página, modos de ajuste, zoom y paneo.

- [ ] **RD-05**: El usuario reanuda un capítulo por la página donde lo dejó.
- [ ] **RD-06**: Encadenado siguiente/anterior capítulo con pantalla de transición — **aquí es donde
      nace el evento «capítulo terminado»**.

- [ ] **RD-07**: Doble página con offset manual ajustable.
- [ ] **RD-08**: Si el CBZ trae `ComicInfo.xml`, se usan sus metadatos en vez de adivinar el número de
      capítulo desde el nombre del fichero.

- [ ] **RD-09**: La memoria del reader tiene techo — ventana de decodificación acotada, con un número
      de RSS en los criterios de aceptación (una página es un JPEG de 200 KB en disco y un bitmap de
      24 MB en RAM).

### Identidad y vínculo (LNK)

- [ ] **LNK-01**: El vínculo fuente↔entrada del tracker es **explícito, almacenado y confirmado por el
      usuario** — nunca calculado en el momento del sync.

- [ ] **LNK-02**: `matcher.py` **propone** el vínculo con un score de confianza; el usuario confirma.
- [ ] **LNK-03**: El reconocimiento de número de capítulo es un componente propio, puro y testeable
      (`extra` = .99, `omake` = .98, `12a` → 12.1) — con su tabla de casos escrita *antes* que el código.

- [ ] **LNK-04**: El sync **falla cerrado** si no hay vínculo confirmado. Nunca escribe a ciegas.

> Este es el peor fallo posible del milestone y se trata como corrupción de datos, no como UX: leo el
> capítulo 12 de la serie A → el matcher difuso lo vincula a la serie B → la app escribe progreso en
> la serie B de mi AniList real → `pending_mutations` lo **reintenta de forma duradera** → no hay
> deshacer, porque nadie se enteró de nada. Un 5% de fallo es invisible en una demo y devastador en
> una lista de 2.761 entradas.

### Sync de progreso (SYN)

- [ ] **SYN-01**: Al llegar a la última página de un capítulo, el progreso sube solo al proveedor
      (AniList/MAL/Kitsu) — la regla de Mihon, literal.

- [ ] **SYN-02**: Se propone, se confirma y se puede deshacer — el mismo trato que la detección de
      reproducción ya da al anime, y la lectura aparece en el timeline de actividad.

- [ ] **SYN-03**: Sync de una sola dirección (Nyanko → tracker). Nunca bidireccional.
- [ ] **SYN-04**: Releer se detecta: si la entrada está `COMPLETED` y el capítulo es menor que el
      progreso, se ofrece `REPEATING` — jamás se empuja un `1` encima de una serie terminada.

- [ ] **SYN-05**: El sync reutiliza la cola de mutaciones existente (`enqueue_mutation` →
      `MutationWorker`), lo que da sync-al-reconectar e inmunidad a ráfagas **gratis**. No se
      construye un segundo camino de sync.

### Fuentes online (ON)

- [ ] **ON-01**: El camino app→fuente funciona contra cualquier adapter que cumpla el contrato: se
      instala por el flujo de SRC-01/02/03 y queda utilizable **sin tocar código de la app**. Los
      adapters de catálogos reales los **escribe el autor a mano** en el repo separado
      `nyanko-extensions` (D-2, D-4) — están **fuera del scope de GSD**; un ejecutor no los escribe. La
      fase sí produce una fuente de conformidad (fixture local) contra la que testear el camino sin
      depender de un sitio vivo.

- [ ] **ON-02**: El usuario busca, explora (popular / recientes) y abre una serie de una fuente online.
- [ ] **ON-03**: Lista de capítulos con número, **scanlator**, idioma, fecha de subida, estado de
      lectura y estado de descarga — más ordenar/filtrar y «marcar anteriores como leídos».

- [ ] **ON-04**: Lectura online con prefetch **acotado** (±2-3 páginas, nunca «el capítulo entero»).
- [ ] **ON-05**: Ninguna petición sale nunca del renderer — todo byte de página va renderer → sidecar →
      fuente. Verificado **en build empaquetado**, no en dev (en dev el renderer tiene origen real; en
      producción es `file://` y las mismas peticiones se rompen — un reader perfecto durante todo el
      desarrollo devuelve un muro de imágenes rotas el día que se empaqueta).

### Descargas (DL)

- [ ] **DL-01**: El usuario encola capítulos, y pausa / reanuda / cancela la cola.
- [ ] **DL-02**: **Serie por fuente, paralelo entre fuentes** — restricción dura para no comerse un
      baneo de IP, no una perilla de ajuste.

- [ ] **DL-03**: Lo descargado se lee **igual que lo local** — mismo pipe, mismo endpoint, mismo
      código (no es una feature: es la ausencia de una).

- [ ] **DL-04**: Una descarga sobrevive a un cierre brusco — `.part` + rename atómico, y
      reconciliación al arrancar (cualquier fila en `downloading` al inicio se resetea). Un capítulo a
      medias **nunca** parece legible.

- [ ] **DL-05**: Las URLs de página se resuelven **al descargar, no al encolar** (las URLs firmadas
      caducan: un capítulo que espera 20 minutos en cola descarga 404s).

- [ ] **DL-06**: El updater avisa y reanuda en vez de destruir — «3 capítulos descargando; seguirán
      tras la actualización» (`killSidecar()` es `taskkill /T /F`: cero oportunidad de vaciar buffers).

### AnimeThemes (AT)

- [ ] **AT-01**: Las cards listan sus openings/endings y se pueden reproducir desde la card.
- [ ] **AT-02**: Búsqueda **por ID directo** (AniList/MAL/Kitsu ya están en `external_identities`) —
      cero matching difuso.

- [ ] **AT-03**: Se respetan las banderas `spoiler` y `nsfw` que la API devuelve.

### Deuda de 0.2 (DBT)

- [ ] **DBT-01**: W-3 — el tray refleja el estado real cuando la detección se pausa desde la UI.
- [ ] **DBT-02**: `RELEASING.md` deja de vivir solo en la máquina del autor (`docs/extra/` está
      gitignorado).

- [ ] **DBT-03**: Auditoría de costuras entre fases antes de cerrar el milestone.

> DBT-03 no es sobrecoste: es **el único control que funcionó**. El audit cruzado de 0.2 es lo único
> que encontró B-1 — y lo encontró *después* de que todas las fases hubieran pasado su verificación.
> D-I-03 **no está aquí**: se movió a Fundaciones, que es donde debe estar.

---

## Future Requirements (v0.3.x / v0.4+)

- **CBR / RAR** — es una decisión de *licencia* (la cláusula de unRAR, o meter `archive.dll` por
  PyInstaller), no técnica. De momento: detectar la extensión y decir «conviértelo a CBZ». Se escala
  como ítem propio y con presupuesto para `THIRD-PARTY-NOTICES`, no se cuela dentro de una fase del
  reader.

- EPUB / PDF (es otro renderizador entero).
- Playlists de temas, mini-reproductor que sobrevive a la navegación.
- Upscaling con IA, auto-división de páginas anchas.
- Firma pública externa + página «Verify» (minisign/cosign) — heredado de 0.2.
- Rediseño de la pantalla de extensión — heredado de 0.2.
- Navegador embebido / webviews — heredado de 0.2.
- Code-signing del instalador Windows — heredado de 0.2.

## Out of Scope (exclusiones explícitas, con motivo)

- **Umbral de «% leído» para marcar completado** — ambiguo, genera falsos positivos y por tanto
  *corrompe el tracker*; y en tira larga el % no significa nada. El evento es «última página», punto.

- **Sync bidireccional** — obliga a resolver conflictos en cada capítulo de cada manga.
- **Progreso por página al tracker** — los trackers físicamente no pueden guardarlo (`$progress: Int!`).
- **Descargas en paralelo dentro de una misma fuente** — la forma más rápida de que a todos los
  usuarios les baneen la IP.

- **Copiar la pantalla de ajustes móvil de Mihon** (teclas de volumen, bloqueo de rotación) — cargo cult.
- **Catálogo propio precargado** — ver D-1. Es la línea que mató a Tachiyomi.

---

## Traceability

**48/48 requisitos mapeados. Cero huérfanos, cero duplicados.**

| REQ | Phase | Status |
|-----|-------|--------|
| FND-01 | Fase 1 — Fundaciones | Complete |
| FND-02 | Fase 1 — Fundaciones | Complete |
| FND-03 | Fase 1 — Fundaciones | Complete |
| FND-04 | Fase 1 — Fundaciones | Complete |
| FND-05 | Fase 1 — Fundaciones | Pending |
| FND-06 | Fase 1 — Fundaciones | Complete |
| SRC-01 | Fase 6 — Distribución de extensiones | Pending |
| SRC-02 | Fase 6 — Distribución de extensiones | Pending |
| SRC-03 | Fase 6 — Distribución de extensiones | Pending |
| SRC-04 | Fase 2 — Motor de fuentes (contrato) | Pending |
| SRC-05 | Fase 2 — Motor de fuentes (contrato) | Pending |
| SRC-06 | Fase 2 — Motor de fuentes (contrato) | Pending |
| SRC-07 | Fase 2 — Motor de fuentes (contrato) | Pending |
| RD-01 | Fase 3 — Page pipe + lectura local | Pending |
| RD-02 | Fase 3 — Page pipe + lectura local | Pending |
| RD-03 | Fase 3 — Page pipe + lectura local | Pending |
| RD-04 | Fase 3 — Page pipe + lectura local | Pending |
| RD-05 | Fase 3 — Page pipe + lectura local | Pending |
| RD-06 | Fase 3 — Page pipe + lectura local | Pending |
| RD-07 | Fase 3 — Page pipe + lectura local | Pending |
| RD-08 | Fase 3 — Page pipe + lectura local | Pending |
| RD-09 | Fase 3 — Page pipe + lectura local | Pending |
| LNK-01 | Fase 4 — Identidad y vínculo | Pending |
| LNK-02 | Fase 4 — Identidad y vínculo | Pending |
| LNK-03 | Fase 4 — Identidad y vínculo | Pending |
| LNK-04 | Fase 4 — Identidad y vínculo | Pending |
| SYN-01 | Fase 5 — Sync de progreso | Pending |
| SYN-02 | Fase 5 — Sync de progreso | Pending |
| SYN-03 | Fase 5 — Sync de progreso | Pending |
| SYN-04 | Fase 5 — Sync de progreso | Pending |
| SYN-05 | Fase 5 — Sync de progreso | Pending |
| ON-01 | Fase 7 — Fuentes online | Pending |
| ON-02 | Fase 7 — Fuentes online | Pending |
| ON-03 | Fase 7 — Fuentes online | Pending |
| ON-04 | Fase 7 — Fuentes online | Pending |
| ON-05 | Fase 7 — Fuentes online | Pending |
| DL-01 | Fase 8 — Cola de descargas | Pending |
| DL-02 | Fase 8 — Cola de descargas | Pending |
| DL-03 | Fase 8 — Cola de descargas | Pending |
| DL-04 | Fase 8 — Cola de descargas | Pending |
| DL-05 | Fase 8 — Cola de descargas | Pending |
| DL-06 | Fase 8 — Cola de descargas | Pending |
| AT-01 | Fase 9 — AnimeThemes + deuda + audit | Pending |
| AT-02 | Fase 9 — AnimeThemes + deuda + audit | Pending |
| AT-03 | Fase 9 — AnimeThemes + deuda + audit | Pending |
| DBT-01 | Fase 9 — AnimeThemes + deuda + audit | Pending |
| DBT-02 | Fase 9 — AnimeThemes + deuda + audit | Pending |
| DBT-03 | Fase 9 — AnimeThemes + deuda + audit | Pending |
