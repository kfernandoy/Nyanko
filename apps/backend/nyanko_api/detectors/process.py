from __future__ import annotations

import time
from pathlib import Path

from ..models import PlaybackCandidate
from ..normalizer import normalize
from ..scanner import VIDEO_EXTENSIONS
from .base import Detector, DetectorInfo

# Ejecutables de reproductores conocidos (port de players.anisthesia de Taiga).
# Aquí la evidencia es el archivo que el proceso tiene abierto, no su ventana,
# así que basta con reconocer el ejecutable.
PLAYER_EXECUTABLES = frozenset(
    {
        "vlc.exe",
        "mpv.exe",
        "mpvnet.exe",
        "mpc-hc.exe",
        "mpc-hc64.exe",
        "mpc-be.exe",
        "mpc-be64.exe",
        "potplayer.exe",
        "potplayermini.exe",
        "potplayermini64.exe",
        "wmplayer.exe",
        "kmplayer.exe",
        "gom.exe",
        "smplayer.exe",
        "bsplayer.exe",
        "mplayer.exe",
        "zoomplayer.exe",
        "splayer.exe",
        "kodi.exe",
    }
)


class ProcessDetector(Detector):
    """Estrategia "open files" de Taiga/anisthesia.

    Encuentra el archivo de video que un reproductor conocido está usando —
    primero por su línea de comandos (doble clic sobre el archivo) y si no por
    sus handles abiertos. Funciona sin interfaces web/IPC habilitadas y entrega
    el nombre de archivo completo, mucho más fiable que un título de ventana.
    No aporta posición/duración: los detectores IPC tienen mayor prioridad.
    """

    name = "process"
    priority = 18
    trusted_evidence = True

    def __init__(self) -> None:
        # open_files() enumera handles y no es gratis: cachear por PID unos segundos.
        self._open_files_cache: dict[int, tuple[float, str | None]] = {}

    @staticmethod
    def _psutil():
        try:
            import psutil

            return psutil
        except ImportError:  # pragma: no cover
            return None

    def info(self) -> DetectorInfo:
        return DetectorInfo(
            name=self.name, available=self._psutil() is not None, priority=self.priority
        )

    def detect(self) -> PlaybackCandidate | None:
        psutil = self._psutil()
        if psutil is None:
            return None
        try:
            processes = list(psutil.process_iter(["name"]))
        except Exception:
            return None
        for proc in processes:
            name = (proc.info.get("name") or "").lower()
            if name not in PLAYER_EXECUTABLES:
                continue
            path = self._video_path(proc)
            if path is None:
                continue
            filename = Path(path).stem
            normalized = normalize(filename)
            title = normalized.anime_title
            if title is None:
                continue
            return PlaybackCandidate(
                source=self.name,
                raw_title=Path(path).name,
                anime_title=title,
                season=normalized.season,
                episode=normalized.episode.number if normalized.episode else None,
                episode_type=normalized.episode.type if normalized.episode else None,
                confidence=min(1.0, normalized.confidence + 0.2),
            )
        return None

    def _video_path(self, proc) -> str | None:
        try:
            for argument in proc.cmdline()[1:]:
                if Path(argument).suffix.lower() in VIDEO_EXTENSIONS:
                    return argument
        except Exception:
            return None
        return self._video_from_open_files(proc)

    def _video_from_open_files(self, proc) -> str | None:
        now = time.monotonic()
        cached = self._open_files_cache.get(proc.pid)
        # TTL corto: si el usuario abre el archivo desde la UI del reproductor,
        # la detección no debe esperar a que venza un negativo cacheado largo.
        if cached is not None and now - cached[0] < 2.0:
            return cached[1]
        path: str | None = None
        try:
            for handle in proc.open_files():
                if Path(handle.path).suffix.lower() in VIDEO_EXTENSIONS:
                    path = handle.path
                    break
        except Exception:
            path = None
        if len(self._open_files_cache) > 64:
            self._open_files_cache.clear()
        self._open_files_cache[proc.pid] = (now, path)
        return path
