"""Check FND-05: ninguna columna persistida de la BD REAL puede empezar por `http`.

El test de `tests/test_persisted_urls.py` corre contra una BD sintetica en CI: siempre verde,
siempre rapido, y ciego a lo que hay escrito en la biblioteca del usuario. El bug que se llevo
todas las portadas (`http://127.0.0.1:<puerto-efimero>/assets/...` persistido en
`cover_image_local`) vivia en los DATOS, no en el esquema: un fixture no lo habria encontrado
nunca. Este script corre la MISMA guardia contra un fichero de BD de verdad.

La deteccion y la lista blanca NO se reimplementan aqui: se importan del test. Que diverjan es
como la guardia acaba diciendo cosas distintas segun quien la llame.

La BD NUNCA se toca: se abre en `mode=ro`.

Ejecutable con: python scripts/check_persisted_urls.py [ruta-a-la-bd]

Sin argumento usa la BD de produccion, que puede seguir en v7. Para ejercitar la guardia
sobre las columnas del esquema v8, corre antes `python scripts/verify_real_db_migration.py` y
pasale la copia migrada que imprime en su ultima linea.
"""
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.test_persisted_urls import (  # noqa: E402
    REMOTE_URL_ALLOWLIST,
    find_loopback_urls,
    find_persisted_urls,
)

DEFAULT_DB = Path(os.path.expandvars(r"%APPDATA%\app.nyanko.desktop")) / "nyanko.sqlite3"


def main() -> int:
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DB
    if not target.exists():
        # Una maquina de CI, o cualquiera que no sea la del autor. Un gate que revienta en
        # toda maquina sin la biblioteca del autor no es un gate, es una mina.
        print(f"sin BD que inspeccionar en {target}: omitido")
        return 0

    print(f"BD: {target}  ({target.stat().st_size / 1_048_576:.1f} MB, mode=ro)")

    connection = sqlite3.connect(f"file:{target}?mode=ro", uri=True)
    try:
        version = connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0]
        hits = find_persisted_urls(connection)
        loopback = find_loopback_urls(connection)
    finally:
        connection.close()
    print(f"schema: v{version}\n")

    allowed = [hit for hit in hits if (hit[0], hit[1]) in REMOTE_URL_ALLOWLIST]
    violations = [hit for hit in hits if (hit[0], hit[1]) not in REMOTE_URL_ALLOWLIST]

    # Sin lista blanca que valga: apuntar al propio sidecar no lo exime ninguna columna.
    if loopback:
        print("FALLO: hay filas que apuntan al PROPIO sidecar (host loopback + puerto):")
        for table, column, rows in loopback:
            exenta = " (columna EXENTA -- la lista blanca NO exime de esto)" if (table, column) in REMOTE_URL_ALLOWLIST else ""
            print(f"  {table}.{column}: {rows} filas{exenta}")
        print("\nUna URL nuestra con el puerto dentro muere en el siguiente arranque del")
        print("sidecar. Guarda la ruta RELATIVA ('/assets/...') y resuelvela al renderizar.")
        return 1

    # Imprimir los aciertos EXENTOS con sus recuentos no es ruido: es la prueba de que la
    # guardia esta mirando filas de verdad. Una guardia sobre tablas vacias pasa en vacio, y
    # eso es un exit 0 que no ha comprobado nada.
    print(f"columnas de URL remota legitima (lista blanca) -- {len(allowed)} con datos:")
    for table, column, rows in allowed:
        print(f"  OK  {f'{table}.{column}':<38} {rows:>6} filas empiezan por http")
    for table, column in sorted(REMOTE_URL_ALLOWLIST):
        if not any(table == t and column == c for t, c, _ in allowed):
            print(f"  --  {f'{table}.{column}':<38} {0:>6} filas (exenta, pero vacia)")

    if violations:
        print("\nFALLO: URLs absolutas persistidas fuera de la lista blanca:")
        for table, column, rows in violations:
            print(f"  {table}.{column}: {rows} filas empiezan por http")
        print("\nEs el bug que dejo la biblioteca sin una sola portada. Guarda rutas")
        print("RELATIVAS ('/assets/...'): una URL con el puerto dentro muere en el siguiente")
        print("arranque del sidecar, y no se cura sola.")
        return 1

    total = sum(rows for _, _, rows in allowed)
    print("\nOK: ninguna columna persistida empieza por http fuera de la lista blanca.")
    print(f"({total} filas de URL remota legitima inspeccionadas: la guardia no paso en vacio)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
