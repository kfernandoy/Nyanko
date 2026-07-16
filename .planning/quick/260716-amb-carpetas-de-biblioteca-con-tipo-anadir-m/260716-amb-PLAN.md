---
phase: quick-260716-amb
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - apps/backend/tests/test_database.py
  - apps/backend/tests/test_scanner.py
  - apps/backend/tests/test_sources.py
  - apps/backend/tests/test_reader_persistence.py
  - apps/backend/nyanko_api/database.py
  - apps/backend/nyanko_api/scanner.py
  - apps/backend/nyanko_api/sources/local_archive.py
  - apps/backend/nyanko_api/models.py
  - apps/backend/nyanko_api/main.py
  - apps/desktop/src/types.ts
  - apps/desktop/src/api.ts
  - apps/desktop/src/LibrarySettingsView.tsx
  - apps/desktop/src/i18n.tsx
autonomous: true
requirements: [UAT-03-02]

must_haves:
  truths:
    - Una BD v9 con carpetas ya añadidas migra a v10 y esas carpetas quedan `ambas` — su comportamiento de HOY no cambia
    - Una carpeta `manga` NO aparece en el escaneo de anime (`iter_video_files`) ni en la firma del `LibraryWatcher`
    - Una carpeta `anime` NO aparece en las raíces de `LocalArchiveSource`
    - Una carpeta `ambas` sigue apareciendo en LOS DOS mundos
    - `GET /api/library/folders` sigue devolviendo TODAS las carpetas, del tipo que sean
    - Cambiar «incluir subcarpetas» de una carpeta NO le resetea el tipo
    - `POST /api/library/folders` sin `kind` sigue funcionando y crea una carpeta `ambas`
    - Suite verde desde `apps/backend` (baseline 455 + los tests nuevos)
  artifacts:
    - apps/backend/nyanko_api/database.py (columna `kind`, `CANONICAL_SCHEMA_VERSION` 10)
    - apps/backend/nyanko_api/scanner.py (`iter_video_files` filtra a anime+ambas)
    - apps/backend/nyanko_api/sources/local_archive.py (`_load_roots` filtra a manga+ambas)
    - apps/backend/tests/test_database.py (migración v9→v10 — RED antes del arreglo)
    - apps/desktop/src/LibrarySettingsView.tsx (selector de tipo al añadir + en la lista)
  key_links:
    - "`iter_video_files()` es el ÚNICO camino al escaneo de anime (main.py:1422 watcher, 2168 scan): el filtro vive ahí, no en los llamantes"
    - "`_load_roots()` es el ÚNICO camino a las raíces de manga (los 3 `build_source_registry` → `_instantiate_source` → aquí): el filtro vive ahí"
    - "`get_library_folders()` NO filtra: la lista y el lookup por id (main.py:2104, 2112) tienen que ver todas las carpetas"
    - "`kind` ausente ⇒ `ambas` en los dos filtros: es lo que mantiene verdes los fixtures que pasan carpetas sin tipo, y es el mismo criterio de la migración"
---

<objective>
Hallazgo #2 del UAT de la fase 03: **añadir una carpeta de manga dispara el escaneo de anime.** Una sola
tabla `library_folders(id, path, recursive)` sin columna de tipo, consumida por los dos mundos.

Se añade `kind` (`anime` / `manga` / `ambas`) a la tabla EXISTENTE, se migra a v10 dejando las carpetas
ya añadidas como `ambas`, y se filtra en los **dos consumidores** — no en la query, no en los llamantes.

Purpose: que una carpeta de manga deje de mover el escáner de vídeo, sin cambiarle el comportamiento a
la biblioteca de producción que ya existe.
Output: esquema v10, filtro en `iter_video_files` y `_load_roots`, `kind` en la API y en la UI (ES+EN).
</objective>

<execution_context>
@.planning/CODEX-RULES.md
</execution_context>

<context>
@.planning/STATE.md
@.claude/CLAUDE.md

@apps/backend/nyanko_api/database.py
@apps/backend/nyanko_api/scanner.py
@apps/backend/nyanko_api/sources/local_archive.py
@apps/desktop/src/LibrarySettingsView.tsx
</context>

<design_notes>

## Dónde va el filtro — y por qué NO en la query ni en los llamantes

`get_library_folders()` tiene **6 llamantes**, en tres grupos:

| Llamante | Mundo | Necesita |
|----------|-------|----------|
| `main.py:1422` `LibraryWatcher._compute_signature` → `iter_video_files(...)` | anime | anime + ambas |
| `main.py:2168` `run_library_scan` → `iter_video_files(folders)` | anime | anime + ambas |
| `main.py:1480` `lifespan` → `build_source_registry(...)` | manga | manga + ambas |
| `main.py:2141` alta de carpeta → `build_source_registry(...)` | manga | manga + ambas |
| `main.py:2157` baja de carpeta → `build_source_registry(...)` | manga | manga + ambas |
| `main.py:2104` `list_library_folders` | API | **TODAS** |
| `main.py:2112` `list_library_subfolders` (busca por id) | API | **TODAS** |

- **En la query, NO**: los dos últimos tienen que ver todas las carpetas. Filtrar ahí rompe la lista de
  Ajustes y el lookup por id. Haría falta un parámetro `kind` y tocar los 6 llamantes.
- **En los llamantes, NO**: son 5 sitios a tocar, y el **sexto llamante que se añada mañana reintroduce
  el bug en silencio**. Es exactamente el invariante-con-N-escritores contra el que ya avisa el comentario
  de `main.py:1101`, y la lección que STATE.md tiene escrita de la Fase 01: *«un invariante mantenido en
  cuatro sitios se rompe, uno derivado al leer no»*.
- **En los dos consumidores, SÍ**: los 2 caminos de anime pasan TODOS por `iter_video_files()`; los 3 de
  manga pasan TODOS por `build_source_registry()` → `_instantiate_source()` → `LocalArchiveSource._load_roots()`.
  **2 funciones, 0 llamantes tocados**, y un llamante nuevo hereda el filtro por construcción. Falla cerrado.

Los dos son un bucle sobre `folders` con `folder.get(...)`: el filtro es una guarda de 2 líneas en cada uno.

## Los dos defaults — mismo valor, razones distintas

El plan los decide por separado, como pide el encargo, y **coinciden en `ambas`**:

- **Valor de la MIGRACIÓN (filas existentes) = `ambas`** — preservación de datos. Esas carpetas HOY sirven
  para las dos cosas; dejarlas en `anime` o `manga` le cambiaría el comportamiento a una biblioteca de
  producción por una migración. Es el Core Value de CLAUDE.md («misma biblioteca, mismos datos») y sería
  pérdida de datos silenciosa.
- **DEFAULT de la COLUMNA (filas nuevas) = `ambas`** — compatibilidad de escritores. La UI siempre mandará
  un `kind`, así que el default solo salta para quien no lo mande: un renderer viejo contra un sidecar nuevo
  durante una actualización, o un INSERT a pelo (`test_persisted_urls.py:247`). Fallar a `ambas` = el
  comportamiento de hoy: la carpeta se escanea de más (molesto, inofensivo). Fallar a `anime` o `manga` = la
  carpeta se vuelve invisible para un mundo **en silencio** — que es justo el bug que se está arreglando.
  `ambas` es el que falla seguro.

Que coincidan es lo que permite que **una sola línea** haga las dos cosas: en SQLite,
`ALTER TABLE ... ADD COLUMN kind TEXT NOT NULL DEFAULT 'ambas'` **rellena las filas existentes con el
default**. No hace falta ninguna función `_migrate_*` nueva ni un `UPDATE` de backfill.

El precedente exacto ya está en el fichero, **misma forma y misma columna**:
`database.py:380` → `self._add_column(connection, "torrent_sources", "kind", "TEXT NOT NULL DEFAULT 'release'")`.
`_add_column` (l.529) ya es idempotente por introspección de `PRAGMA table_info`. Es el patrón aditivo del v8
(`chapter_progress`). **No inventes un mecanismo nuevo.**

## El campo de minas del bump de versión

Subir `CANONICAL_SCHEMA_VERSION` 9→10 **rompe 7 aserciones ya verdes** en 2 ficheros. No son bugs: son pines
de la versión y del nombre del backup, que lleva la versión DESTINO dentro (`_backup_before_migration`, l.610).
**Van en el MISMO commit que el bump** (Tarea 2), o la suite se queda roja:

| Fichero | Línea | Hoy | Debe quedar |
|---------|-------|-----|-------------|
| `test_database.py` | 81 | `assert version == 9` | `== 10` |
| `test_database.py` | 1039 | `def test_canonical_schema_version_is_9():` | renombrar a `_is_10` |
| `test_database.py` | 1042 | `assert CANONICAL_SCHEMA_VERSION == 9` | `== 10` |
| `test_database.py` | 1089 | `assert version == 9` | `== 10` |
| `test_database.py` | 1095 | `glob("nyanko.backup-v9-*.sqlite3")` | `backup-v10-*` |
| `test_reader_persistence.py` | 180 | `... fetchone()[0] == 9` | `== 10` |
| `test_reader_persistence.py` | 183 | `glob("nyanko.backup-v9-*.sqlite3")` | `backup-v10-*` |

## La trampa de la UI: el upsert que borra el tipo

`add_library_folder` es un **upsert** (`ON CONFLICT(path) DO UPDATE SET recursive = excluded.recursive`), y
`LibrarySettingsView.tsx:50` lo reutiliza para el checkbox de subcarpetas:
`api.addLibraryFolder(folder.path, !folder.recursive)`.

Si el upsert pasa a escribir también `kind = excluded.kind`, **tocar «incluir subcarpetas» le resetearía el
tipo a la carpeta**. `toggleRecursive` TIENE que pasar `folder.kind`. Hay un must-have para esto.

## Lo que NO se toca

- El reader: los hallazgos #3/#4/#5 del UAT van en sus propias tareas.
- `conftest.py`, `pyproject.toml`, `pytest.ini` (CODEX-RULES regla 3).
- Sin dependencias nuevas.
- Sin `CHECK` en la columna: el único escritor es `add_library_folder`, y `LibraryFolderCreate` ya valida el
  vocabulario con un `Literal` de pydantic (422 para un tipo inventado) en la frontera de confianza. Mantener
  el `CREATE TABLE` y el `_add_column` con la MISMA definición de columna, sin divergir.
- `assert_no_persisted_urls` (FND-05) no se ve afectada: `kind` guarda `anime`/`manga`/`ambas`, nunca una URL.
  La guarda es sobre DATOS y pasa sola. No la toques.

</design_notes>

<tasks>

<task type="auto">
  <name>Tarea 1: Los tests que fallan HOY (RED) — la migración primero</name>
  <files>apps/backend/tests/test_database.py, apps/backend/tests/test_scanner.py, apps/backend/tests/test_sources.py</files>
  <action>
    Escribir SOLO tests. Ni una línea de arreglo — esta tarea tiene que dejar la suite ROJA a propósito;
    el orquestador ejecuta y comprueba el RED antes de que empiece la Tarea 2.

    **`test_database.py` — el test que importa, el que protege la biblioteca de producción.**
    Añadir junto al bloque de v8 que ya existe (l.1024+), reusando su patrón exacto:
    un helper `_degrade_to_v9(path)` calcado de `_degrade_to_v7` (l.1027) — crea la BD con el esquema real,
    le quita la columna nueva con `ALTER TABLE library_folders DROP COLUMN kind`, borra `schema_migrations`
    e inserta `VALUES (9)`. La razón de calcarlo está en su docstring y sigue valiendo: un fixture escrito a
    mano no comparte el esquema con el de producción. NO le pongas guardas ni condicionales al helper.

    El test (`test_v9_library_folders_migran_a_ambas`, con `tmp_path`): crear BD, degradar a v9, insertar a
    pelo dos carpetas con `INSERT INTO library_folders(path, recursive)`, volver a `Database(path).initialize()`,
    y afirmar que **las dos filas siguen ahí** y que **las dos tienen `kind == 'ambas'`**; que
    `MAX(version)` es 10; que `PRAGMA integrity_check` sale `ok`; y que existe UN backup
    `nyanko.backup-v10-*.sqlite3` (mismo cierre que el test de v7, l.1094).

    Añadir también un test de que una BD NUEVA trae la columna: `PRAGMA table_info(library_folders)` incluye
    `kind`, y una carpeta insertada sin tipo sale `ambas` (cubre el default de la columna, que es una decisión
    distinta de la de la migración).

    **`test_scanner.py`** — `iter_video_files` con tres carpetas (una `anime`, una `manga`, una `ambas`), cada
    una con un fichero de vídeo real dentro (`tmp_path`): devuelve el vídeo de la `anime` y el de la `ambas`,
    y **NO el de la `manga`**. Sigue el patrón de los tests que ya hay en el fichero.

    **`test_sources.py`** — `LocalArchiveSource(library_folders=[...])` con una carpeta `anime` y una `manga`
    (dicts con `id`/`path`/`kind`, como el fixture de l.482): sus raíces contienen la de manga y **NO la de
    anime**. Afirmar sobre el comportamiento observable de las raíces cargadas.

    Añadir además el caso que fija la compatibilidad, en los dos ficheros: una carpeta **sin** clave `kind` se
    acepta en LOS DOS mundos (es el mismo criterio que la migración: tipo desconocido ⇒ `ambas`).
  </action>
  <verify>
    <automated>cd apps/backend && .venv/Scripts/python.exe -m pytest -q tests/test_database.py tests/test_scanner.py tests/test_sources.py</automated>
    Lo ejecuta el ORQUESTADOR (CODEX-RULES regla 2: Codex no puede correr pytest).
    **RED esperado, y hay que MIRARLO, no asumirlo** — en esta fase ya han mordido dos falsos verdes:
    - los tests de `test_scanner.py` / `test_sources.py` fallan por ASERCIÓN (la carpeta prohibida aparece
      en la lista);
    - el de migración falla con `sqlite3.OperationalError: no such column: kind` — hoy la columna no existe,
      así que el `DROP COLUMN` del helper revienta. Es un error, no un assert, y es RED legítimo.
    Un test nuevo que salga VERDE aquí está mal escrito: PARA y dilo.
    El resto de la suite (455) sigue verde: esta tarea todavía no sube la versión.
  </verify>
  <done>Los tests nuevos fallan, cada uno por el motivo de arriba, y el orquestador los commitea EN ROJO (mismo precedente que CR-01, `ea84237`).</done>
</task>

<task type="auto">
  <name>Tarea 2: `kind` en el esquema, migración v10 y filtro en los dos consumidores</name>
  <files>apps/backend/nyanko_api/database.py, apps/backend/nyanko_api/scanner.py, apps/backend/nyanko_api/sources/local_archive.py, apps/backend/nyanko_api/models.py, apps/backend/nyanko_api/main.py, apps/backend/tests/test_database.py, apps/backend/tests/test_reader_persistence.py</files>
  <action>
    **`database.py`** — cuatro cosas, todas siguiendo lo que ya está en el fichero:
    1. `SCHEMA`, `CREATE TABLE ... library_folders` (l.228): añadir `kind TEXT NOT NULL DEFAULT 'ambas'`
       (para BD nuevas; en una existente el `IF NOT EXISTS` no hace nada, de ahí el punto 2).
    2. `initialize()`: añadir un `self._add_column(connection, "library_folders", "kind", "TEXT NOT NULL DEFAULT 'ambas'")`
       junto a los demás (l.375-380). **Definición de columna IDÉNTICA a la del `SCHEMA`.** Esto ES la
       migración completa: SQLite rellena las filas existentes con el default. No escribas ninguna función
       `_migrate_*` nueva ni un `UPDATE` de backfill — no hacen falta y el patrón ya existe en l.380
       (`torrent_sources.kind`, misma forma).
    3. `CANONICAL_SCHEMA_VERSION` (l.308): 9 → 10. Esto es lo que arma el backup previo, que ya hace la clase.
    4. `get_library_folders` (l.755): meter `kind` en el `SELECT` y en el dict. **Sin filtrar** — la lista y el
       lookup por id tienen que seguir viendo todas las carpetas. `add_library_folder` (l.765): parámetro
       `kind: str = "ambas"` (el default mantiene vivos los dos llamantes de `test_main.py:863` y `1675`, que
       pasan posicionales), `kind` en el INSERT, `kind = excluded.kind` en el `ON CONFLICT`, y `kind` en el
       dict de vuelta.

    **`scanner.py`** — en `iter_video_files` (l.22), al principio del bucle: saltar la carpeta si su tipo no
    está entre anime y ambas. Tipo ausente o vacío ⇒ tratar como ambas (`folder.get("kind") or "ambas"`),
    que es lo que mantiene verdes los fixtures que pasan carpetas sin tipo. Actualiza el docstring, que hoy
    dice que cada carpeta es `{"path", "recursive"}`.

    **`sources/local_archive.py`** — en `_load_roots` (l.291), dentro de la rama `isinstance(folder, Mapping)`:
    saltar la carpeta si su tipo no está entre manga y ambas, con el mismo criterio de ausente ⇒ ambas. Las
    carpetas que llegan como `str` no tienen tipo: se aceptan (mismo criterio).

    **`models.py`** — `LibraryFolder` (l.105): `kind: str`. `LibraryFolderCreate` (l.111):
    `kind: Literal["anime", "manga", "ambas"] = "ambas"` — el `Literal` da el 422 gratis en la frontera de
    confianza, y el default mantiene compatible a un cliente que no mande el campo.

    **`main.py`** — `add_library_folder` (l.2137): pasar `body.kind` a `database.add_library_folder`. Una línea.
    **NO toques los 3 sitios de `build_source_registry`** (l.1479, 2140, 2156) ni los 2 de `iter_video_files`
    (l.1422, 2168): el filtro vive en los consumidores, ese es el punto del plan.

    **Los 7 pines de versión** de la tabla de `<design_notes>` (`test_database.py` 81/1039/1042/1089/1095 y
    `test_reader_persistence.py` 180/183): van en ESTE commit. Rompen por el bump, no por un bug.
  </action>
  <verify>
    <automated>cd apps/backend && .venv/Scripts/python.exe -m pytest -q</automated>
    Lo ejecuta el ORQUESTADOR. Verde: baseline **455 passed** + los tests nuevos de la Tarea 1.
    Los tres tests de la Tarea 1 pasan de rojo a verde SIN haberlos tocado.
    Cero fallos en `test_reader_persistence.py` y `test_persisted_urls.py`: la guarda FND-05 sigue verde.
  </verify>
  <done>Una BD v9 con carpetas migra a v10 con esas carpetas en `ambas` y su backup `-v10-` en disco; una carpeta `manga` no la ve el escáner de anime y una `anime` no la ve el registry de manga; `GET /api/library/folders` las sigue devolviendo todas.</done>
</task>

<task type="auto">
  <name>Tarea 3: elegir el tipo al añadir y verlo en la lista (ES + EN)</name>
  <files>apps/desktop/src/types.ts, apps/desktop/src/api.ts, apps/desktop/src/LibrarySettingsView.tsx, apps/desktop/src/i18n.tsx</files>
  <action>
    **`types.ts`** (l.291): `export type LibraryFolderKind = "anime" | "manga" | "ambas";` y `kind: LibraryFolderKind`
    en `LibraryFolder`.

    **`api.ts`** (l.310): `addLibraryFolder(path, recursive, kind: LibraryFolderKind = "ambas")`, con `kind` en el
    body JSON. El default deja el sitio de llamada compatible mientras se edita.

    **`LibrarySettingsView.tsx`** — tres cambios, calcados del checkbox `recursive` que ya está:
    1. Un estado para el tipo de la PRÓXIMA carpeta (`useState<LibraryFolderKind>("ambas")`) y un `<select>`
       nativo junto al botón de añadir; `addFolder` (l.37) pasa ese valor.
    2. En cada fila, otro `<select>` con el `folder.kind` — muestra el tipo y deja corregirlo reusando el mismo
       upsert que ya usa `toggleRecursive` (`api.addLibraryFolder(folder.path, folder.recursive, nuevoKind)`
       + `load()`). Mismo coste que una etiqueta de solo lectura y hace recuperable elegir mal.
    3. **`toggleRecursive` (l.50) tiene que pasar `folder.kind`.** Si no, tocar «incluir subcarpetas» le resetea
       el tipo a la carpeta — ver `<design_notes>`. Es un must-have.
    Las tres opciones salen de una constante local (`["anime", "manga", "ambas"] as const`) recorrida con `.map()`
    en los dos `<select>`; nada de componentes nuevos.

    **`i18n.tsx`** — claves nuevas en LOS DOS bloques, ES (junto a l.224-228) y EN (junto a l.528-532),
    con el estilo plano que ya usan: `libset.kind` («Tipo» / «Type»), `libset.kind.anime` («Anime» / «Anime»),
    `libset.kind.manga` («Manga» / «Manga»), `libset.kind.ambas` («Ambas» / «Both»).
    Las etiquetas se leen con clave dinámica — `t()` es `(key: string) => string` (l.625), así que tsc lo traga.
  </action>
  <verify>
    <automated>npm run check</automated>
    tsc verde. Lo ejecuta el ORQUESTADOR.
  </verify>
  <done>Al añadir una carpeta se elige el tipo; la lista lo muestra; cambiar «incluir subcarpetas» no lo pisa; los textos existen en ES y EN.</done>
</task>

</tasks>

<verification>
1. Suite desde `apps/backend` (`cd apps/backend && .venv/Scripts/python.exe -m pytest -q`; desde la raíz
   falla la recolección): **455 passed** de baseline + los tests nuevos.
2. El RED de la Tarea 1 quedó OBSERVADO antes de la Tarea 2, no asumido, y con el motivo esperado de cada test.
3. `npm run check` verde.
4. `rg -n "get_library_folders" apps/backend/nyanko_api/main.py` sigue mostrando los 6 llamantes **sin
   parámetro de tipo**: el filtro está en los consumidores.
5. UAT manual (usuario): añadir una carpeta de manga NO arranca el escaneo de anime.
</verification>

<success_criteria>
El hallazgo #2 del UAT queda cerrado sin cambiarle el comportamiento a ninguna carpeta ya existente:
migran a `ambas` y siguen sirviendo a los dos mundos, como hoy.
</success_criteria>

<output>
Crear `.planning/quick/260716-amb-carpetas-de-biblioteca-con-tipo-anadir-m/260716-amb-SUMMARY.md` al terminar.
</output>
