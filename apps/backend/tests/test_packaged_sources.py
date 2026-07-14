from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import time
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def packaged_exe(tmp_path_factory) -> Path:
    pyinstaller = shutil.which("pyinstaller")
    assert pyinstaller is not None, "pyinstaller no esta instalado"

    root = tmp_path_factory.mktemp("nyanko-packaged")
    dist = root / "dist"
    build = root / "build"
    subprocess.run(
        [
            pyinstaller,
            "nyanko-api.spec",
            "--noconfirm",
            "--clean",
            "--distpath",
            str(dist),
            "--workpath",
            str(build),
        ],
        cwd=BACKEND_DIR,
        check=True,
        capture_output=True,
        text=True,
        timeout=600,
    )
    exe_name = "nyanko-api.exe" if os.name == "nt" else "nyanko-api"
    exe = dist / "nyanko-api" / exe_name
    assert exe.exists(), f"No se construyo {exe}"
    return exe


@pytest.fixture
def packaged_sidecar(
    packaged_exe: Path, tmp_path
) -> Iterator[tuple[subprocess.Popen, Path, int]]:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    port = _free_port()
    env = {
        **os.environ,
        "NYANKO_DATA_DIR": str(data_dir),
        "NYANKO_API_HOST": "127.0.0.1",
        "NYANKO_API_PORT": str(port),
    }
    stdout = (tmp_path / "nyanko-api.stdout.log").open("w", encoding="utf-8")
    stderr = (tmp_path / "nyanko-api.stderr.log").open("w", encoding="utf-8")
    process = subprocess.Popen(
        [str(packaged_exe)],
        cwd=packaged_exe.parent,
        env=env,
        stdout=stdout,
        stderr=stderr,
    )
    try:
        real_port = _wait_for_port_file(data_dir, process)
        _wait_for_json(real_port, "/api/health", process)
        yield process, data_dir, real_port
    finally:
        _terminate(process)
        stdout.close()
        stderr.close()


def test_packaged_sources_endpoint_is_not_empty(packaged_sidecar):
    process, data_dir, port = packaged_sidecar

    payload = _wait_for_json(port, "/api/sources", process)

    assert process.poll() is None
    assert process.pid > 0
    assert (data_dir / "port").read_text(encoding="utf-8").strip() == str(port)
    assert (data_dir / "nyanko.sqlite3").exists()
    assert isinstance(payload, list)
    assert len(payload) > 0


def _free_port() -> int:
    while True:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        if port != 8765:
            return int(port)


def _wait_for_port_file(data_dir: Path, process: subprocess.Popen) -> int:
    port_file = data_dir / "port"
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        _assert_alive(process)
        if port_file.exists():
            raw = port_file.read_text(encoding="utf-8").strip()
            if raw:
                return int(raw)
        time.sleep(0.1)
    raise AssertionError("El sidecar empaquetado no escribio el archivo de puerto")


def _wait_for_json(port: int, path: str, process: subprocess.Popen):
    url = f"http://127.0.0.1:{port}{path}"
    deadline = time.monotonic() + 30
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        _assert_alive(process)
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                assert response.status == 200
                return json.loads(response.read().decode("utf-8"))
        except Exception as error:
            last_error = error
            time.sleep(0.2)
    raise AssertionError(f"No respondio {url}: {last_error}")


def _assert_alive(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        raise AssertionError(f"El sidecar empaquetado termino con codigo {process.returncode}")


def _terminate(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)
