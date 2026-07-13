# Phase 2: Motor de fuentes — contrato, presupuesto y taxonomía de errores - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-13
**Phase:** 2 — Motor de fuentes — contrato, presupuesto y taxonomía de errores
**Areas discussed:** Superficie del contrato, Dueño del cubo, Errores + caché, Registro y rechazo

---

## Superficie del contrato

### ¿Cuántas cosas puede pedirle la app a una fuente en la v1 del contrato?

| Opción | Descripción | Elegida |
|--------|-------------|---------|
| Lo mínimo para leer | `search` / `chapters` / `pages` + capacidades declaradas por fuente | ✓ |
| Copiar a Mihon | + populares, novedades, ficha de serie | |
| Todavía menos | Solo `chapters` + `pages`; `search` llega en la Fase 7 | |

**Notas:** El contrato vive contra un repo de fuentes externo (`nyanko-extensions`, D-2): quitar
métodos mañana es gratis, añadirlos sube `SOURCE_API_VERSION` y expulsa a las fuentes ya escritas. Se
elige el mínimo a sabiendas de ese coste, porque hoy el autor escribe todas las fuentes.

### ¿Con qué fuente se estrena el test de conformidad, si hoy no hay ninguna?

| Opción | Descripción | Elegida |
|--------|-------------|---------|
| Fuente local mínima aquí | `LocalArchiveSource` lista capítulos de una carpeta + qué imágenes tiene cada uno | ✓ |
| Fuente falsa de test | Una fuente inventada que solo existe en los tests | |
| Fuente local completa | CBZ + orden natural + `ComicInfo.xml` ya en esta fase | |

**Notas:** Leer/ordenar/`ComicInfo.xml` es la Fase 3. Una fuente falsa solo demostraría que el contrato
es coherente consigo mismo.

### ¿Qué forma tienen los datos que devuelve una fuente?

| Opción | Descripción | Elegida |
|--------|-------------|---------|
| Tipos propios del motor | Serie/capítulo/página de fuente, separados del tracker | ✓ |
| Reusar los tipos del tracker | Los Pydantic de `models.py` | |
| Datos sueltos | Dicts sin forma fija | |

**Notas:** Una serie de una fuente no es una entrada de AniList. Confundirlas es el desastre que la
Fase 4 existe para prevenir; tipos separados lo hacen imposible de escribir por accidente.

### ¿Cómo se persiste «qué serie de qué fuente»?

| Opción | Descripción | Elegida |
|--------|-------------|---------|
| Identificador opaco | La fuente da un id suyo; la app nunca ve URLs | ✓ |
| Trozo de ruta relativa | `/manga/berserk`, estilo Mihon | |
| URL completa | `https://sitio/manga/berserk` | |

**Notas:** La guardia FND-05 de la Fase 1 prohíbe persistir URLs (este proyecto ya perdió todas las
portadas por eso). El id opaco además sobrevive a un cambio de dominio.

---

## Dueño del cubo (presupuesto de peticiones)

### ¿Cuál es la unidad con presupuesto propio?

| Opción | Descripción | Elegida |
|--------|-------------|---------|
| Uno por fuente | El motor crea el cubo al registrar; todos sus consumidores beben de él | ✓ |
| Uno por fuente, partido en dos | API/HTML por un lado, imágenes por otro | |
| Uno por dominio | El cubo va por servidor, no por fuente | |

**Notas:** El criterio 4 habla de dos consumidores de *la misma fuente*. El cubo por dominio es más
fiel a la realidad (quien banea es el host) pero deja sin dueño el presupuesto de un CDN compartido.

### ¿Cómo se impide que una fuente se salte el cubo?

| Opción | Descripción | Elegida |
|--------|-------------|---------|
| Se lo damos + test que lo caza | Fetcher inyectado + test que falla si la fuente importa red por su cuenta | ✓ |
| Solo se lo damos | Inyección y confianza | |
| Bloqueo real al cargar | Impedir técnicamente el import de red | |

**Notas:** El bloqueo real es el trust gate de la Fase 6 (código de terceros). La inyección sola es
ciega: una fuente con su propia librería de red pasaría los tests y duplicaría el ritmo en producción.

### ¿Quién pone el número del presupuesto?

| Opción | Descripción | Elegida |
|--------|-------------|---------|
| Lo declara la fuente, con techo | La fuente pide su ritmo; el motor lo recorta | ✓ |
| Lo declara la fuente, sin techo | La fuente manda | |
| Un ritmo único para todas | El motor fija el mismo límite | |

**Notas:** Misma lógica que la Fase 1 dejó en el limitador (el número declarado es petición, no orden).
Protege del día en que una fuente de terceros declare 600/min.

### Reader y descargas compiten por el mismo cubo lleno: ¿quién espera?

| Opción | Descripción | Elegida |
|--------|-------------|---------|
| Manda la lectura | Prioridad en la petición; la descarga usa lo que sobra | ✓ |
| El que llegue primero | FIFO | |
| Cuota reservada | La descarga nunca pasa de X% del presupuesto | |

**Notas:** El usuario ve congelarse la lectura, no ve ir despacio la descarga. Decidirlo ahora es
gratis; en la Fase 8 obliga a volver a tocar el motor — que es justo la costura que esta fase mete
dentro (Seam F).

---

## Errores + caché

### ¿Cómo se entera el motor de QUÉ ha fallado?

| Opción | Descripción | Elegida |
|--------|-------------|---------|
| Una familia de errores | Base + hijos: red / parseo / rate limit / no existe / no soportado | ✓ |
| Un error con etiqueta | Un tipo con un campo `kind` | |
| Lo que salga | Excepciones de las librerías que use la fuente | |

**Notas:** Es lo único que permite reintentar la red y NO reintentar un parseo roto.

### ¿Quién reintenta?

| Opción | Descripción | Elegida |
|--------|-------------|---------|
| Reintenta el motor | La fuente nunca reintenta; el parseo nunca se reintenta | ✓ |
| Reintenta la fuente | Cada fuente conoce su sitio | |
| Nadie reintenta aún | Todo fallo sube tal cual | |

**Notas:** `retry_with_backoff` ya existe en `http.py`. Si cada fuente reintenta por su cuenta, los
reintentos no cuentan en el cubo de nadie.

### ¿Dónde vive la lista de capítulos cacheada?

| Opción | Descripción | Elegida |
|--------|-------------|---------|
| En memoria del motor | Última lista buena por serie; un error nunca la pisa | ✓ |
| En la base de datos | Tabla nueva, esquema v9 | |
| Nada, solo la regla | Sin caché en esta fase | |

**Notas:** Cumple el criterio 3 (reto de Cloudflare con HTTP 200 + HTML) sin tocar la BD. Persistirla es
de la Fase 8; la regla —lo irreversible— se escribe y se testea ahora.

### ¿Qué ve el usuario cuando una fuente falla?

| Opción | Descripción | Elegida |
|--------|-------------|---------|
| Mensaje según el tipo | Sin conexión → reintentar; fuente rota → actualizar; limitado → esperar | ✓ |
| Un mensaje genérico | «Error al cargar desde esta fuente» | |
| Nada de UI todavía | Solo log | |

---

## Registro y rechazo

### ¿Cómo se compara `SOURCE_API_VERSION`?

| Opción | Descripción | Elegida |
|--------|-------------|---------|
| Número exacto | La app habla la 1; cualquier otra cosa se rechaza | ✓ |
| Rango de compatibilidad | «Acepto de la 1 a la 3» | |
| Mayor.menor | Estilo semver | |

**Notas:** Coste asumido: subir la versión expulsa a todas las fuentes hasta que su autor las
actualice. Hoy es barato porque el autor las escribe todas.

### ¿Qué queda de una fuente rechazada?

| Opción | Descripción | Elegida |
|--------|-------------|---------|
| Sigue en la lista, marcada | Con su motivo (versión incompatible / reventó al cargar) | ✓ |
| Solo al log | Desaparece de la UI | |
| Aviso al arrancar | Notificación al abrir la app | |

**Notas:** Una fuente que desaparece en silencio es la queja que la Fase 6 va a recibir. El sidecar
arranca igual (SRC-04).

### ¿El registro se monta al arrancar o admite altas en caliente?

| Opción | Descripción | Elegida |
|--------|-------------|---------|
| Se monta al arrancar, y se rehace entero | Imports explícitos; instalar una fuente reconstruye la lista | ✓ |
| Altas y bajas en caliente | `register`/`unregister` individuales | |
| Estricto: solo al arrancar | Instalar una fuente exigiría reiniciar | |

**Notas:** Jamás `pkgutil`/`importlib` (criterio 6: en el build frozen encuentra cero). Precedente vivo:
`detectors/__init__.py`.

### ¿El motor desactiva sola una fuente que falla siempre?

| Opción | Descripción | Elegida |
|--------|-------------|---------|
| No, todavía no | Se reporta el error; decide el usuario | ✓ |
| Sí, tras varios fallos seguidos | Circuit breaker | |

**Notas:** No hay ni una fuente online contra la que calibrar el umbral. Se reconsidera en la Fase 7.

---

## Claude's Discretion

- Nombres de tipos, clases de error y layout de módulos (`sources/` package vs módulo plano).
- Valor del techo global de peticiones/minuto y del `max_concurrency` por fuente.
- Cómo se expone al renderer la lista de fuentes con estado (endpoint nuevo vs ampliar uno existente).
- Mecanismo del test de guardia contra imports de red en fuentes (AST vs grep).

## Deferred Ideas

- Persistir la caché de capítulos en SQLite (esquema v9) → **Fase 8** (lectura offline).
- Desactivación automática de fuentes rotas (circuit breaker) → **Fase 7**.
- Partir el cubo en dos (API vs CDN de imágenes) → **Fase 3/7**, si las ráfagas de páginas ahogan el listado.
- Bloqueo real de imports de red en código de fuente → **Fase 6** (trust gate).
- Ampliar el contrato (populares / novedades / ficha) → **Fase 7**, subiendo `SOURCE_API_VERSION`.
