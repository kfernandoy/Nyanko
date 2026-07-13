"""Check: la migracion a schema v8 no puede perder una sola fila de la biblioteca real.

Cambiar la semantica de `library_entries.progress` DESPUES de que los usuarios hayan escrito
filas es migrar una biblioteca de verdad (33 MB, miles de entradas y episodios,
irreemplazables). Un fixture no prueba eso: prueba el fixture. Esto migra una COPIA de la BD
real de produccion y compara los recuentos tabla por tabla antes y despues.

La original NUNCA se toca: se abre en `mode=ro` y toda escritura ocurre sobre la copia. Si
este script puede migrar la BD del usuario, esta mal escrito.

Ejecutable con: python scripts/verify_real_db_migration.py [ruta-a-la-bd]
"""
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nyanko_api.database import CANONICAL_SCHEMA_VERSION, Database  # noqa: E402

DEFAULT_DB = Path(os.path.expandvars(r"%APPDATA%\app.nyanko.desktop")) / "nyanko.sqlite3"
COPY = Path(tempfile.gettempdir()) / "nyanko-v8-verify.sqlite3"
# La bitacora de migraciones GANA una fila (la v8): es justo lo que queremos que pase.
LEDGER = "schema_migrations"


def table_counts(connection: sqlite3.Connection) -> dict[str, int]:
    """Recuentos de TODAS las tablas, enumeradas desde sqlite_master.

    Una lista escrita a mano deja de cubrir la tabla que alguien anada manana."""
    names = [
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    ]
    return {name: connection.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0] for name in names}


def census(path: Path) -> tuple[str, int, dict[str, int]]:
    connection = sqlite3.connect(path)
    try:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        row = connection.execute(f"SELECT MAX(version) FROM {LEDGER}").fetchone()
        version = (row[0] or 0) if row else 0
        return integrity, version, table_counts(connection)
    finally:
        connection.close()


def copy_readonly(source: Path, destination: Path) -> None:
    """Copia consistente con la API de backup de sqlite, sobre una conexion `mode=ro`.

    Un shutil.copy() del .sqlite3 a secas se dejaria el -wal fuera y copiaria una BD a
    medias. La API de backup lee la original sin escribirla y resuelve el WAL."""
    for stale in [destination, *destination.parent.glob(f"{destination.stem}.backup-v*")]:
        stale.unlink(missing_ok=True)
    for sidecar in ("-wal", "-shm"):
        Path(str(destination) + sidecar).unlink(missing_ok=True)

    source_connection = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    destination_connection = sqlite3.connect(destination)
    try:
        source_connection.backup(destination_connection)
    finally:
        destination_connection.close()
        source_connection.close()


def main() -> int:
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DB
    if not target.exists():
        # Una maquina de CI, o cualquiera que no sea la del autor. Un gate que revienta en
        # toda maquina sin la biblioteca del autor no es un gate, es una mina.
        print(f"sin BD de produccion en {target}: omitido")
        return 0

    before_stat = target.stat()
    print(f"BD real: {target}  ({before_stat.st_size / 1_048_576:.1f} MB)")
    copy_readonly(target, COPY)
    print(f"copia:   {COPY}\n")

    pre_integrity, pre_version, pre_counts = census(COPY)

    Database(COPY).initialize()  # la migracion de verdad: la del arranque

    post_integrity, post_version, post_counts = census(COPY)

    print(f"{'tabla':<28} {'antes':>10} {'despues':>10}")
    print("-" * 50)
    failures: list[str] = []
    for name in sorted(set(pre_counts) | set(post_counts)):
        before = pre_counts.get(name)
        after = post_counts.get(name)
        mark = ""
        if name not in pre_counts:
            mark = "  (tabla nueva)"
        elif name == LEDGER:
            mark = "  (la bitacora gana la fila v8)"
        elif before != after:
            mark = "  <-- CAMBIO"
            failures.append(f"{name}: {before} -> {after} filas")
        print(f"{name:<28} {'-' if before is None else before:>10} {'-' if after is None else after:>10}{mark}")

    print(f"\nintegrity_check: {pre_integrity} -> {post_integrity}")
    print(f"schema_migrations: {pre_version} -> {post_version}")

    connection = sqlite3.connect(COPY)
    try:
        columns = {
            row[1]: row[2]
            for row in connection.execute("PRAGMA table_info(library_entries)").fetchall()
        }
    finally:
        connection.close()
    print(f"library_entries.chapter_progress: {columns.get('chapter_progress', 'AUSENTE')}")

    backups = sorted(COPY.parent.glob(f"{COPY.stem}.backup-v{CANONICAL_SCHEMA_VERSION}-*"))
    print(f"backup pre-migracion: {backups[0].name if backups else 'NO SE CREO'}")

    after_stat = target.stat()
    original_intact = (
        before_stat.st_size == after_stat.st_size and before_stat.st_mtime == after_stat.st_mtime
    )
    print(f"BD original intacta (tamano y mtime): {'si' if original_intact else 'NO'}")

    if pre_integrity != "ok":
        failures.append(f"integrity_check previo: {pre_integrity}")
    if post_integrity != "ok":
        failures.append(f"integrity_check posterior: {post_integrity}")
    if post_version != CANONICAL_SCHEMA_VERSION:
        failures.append(f"version {post_version}, se esperaba {CANONICAL_SCHEMA_VERSION}")
    if columns.get("chapter_progress") != "REAL":
        failures.append("library_entries.chapter_progress no existe como REAL")
    if not backups:
        failures.append("no se creo el backup pre-migracion: no hay rollback")
    if not original_intact:
        failures.append("la BD ORIGINAL cambio: el script la ha tocado")

    if failures:
        print("\nFALLO:")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print("\nOK: migracion v8 aditiva, integridad intacta, recuentos identicos, backup creado.")
    print(COPY)  # ultima linea: la consume la guarda de URLs del plan 01-03
    return 0


if __name__ == "__main__":
    sys.exit(main())
