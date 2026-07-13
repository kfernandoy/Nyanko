# Modelo de progreso: capítulo decimal en local, entero al proveedor

> Estado: decidido (Fase 1, plan 01-02). La Fase 5 hereda este documento como verdad.

## El problema

`library_entries.progress` es `INTEGER NOT NULL DEFAULT 0`. El capítulo 10.5 no tiene dónde ir.
`episodes.episode_number` ya es `REAL` (`database.py:118`): el proyecto ya sabe guardar números
decimales; es la columna de progreso la que se quedó en entero.

## Decisión: dos números, no uno

| Columna | Tipo | Qué es |
|---------|------|--------|
| `library_entries.progress` | `INTEGER` | Lo que el tracker **tiene o va a tener**. Los proveedores solo aceptan enteros (`$progress: Int!`). |
| `library_entries.chapter_progress` | `REAL` (nuevo, `NULL` para anime) | Lo que el usuario **leyó de verdad**: 10.5. |

`floor()` es la función que va del segundo al primero, y **solo se aplica al cruzar hacia el
proveedor**. Vive en un sitio único: `progress.to_provider(chapter)`.

## Decisión: columna aditiva, NO rebuild de `library_entries`

SQLite no tiene `ALTER COLUMN TYPE`. Cambiar `progress` a `REAL` exige el rebuild de tabla
(rename → create → copy → drop; el único precedente en el árbol es `_migrate_torrent_filters`,
`database.py:507`) sobre 2.774 filas vivas de una biblioteca real e irreemplazable. Y devolvería
`10.0` donde hoy la API devuelve `10`: un cambio de tipo visible desde el renderer, en la ruta que
el manga comparte con el anime, para nada.

**Rechazado.** `ALTER TABLE ADD COLUMN` es aditivo: no reescribe ni una fila existente y, por
construcción, no puede alterar los recuentos por tabla. La migración a v8 es una columna nueva y
nada más.

El backup pre-migración es el único rollback que existe, y se dispara solo: `initialize()` llama a
`_backup_before_migration()` (`database.py:577`) cuando `_requires_canonical_migration()`
(`database.py:562`) ve que la versión aplicada es menor que `CANONICAL_SCHEMA_VERSION`.
**Subir la constante de 7 a 8 es, por sí mismo, lo que arma el backup.**

## Decisión: la guarda monotónica compara contra el TRACKER

El valor de referencia de `progress.next_progress()` es `remote_library_entries.progress` — el
espejo del proveedor —, **no** `library_entries.progress`, que es el local y la UI ya movió de forma
optimista. Comparar contra el local es cómo se empuja un `1` encima de una serie terminada.

Que sea construcción y no convención lo garantiza el lector: `Database.tracker_progress(media_id,
account_id)` lee de `remote_library_entries`. Sin valor conocido del tracker, `next_progress`
devuelve `None`: **falla cerrado**, no escribe a ciegas en la lista real del usuario.

## Decisión: `progress_before` se graba en cada sync

`undo_playback` hace `restored_progress = last_event["progress_before"]` y **lo escribe de vuelta en
el proveedor**. Por eso `progress_before` guarda el valor **que el tracker tenía** — capturado
*antes* de que `update_remote_library_entry` sobrescriba el espejo con el valor nuevo — o no guarda
nada. Un `0` de relleno convertiría el botón de deshacer en «pon a cero mi AniList real».

## La divergencia de la pareja `(progress, chapter_progress)`

`library_entries.progress` **ya tiene cuatro escritores** en el árbol, y ninguno tocará
`chapter_progress`:

| Sitio | Qué es |
|-------|--------|
| `database.py:1231` | `INSERT INTO library_entries(... progress ...)` desde la lista remota (`sync_provider_library`) |
| `database.py:1374` | `INSERT INTO library_entries` desde la lista remota (`sync_provider_library`, rama con fechas) |
| `database.py:2158` | `INSERT INTO library_entries(... progress ...)` en `update_remote_library_entry` |
| `database.py:2639` | `UPDATE library_entries SET progress = ?` en `update_account_progress` — **el sync del tracker** |

(`database.py:2666`, en `update_account_status`, **no** es un escritor de `progress`: escribe
`status` y `updated_at`. Es relevante para el `tracker_status` que consume `next_progress` — el caso
`COMPLETED` → relectura —, pero no para esta pareja.)

En cuanto el usuario edite su progreso en la web de AniList, o desde otro dispositivo, el sync
moverá `progress` y `chapter_progress` quedará obsoleto. Escribir «`set_chapter_progress` es el
único escritor autorizado de la pareja» sería **falso el primer día**. `set_chapter_progress` es el
único escritor que la mantiene *coherente*; no es el único escritor de `progress`.

**La regla:**

> `progress` (INTEGER) es **siempre** autoritativo. `chapter_progress` (REAL) solo es válido
> mientras `floor(chapter_progress) == progress`. Si no cuadran, el tracker se movió por debajo y
> `chapter_progress` es basura: se ignora y se cae a `float(progress)`.

Se **evalúa al leer**, no se mantiene al escribir: es la función pura
`progress.effective_chapter(progress, chapter_progress)`. Por eso no hay que tocar los cuatro
escritores, ni acordarse del quinto que alguien añada mañana. Un invariante que hay que mantener en
cuatro sitios es un invariante que se rompe; uno que se deriva al leer, no. (El número exacto de
escritores da igual para la regla — esa es justo su virtud.)

## La ventana transitoria: conocida y ACEPTADA

La regla al leer tiene una consecuencia. Secuencia:

1. El usuario lee el 10.5 → `chapter_progress = 10.5`, `progress = 10`, y la mutación se queda en
   `pending_mutations`.
2. Antes de que la cola drene, entra un sync del tracker que espeja el valor **viejo** del proveedor
   (9) en `library_entries.progress` vía `update_account_progress` (`database.py:2639`).
3. Ahora `floor(10.5) != 9` → `effective_chapter` cae a `9.0` y el reader **olvida el medio
   capítulo**.
4. Se cura solo en cuanto la mutación encolada llega y `progress` vuelve a 10.

**Se acepta.** Es transitorio, se autocura, y no pierde datos: el `chapter_progress` sigue en la
fila, solo se ignora mientras no cuadre. El precio de evitarlo sería mantener el invariante en los
cuatro escritores — que es exactamente el diseño que rechazamos arriba.

Queda escrito como consecuencia conocida y aceptada del modelo. **No es un bug pendiente**, y la
Fase 5 no debe taparlo con un parche.
