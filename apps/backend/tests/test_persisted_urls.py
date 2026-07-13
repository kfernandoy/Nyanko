"""Guardia FND-05: ninguna columna persistida puede empezar por `http` sin justificación.

Este proyecto ya perdió TODAS las portadas de la biblioteca por esto. El backend guardaba
`cover_image_local` como URL absoluta con el puerto del sidecar dentro
(`http://127.0.0.1:8765/assets/...`). El sidecar arrancó un día en otro puerto, y la
biblioteca se quedó sin una sola portada, de forma permanente y silenciosa: no se curó sola.
El reader de la Fase 3 multiplica esa superficie por diez (cada página de cada capítulo).

La guardia descubre el esquema EN RUNTIME (`sqlite_master` + `PRAGMA table_info`). No hay
ninguna lista de tablas ni de columnas que mantener: cubre las columnas del esquema v8 y las
que añada cualquier fase futura sin que nadie tenga que acordarse de actualizarla. La guardia
que hay que actualizar a mano es la guardia que un día no se actualiza.

PARA QUIEN PLANIFIQUE LA FASE 3 (y la 7, y la 8) — IMPORTANTE:

    Llama a `assert_no_persisted_urls(connection)` al final de CUALQUIER test que persista una
    URL de página, de portada o de cualquier asset.

Motivo, y es el que importa: esto es un control sobre DATOS. Sobre una tabla vacía, un
`SELECT ... LIKE 'http%'` no encuentra nada y el test es verde SIN HABER MIRADO NADA. Si la
Fase 3 no invoca la guardia después de sus propias escrituras, la guardia se queda verde
mientras el reader persiste URLs absolutas — que es exactamente el fallo que existe para
impedir. Por eso la detección vive en dos funciones importables, no enterrada en un test:

    from tests.test_persisted_urls import assert_no_persisted_urls
    assert_no_persisted_urls(connection)   # después de tus escrituras, no antes
"""
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nyanko_api.database import Database  # noqa: E402

# Columnas que guardan una URL REMOTA legítima: la del proveedor, no la del sidecar. Cada
# entrada se derivó CORRIENDO la guardia contra la BD real de producción migrada a v8 y
# justificando el acierto uno por uno. Nada entra aquí «para que pase».
REMOTE_URL_ALLOWLIST: frozenset[tuple[str, str]] = frozenset(
    {
        # La URL pública del media en el proveedor: https://anilist.co/anime/21 (5.099 filas
        # en la BD real). Es del proveedor, no nuestra: no caduca con el puerto del sidecar.
        ("external_identities", "url"),
        # El `siteUrl` que devuelve AniList (2.786 filas). Mismo caso.
        ("media_details_cache", "site_url"),
        # El banner en el CDN del proveedor: https://s4.anilist.co/... (1.938 filas). Es el
        # ORIGEN remoto. Su copia local vive en `banner_image_local`, que NO está exenta.
        ("media_details_cache", "banner_image"),
        # La portada en el CDN del proveedor (2.786 filas). Mismo caso: el original remoto.
        # La copia local es `cover_image_local`, y esa es precisamente la que se llevó por
        # delante la biblioteca. No está exenta y no puede estarlo.
        ("media_details_cache", "cover_image"),
        # El feed RSS de la fuente de torrents: https://nyaa.si/?page=rss (1 fila).
        ("torrent_sources", "url"),
        # La portada de la card de «no quiero verlo». `add_wont_watch` (main.py:3992) guarda
        # lo que el cliente le manda, que es la portada del CDN del proveedor cuando no hay
        # asset local cacheado (y `/assets/...` RELATIVA cuando lo hay: `_asset_url`,
        # main.py:317, ya no lleva host ni puerto dentro). Hoy la tabla está vacía en la BD
        # real, así que la guardia no la acierta todavía; está exenta por lo que su ESCRITOR
        # guarda, no para silenciar un acierto.
        ("wont_watch", "cover_image"),
    }
)

# DOS EXCLUSIONES QUE NO SON LISTA BLANCA, y por eso no están arriba:
#
#   - Las columnas `*_json` (`synonyms_json`, `relations_json`, `characters_json`, ...) y
#     `cache.payload` guardan payloads JSON del proveedor con URLs remotas DENTRO. Pero el
#     valor de la columna no *empieza* por `http`: empieza por `{` o por `[`. La guardia no
#     las toca, sin necesidad de exención alguna.
#   - Si algún día una de ellas EMPEZARA por `http`, querríamos enterarnos: significaría que
#     alguien guardó una URL suelta donde debía ir un documento. Que salte.

_URL_PREFIX = "http"


def find_persisted_urls(connection: sqlite3.Connection) -> list[tuple[str, str, int]]:
    """Toda columna de toda tabla cuyo valor empiece por `http`: (tabla, columna, filas).

    El esquema se descubre en runtime. Cero listas escritas a mano: por construcción, esto
    cubre las columnas del esquema v8 y las que llegue a añadir cualquier fase futura.

    Devuelve TODOS los aciertos, incluidos los de la lista blanca — el script los imprime con
    sus recuentos, que es como un humano ve que la guardia está mirando de verdad y no
    pasando en vacío sobre tablas sin filas.
    """
    tables = [
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    ]
    hits: list[tuple[str, str, int]] = []
    for table in tables:
        columns = [row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')]
        for column in columns:
            # SQLite convierte el operando de LIKE a texto: una columna INTEGER o REAL no
            # puede casar con 'http%', así que no hace falta filtrar por tipo declarado (y
            # filtrar por él sería un error: el tipo es una sugerencia, no una restricción).
            rows = connection.execute(
                f'SELECT COUNT(*) FROM "{table}" WHERE "{column}" LIKE ?', (f"{_URL_PREFIX}%",)
            ).fetchone()[0]
            if rows:
                hits.append((table, column, rows))
    return hits


def assert_no_persisted_urls(connection: sqlite3.Connection) -> None:
    """Falla si alguna columna NO exenta guarda un valor que empieza por `http`.

    El helper que las Fases 3/7/8 deben llamar TRAS SUS PROPIAS ESCRITURAS. Ver el docstring
    del módulo: sobre datos que no existen, esta comprobación pasa en vacío.
    """
    violations = [
        (table, column, rows)
        for table, column, rows in find_persisted_urls(connection)
        if (table, column) not in REMOTE_URL_ALLOWLIST
    ]
    if violations:
        detail = "\n".join(
            f"  {table}.{column}: {rows} fila(s) empiezan por '{_URL_PREFIX}'"
            for table, column, rows in violations
        )
        raise AssertionError(
            "URLs absolutas persistidas (el bug que dejó la biblioteca sin portadas):\n"
            f"{detail}\n"
            "Guarda una ruta RELATIVA ('/assets/...'). Una URL con host:puerto dentro muere "
            "en cuanto el sidecar arranca en otro puerto, y no se cura sola."
        )


def _seed(connection: sqlite3.Connection) -> None:
    """Siembra una fila en cada tabla que esta fase puede tocar.

    Una guardia de DATOS sobre tablas vacías es un test verde que no mira nada. Los valores
    son los reales: URLs remotas del CDN donde van URLs remotas, rutas RELATIVAS donde va el
    asset local (`_asset_url`, main.py:317).
    """
    connection.executescript(
        """
        -- `initialize()` ya siembra los providers canónicos: OR IGNORE, no los dupliques.
        INSERT OR IGNORE INTO providers (id, display_name) VALUES ('anilist', 'AniList');
        INSERT INTO accounts (id, provider_id, alias, external_user_id)
            VALUES (1, 'anilist', 'default', '12345');
        INSERT INTO media (id, media_type, chapter_count) VALUES (1, 'MANGA', 100);
        INSERT INTO media_titles (media_id, language, title, is_primary)
            VALUES (1, 'romaji', 'Berserk', 1);
        INSERT INTO media_genres (media_id, genre) VALUES (1, 'Action');
        INSERT INTO media_tags (media_id, tag) VALUES (1, 'Dark Fantasy');
        INSERT INTO media_seasons (id, media_id, season_number, label)
            VALUES (1, 1, 1, 'Season 1');
        INSERT INTO episodes (media_id, season_id, episode_number, title)
            VALUES (1, 1, 1.0, 'The Black Swordsman');
        INSERT INTO external_identities (media_id, provider_id, external_id, url)
            VALUES (1, 'anilist', '30002', 'https://anilist.co/manga/30002');
        INSERT INTO library_entries (media_id, status, progress, chapter_progress, score)
            VALUES (1, 'CURRENT', 10, 10.5, 9.0);
        INSERT INTO remote_library_entries
            (account_id, media_id, external_entry_id, status, progress, original_payload)
            VALUES (1, 1, 'e1', 'CURRENT', 10, '{"progress": 10}');
        INSERT INTO media_details_cache
            (media_id, provider_id, external_id, title, description, site_url,
             banner_image, cover_image, banner_image_local, cover_image_local,
             media_type, synonyms_json, relations_json)
            VALUES (1, 'anilist', '30002', 'Berserk', 'Guts.',
                    'https://anilist.co/manga/30002',
                    'https://s4.anilist.co/file/anilistcdn/media/manga/banner/30002.jpg',
                    'https://s4.anilist.co/file/anilistcdn/media/manga/cover/30002.jpg',
                    '/assets/anilist/30002/banner.jpg',
                    '/assets/anilist/30002/cover.jpg',
                    'MANGA', '["Berserk"]',
                    '[{"cover_image": "https://s4.anilist.co/relacionado.jpg"}]');
        INSERT INTO wont_watch (provider_id, external_id, title, cover_image)
            VALUES ('anilist', '99', 'Nope', 'https://s4.anilist.co/nope.jpg');
        INSERT INTO library_folders (path) VALUES ('E:\\manga');
        INSERT INTO local_files (path, media_id, episode, parsed_title, matched)
            VALUES ('E:\\manga\\berserk\\c001.cbz', 1, 1, 'Berserk', 1);
        INSERT INTO cache (key, payload, expires_at)
            VALUES ('media:1', '{"coverImage": "https://s4.anilist.co/x.jpg"}', 0);
        INSERT INTO playback_events (source, raw_title, media_id, progress_before, progress_after)
            VALUES ('mpv', 'Berserk - 01', 1, 9, 10);
        INSERT INTO match_corrections (raw_pattern, media_id) VALUES ('berserk', 1);
        INSERT INTO media_mappings (provider, site_identifier, media_id)
            VALUES ('anilist', 'berserk', 1);
        INSERT INTO conflicts (media_id, account_id, field, local_value, remote_value)
            VALUES (1, 1, 'progress', '10', '9');
        INSERT INTO extension_clients (label, token_hash, created_at, expires_at)
            VALUES ('firefox', 'deadbeef', 0, 0);
        -- `initialize()` también siembra la fuente nyaa (con su RSS): OR IGNORE.
        INSERT OR IGNORE INTO torrent_sources (id, name, url)
            VALUES (1, 'nyaa', 'https://nyaa.si/?page=rss&c=1_2&f=0');
        INSERT INTO torrent_seen (signature, media_id) VALUES ('sig1', 1);
        INSERT INTO pending_mutations
            (provider_id, account_alias, kind, external_id, media_id, payload)
            VALUES ('anilist', 'default', 'progress', '30002', 1, '{"progress": 11}');
        INSERT INTO settings (key, value) VALUES ('theme', 'dark');
        """
    )
    connection.commit()


def _seeded_database(tmp_path) -> sqlite3.Connection:
    database = Database(tmp_path / "nyanko.sqlite3")
    database.initialize()
    connection = sqlite3.connect(tmp_path / "nyanko.sqlite3")
    _seed(connection)
    return connection


def test_no_persisted_column_starts_with_http(tmp_path):
    """El test de la fase, sobre una BD SEMBRADA: nada persistido empieza por `http`."""
    connection = _seeded_database(tmp_path)
    try:
        assert_no_persisted_urls(connection)
    finally:
        connection.close()


def test_guard_is_not_passing_vacuously(tmp_path):
    """La guardia mira filas de verdad: las columnas exentas SÍ traen URLs remotas.

    Un `LIKE 'http%'` sobre tablas vacías pasa en vacío. Si este test deja de encontrar
    aciertos, la siembra se ha roto y el test de arriba es verde sin mirar nada.
    """
    connection = _seeded_database(tmp_path)
    try:
        hits = {(table, column) for table, column, _ in find_persisted_urls(connection)}
        assert ("media_details_cache", "cover_image") in hits
        assert ("external_identities", "url") in hits
        assert hits <= REMOTE_URL_ALLOWLIST
    finally:
        connection.close()


def test_local_column_with_absolute_url_fails_the_guard(tmp_path):
    """EL BUG QUE YA OCURRIÓ: el puerto del sidecar dentro de `cover_image_local`."""
    connection = _seeded_database(tmp_path)
    try:
        connection.execute(
            "UPDATE media_details_cache SET cover_image_local = ?",
            ("http://127.0.0.1:8765/assets/x.jpg",),
        )
        connection.commit()

        try:
            assert_no_persisted_urls(connection)
        except AssertionError as error:
            message = str(error)
        else:
            raise AssertionError("la guardia NO detectó el bug que se llevó las portadas")

        assert "media_details_cache" in message
        assert "cover_image_local" in message
        assert "1" in message  # el número de filas afectadas
    finally:
        connection.close()


def test_guard_covers_columns_it_never_names(tmp_path):
    """Una columna que este test NO nombra: la guardia la cubre igual.

    Es la propiedad entera de la guardia. La columna se añade en runtime, con el mismo
    `ALTER TABLE ADD COLUMN` que usan las migraciones, y la guardia la encuentra sola: se la
    da `PRAGMA table_info`, no una lista escrita a mano.
    """
    connection = _seeded_database(tmp_path)
    try:
        connection.execute("ALTER TABLE episodes ADD COLUMN page_image_local TEXT")
        connection.execute(
            "UPDATE episodes SET page_image_local = ?",
            ("http://127.0.0.1:49876/assets/anilist/30002/p1.jpg",),
        )
        connection.commit()

        try:
            assert_no_persisted_urls(connection)
        except AssertionError as error:
            assert "episodes" in str(error)
            assert "page_image_local" in str(error)
        else:
            raise AssertionError("la guardia no cubre las columnas que no están escritas en ella")
    finally:
        connection.close()


def test_json_payloads_are_not_flagged(tmp_path):
    """Los `*_json` y `cache.payload` llevan URLs DENTRO, pero empiezan por `{` o `[`."""
    connection = _seeded_database(tmp_path)
    try:
        hits = {(table, column) for table, column, _ in find_persisted_urls(connection)}
        assert ("media_details_cache", "relations_json") not in hits
        assert ("cache", "payload") not in hits
    finally:
        connection.close()


@pytest.mark.parametrize(
    "poisoned",
    [
        "http://127.0.0.1:8765/assets/anilist/99/cover.jpg",
        "http://localhost:8765/assets/anilist/99/cover.jpg",
        "http://[::1]:8765/assets/anilist/99/cover.jpg",
        "https://127.0.0.1:8765/assets/anilist/99/cover.jpg",
    ],
)
def test_loopback_url_fails_even_in_an_allowlisted_column(tmp_path, poisoned):
    """LOS DIENTES: la lista blanca exime de `http%`. De apuntar al sidecar NO exime a nadie.

    `wont_watch.cover_image` está EXENTA, y hoy con razón: guarda la portada del CDN remoto.
    Pero el renderer prefija cada `/assets/...` con `http://127.0.0.1:<puerto>` (api.ts:204) y
    `addWontWatch` reenvía esa URL tal cual a `add_wont_watch` (main.py:3992), que la guarda.
    Con una guardia que exime por COLUMNA, ese veneno entra sin que salte nada — la exención
    es de la columna, y el bug es del VALOR. Este test es la única razón de que eso no pase.
    """
    connection = _seeded_database(tmp_path)
    try:
        assert ("wont_watch", "cover_image") in REMOTE_URL_ALLOWLIST, (
            "este test pierde todo el sentido si la columna deja de estar exenta"
        )
        connection.execute("UPDATE wont_watch SET cover_image = ?", (poisoned,))
        connection.commit()

        try:
            assert_no_persisted_urls(connection)
        except AssertionError as error:
            message = str(error)
        else:
            raise AssertionError(
                "la guardia dejó pasar una URL al PROPIO sidecar por estar en una columna exenta"
            )

        assert "wont_watch" in message
        assert "cover_image" in message
    finally:
        connection.close()


def test_loopback_check_does_not_flag_remote_cdn_urls(tmp_path):
    """Y no muerde a quien no debe: la portada del CDN remoto sigue siendo legítima."""
    connection = _seeded_database(tmp_path)
    try:
        assert find_loopback_urls(connection) == []
    finally:
        connection.close()


def test_loopback_url_hidden_inside_a_json_payload_is_caught(tmp_path):
    """El veneno no siempre va al principio del valor: en `cache.payload` va DENTRO del JSON.

    `cache.payload` no está exenta — no le hace falta: no *empieza* por `http`, empieza por `{`.
    Un `LIKE 'http%'` no lo ve. Pero esa portada la sirve el backend igual, y muere con el
    puerto igual. Se busca el host, esté donde esté dentro del valor.
    """
    connection = _seeded_database(tmp_path)
    try:
        connection.execute(
            "UPDATE cache SET payload = ?",
            ('{"coverImage": "http://127.0.0.1:8765/assets/x.jpg"}',),
        )
        connection.commit()

        try:
            assert_no_persisted_urls(connection)
        except AssertionError as error:
            assert "cache" in str(error)
            assert "payload" in str(error)
        else:
            raise AssertionError("la guardia no mira dentro del valor: solo su primer carácter")
    finally:
        connection.close()


def test_allowlist_never_covers_local_columns():
    """LA REGLA DURA: ninguna columna de ruta LOCAL puede estar exenta. Nunca.

    La lista blanca es el mecanismo por el que un ejecutor con prisa silencia un acierto real
    («lo meto en la lista y pasa»). Las columnas locales son, por definición, rutas — y son
    exactamente las dos que se llevaron por delante las portadas de la biblioteca entera.
    Exentarlas sería usar la lista blanca para consentir la reincidencia del bug.

    El sufijo comprobado es `path` a secas, no `_path`: las dos columnas de rutas locales que
    existen hoy se llaman `local_files.path` y `library_folders.path`, y ninguna acaba en
    `_path`. Una regla literal `_path` habría dejado fuera justo lo que tiene que cubrir.
    """
    for table, column in REMOTE_URL_ALLOWLIST:
        assert not column.endswith("_local"), f"{table}.{column} es una ruta local: no puede estar exenta"
        assert not column.endswith("path"), f"{table}.{column} es una ruta local: no puede estar exenta"
