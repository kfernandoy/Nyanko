import platform
import shutil
import subprocess
import sys
from pathlib import Path


def rust_target_triple() -> str:
    system = platform.system()
    machine = platform.machine().lower()
    if system == "Windows":
        return "x86_64-pc-windows-msvc"
    if system == "Darwin":
        return "x86_64-apple-darwin" if machine == "x86_64" else "aarch64-apple-darwin"
    if system == "Linux":
        return "x86_64-unknown-linux-gnu"
    raise RuntimeError(f"Unsupported platform: {system} {machine}")


def main() -> int:
    backend_root = Path(__file__).resolve().parent.parent
    desktop_root = backend_root.parent / "desktop"
    binary_dir = desktop_root / "src-tauri" / "binaries"
    binary_dir.mkdir(parents=True, exist_ok=True)

    target = rust_target_triple()
    binary_name = f"nyanko-api-{target}{'.exe' if platform.system() == 'Windows' else ''}"
    output_file = binary_dir / binary_name

    dist_dir = backend_root / "dist"
    if dist_dir.exists():
        shutil.rmtree(dist_dir)

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--onefile",
        "--name",
        "nyanko-api",
        "--distpath",
        str(dist_dir),
        "--workpath",
        str(backend_root / "build"),
        "--specpath",
        str(backend_root),
        "--hidden-import",
        "nyanko_api.anilist",
        "--hidden-import",
        "nyanko_api.config",
        "--hidden-import",
        "nyanko_api.database",
        "--hidden-import",
        "nyanko_api.detectors",
        "--hidden-import",
        "nyanko_api.instance",
        "--hidden-import",
        "nyanko_api.models",
        "--hidden-import",
        "nyanko_api.secrets",
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

    subprocess.run(command, check=True)

    built = dist_dir / ("nyanko-api.exe" if platform.system() == "Windows" else "nyanko-api")
    shutil.copy2(built, output_file)
    print(f"Sidecar built: {output_file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
