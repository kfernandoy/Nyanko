"""Dev server with reliable hot-reload on Windows.

uvicorn's in-process ``--reload`` detects edits but fails to swap the worker
while connections stay open (the desktop holds a permanent WebSocket and the
extension polls every second), so it serves stale code indefinitely. watchfiles
restarts the whole uvicorn process instead, which always picks up changes.
"""
import socket
import subprocess
from pathlib import Path

from watchfiles import run_process

BACKEND = Path(__file__).resolve().parents[1]
PORT = 8765


def _free_port(port: int) -> None:
    """Kill any process still holding the dev port.

    A previous dev backend that didn't shut down cleanly keeps serving stale code
    on this port; the new one then fails to bind and the desktop talks to the old
    one — the exact "I see no changes" trap. Best-effort, Windows-only.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        if probe.connect_ex(("127.0.0.1", port)) != 0:
            return  # nobody listening
    try:
        out = subprocess.run(["netstat", "-ano", "-p", "TCP"], capture_output=True, text=True).stdout
        pids = {
            line.split()[-1]
            for line in out.splitlines()
            if f":{port} " in line and "LISTENING" in line
        }
        for pid in pids:
            subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True)
    except (OSError, FileNotFoundError):
        pass  # not Windows / netstat missing — uvicorn will surface the bind error


def _kill_other_devs() -> None:
    """Solo puede haber UN dev.py.

    Instancias paralelas (dos `npm run dev`, un lanzamiento manual suelto) se roban el
    puerto entre sí en cada hot-reload —taskkill mutuo, "el backend se cae solo"— y
    sus workers huérfanos siguen quemando CPU contra la misma base. El último
    lanzado gana: al arrancar, se eliminan los árboles de cualquier otro dev.py.
    """
    import os

    # El python.exe de un venv de uv es un trampolín que lanza el python real como
    # hijo: nuestro propio dev.py son DOS procesos. Excluir también al padre, o el
    # taskkill /T al "otro" arrasaría nuestro propio árbol.
    own = {os.getpid(), os.getppid()}
    # Solo dev.py de ESTE repo: matar cualquier python con "dev.py" en la línea de
    # comandos arrasaría dev servers de otros proyectos. El ExecutablePath del venv
    # (apps/backend/.venv) ancla el match aunque dev.py se lance con ruta relativa.
    marker = str(BACKEND).lower()
    try:
        out = subprocess.run(
            [
                "powershell", "-NoProfile", "-Command",
                "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
                "ForEach-Object { \"$($_.ProcessId)|$($_.ExecutablePath)|$($_.CommandLine)\" }",
            ],
            capture_output=True, text=True, timeout=20,
        ).stdout
    except (OSError, subprocess.TimeoutExpired):
        return  # sin PowerShell/WMI: _free_port sigue cubriendo al dueño del puerto
    for line in out.splitlines():
        pid_text, _, rest = line.partition("|")
        exe_path, _, command = rest.partition("|")
        pid_text = pid_text.strip()
        if not pid_text.isdigit() or int(pid_text) in own or "dev.py" not in command:
            continue
        if marker not in exe_path.lower() and marker not in command.lower():
            continue
        subprocess.run(["taskkill", "/F", "/T", "/PID", pid_text], capture_output=True)


def _serve() -> None:
    import uvicorn

    uvicorn.run("nyanko_api.main:app", host="127.0.0.1", port=PORT, app_dir=str(BACKEND))


if __name__ == "__main__":
    _kill_other_devs()
    _free_port(PORT)
    run_process(BACKEND / "nyanko_api", target=_serve)
