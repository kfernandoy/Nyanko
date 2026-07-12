import os
import platform
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path


def main() -> int:
    backend_root = Path(__file__).resolve().parent.parent

    dist_dir = backend_root / "dist"
    if dist_dir.exists():
        shutil.rmtree(dist_dir)

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--onedir",
        "--name",
        "nyanko-api",
        "--distpath",
        str(dist_dir),
        "--workpath",
        str(backend_root / "build"),
        "--specpath",
        str(backend_root),
        # sidecar.py carga la app por string ("nyanko_api.main:app"), así que PyInstaller
        # no ve los imports de main.py. Recogemos todo el paquete de una vez (incluye main,
        # proveedores, detectores/process, torrents, matcher, normalizer…) en vez de listar
        # módulos a mano, que se desactualizaba (faltaba psutil/ProcessDetector, MAL, Kitsu…).
        "--collect-submodules",
        "nyanko_api",
        # psutil (ProcessDetector) se importa de forma diferida dentro de una función.
        "--hidden-import",
        "psutil",
        "--hidden-import",
        "keyring.backends.Windows",
        "--hidden-import",
        "keyring.backends.chainer",
        "--hidden-import",
        "keyring.backends.fail",
        "--hidden-import",
        "keyring.backends.null",
        "--hidden-import",
        "uvicorn.logging",
        "--hidden-import",
        "uvicorn.loops.auto",
        "--hidden-import",
        "uvicorn.protocols.http.auto",
        "--hidden-import",
        "uvicorn.protocols.websockets.auto",
        str(backend_root / "sidecar.py"),
    ]

    if platform.system() == "Windows":
        command.append("--noconsole")

    subprocess.run(command, check=True)

    # El bundle onedir de PyInstaller (nyanko-api.exe + _internal/) ES el artefacto final:
    # electron-builder lo copia tal cual vía extraResources → resources/nyanko-api/ (D-06/D-07).
    # Ya no se copia nada al directorio de binarios del crate Rust borrado: aquel mkdir lo
    # resucitaba en cada build del sidecar.
    bundle_dir = dist_dir / "nyanko-api"
    built = bundle_dir / ("nyanko-api.exe" if platform.system() == "Windows" else "nyanko-api")
    smoke_test(built)

    print(f"Sidecar built: {built}")
    return 0


def free_port() -> int:
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        return int(server.getsockname()[1])


def smoke_test(exe: Path) -> None:
    port = free_port()
    env = os.environ.copy()
    with tempfile.TemporaryDirectory(prefix="nyanko-sidecar-") as data_dir:
        env["NYANKO_DATA_DIR"] = data_dir
        env["NYANKO_API_PORT"] = str(port)
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        process = subprocess.Popen(
            [str(exe)],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            creationflags=creationflags,
        )
        try:
            deadline = time.time() + 30
            url = f"http://127.0.0.1:{port}/api/instance"
            while time.time() < deadline:
                if process.poll() is not None:
                    stdout, stderr = process.communicate()
                    raise RuntimeError(
                        f"Sidecar smoke test exited with {process.returncode}\n{stdout}{stderr}"
                    )
                try:
                    with urllib.request.urlopen(url, timeout=1) as response:
                        if response.status == 200:
                            return
                except OSError:
                    time.sleep(0.25)
            raise RuntimeError("Sidecar smoke test timed out")
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()


if __name__ == "__main__":
    sys.exit(main())
