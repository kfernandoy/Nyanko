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
