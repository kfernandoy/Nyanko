from __future__ import annotations

import time
from threading import Lock

from ..models import PlaybackCandidate
from .base import Detector, DetectorInfo


class BrowserDetector(Detector):
    name = "browser"
    priority = 110
    trusted_evidence = True

    def __init__(self, timeout_seconds: float = 15.0):
        self._timeout_seconds = timeout_seconds
        self._candidate: PlaybackCandidate | None = None
        self._received_at = 0.0
        self._lock = Lock()

    def info(self) -> DetectorInfo:
        with self._lock:
            available = self._candidate is not None and (
                time.monotonic() - self._received_at <= self._timeout_seconds
            )
        return DetectorInfo(name=self.name, available=available, priority=self.priority)

    def push(self, candidate: PlaybackCandidate | None) -> None:
        with self._lock:
            self._candidate = candidate
            self._received_at = time.monotonic()

    def detect(self) -> PlaybackCandidate | None:
        with self._lock:
            if self._candidate is None:
                return None
            if time.monotonic() - self._received_at > self._timeout_seconds:
                self._candidate = None
                return None
            # La pausa NO descarta el candidato: borrarlo vaciaba el panel a los
            # pocos segundos de pausar y obligaba a re-matchear al reanudar. El
            # flag paused viaja en el candidato y la UI/autoguardado ya lo manejan.
            if self._candidate.content_kind in {
                "trailer",
                "preview",
                "opening",
                "ending",
            }:
                return None
            return self._candidate
