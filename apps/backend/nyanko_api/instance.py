import secrets
import socket
from pathlib import Path


def generate_token() -> str:
    return secrets.token_urlsafe(32)


def read_token_file(path: Path) -> str | None:
    if not path.exists():
        return None
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return None


def write_token_file(path: Path, token: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(token, encoding="utf-8")


def find_free_port(host: str) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return sock.getsockname()[1]


def resolve_port(host: str, preferred: int) -> int:
    """Puerto en el que escuchar el sidecar.

    OAuth necesita un puerto estable: el `redirect_uri` registrado en AniList/MAL apunta
    a un puerto fijo (p. ej. 8765), así que se intenta ese primero. Si está ocupado se cae
    a uno libre —la app funciona, pero el login OAuth fallará hasta liberar el puerto—.
    `preferred == 0` significa puerto dinámico explícito.
    """
    if preferred == 0:
        return find_free_port(host)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((host, preferred))
            return preferred
        except OSError:
            return find_free_port(host)


def read_port_file(path: Path) -> int | None:
    token = read_token_file(path)
    if token is None:
        return None
    try:
        return int(token)
    except ValueError:
        return None


def write_port_file(path: Path, port: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(port), encoding="utf-8")
