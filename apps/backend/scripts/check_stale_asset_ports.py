"""Check: ninguna URL de asset guardada debe apuntar a un puerto donde el sidecar no escucha.

El backend persiste cover_image_local/banner_image_local como URLs ABSOLUTAS con el puerto
dentro. Si el sidecar arranca en otro puerto (porque el 8765 estaba ocupado), esas URLs
mueren y la biblioteca se queda sin portadas, sin curarse sola (COALESCE en database.py:1503
conserva el valor viejo; el `or` de la 1607 lo prefiere antes que caer al CDN remoto).

Falla ANTES de la reparacion, pasa DESPUES. Ejecutable con: python check_stale_asset_ports.py
"""
import os
import re
import sqlite3
import sys

DD = os.path.expandvars(r"%APPDATA%\app.nyanko.desktop")
DB = os.path.join(DD, "nyanko.sqlite3")
PORT_FILE = os.path.join(DD, "port")
COLS = ("cover_image_local", "banner_image_local")
PORT_RE = re.compile(r"^http://127\.0\.0\.1:(\d+)/")


def live_port() -> int:
    with open(PORT_FILE, encoding="utf-8") as fh:
        return int(fh.read().strip())


def stale_counts(conn, port: int) -> dict[str, dict[int, int]]:
    """Por columna: {puerto_encontrado: numero_de_filas} para los puertos != port."""
    out = {}
    for col in COLS:
        found: dict[int, int] = {}
        rows = conn.execute(
            f"SELECT {col} FROM media_details_cache WHERE {col} IS NOT NULL AND {col} != ''"
        )
        for (url,) in rows:
            m = PORT_RE.match(url)
            if m and int(m.group(1)) != port:
                found[int(m.group(1))] = found.get(int(m.group(1)), 0) + 1
        out[col] = found
    return out


def main() -> int:
    port = live_port()
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    stale = stale_counts(conn, port)
    total = sum(sum(v.values()) for v in stale.values())

    print(f"puerto real del sidecar (fichero `port`): {port}")
    for col, ports in stale.items():
        if ports:
            detalle = ", ".join(f"{p} ({n} filas)" for p, n in sorted(ports.items()))
            print(f"  {col}: APUNTA A PUERTOS MUERTOS -> {detalle}")
        else:
            print(f"  {col}: OK (todas las URLs apuntan al {port})")

    if total:
        print(f"\nFALLO: {total} URLs de assets apuntan a un puerto donde el sidecar NO escucha.")
        print("La biblioteca mostrara huecos en lugar de portadas.")
        return 1

    print(f"\nOK: todas las URLs de assets apuntan al puerto vivo ({port}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
