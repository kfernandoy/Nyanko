from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from threading import Event, Lock, Thread
from typing import ClassVar

from ..models import PlaybackCandidate


logger = logging.getLogger(__name__)


def looks_finished(
    position_seconds: float | None, duration_seconds: float | None
) -> bool | None:
    """Heuristic for end-of-playback based on position and duration.

    Returns None when there is not enough information.
    """
    if position_seconds is None or duration_seconds is None or duration_seconds <= 0:
        return None
    if position_seconds >= duration_seconds * 0.95:
        return True
    if duration_seconds - position_seconds <= 60:
        return True
    return False


@dataclass(frozen=True, slots=True)
class DetectorInfo:
    name: str
    available: bool
    priority: int
    enabled: bool = True


class Detector(ABC):
    """Base class for media detectors."""

    name: ClassVar[str]
    priority: ClassVar[int] = 0
    # Evidencia directa de reproducción (archivo abierto, IPC del reproductor,
    # extensión): no parpadea como un título de ventana, así que el manager la
    # publica casi de inmediato en vez de aplicar el umbral anti-transiciones.
    trusted_evidence: ClassVar[bool] = False

    @abstractmethod
    def info(self) -> DetectorInfo:
        """Return metadata about this detector."""
        ...

    @abstractmethod
    def detect(self) -> PlaybackCandidate | None:
        """Return the currently playing media, or None if not available."""
        ...

    def start(self) -> None:
        """Optional lifecycle hook called when the detector is registered."""

    def stop(self) -> None:
        """Optional lifecycle hook called when the application shuts down."""


class DetectorManager:
    """Run detectors by priority and return the best candidate."""

    def __init__(self, stability_seconds: float = 3.0):
        self._detectors: list[Detector] = []
        self._enabled: dict[str, bool] = {}
        self._latest: PlaybackCandidate | None = None
        self._latest_lock = Lock()
        self._stop_event = Event()
        self._poll_thread: Thread | None = None
        self._stability_seconds = max(0.0, stability_seconds)
        # Las fuentes con evidencia directa publican tras una sola confirmación (~1 s
        # de sondeo), no tras el umbral completo: el umbral existe para títulos de
        # ventana que parpadean, no para archivos/IPC reales.
        self._trusted_stability_seconds = min(1.0, self._stability_seconds)
        self._trusted_sources: set[str] = set()
        self._grace_seconds = 5.0
        self._pending_fingerprint: tuple | None = None
        self._pending_since = 0.0
        self._last_seen_at = 0.0

    def register(self, detector: Detector, enabled: bool = True) -> None:
        self._detectors.append(detector)
        self._enabled[detector.name] = enabled
        if detector.trusted_evidence:
            self._trusted_sources.add(detector.name)
        self._detectors.sort(key=lambda d: d.priority, reverse=True)
        detector.start()

    def detect(self) -> PlaybackCandidate | None:
        """Run one synchronous detection pass.

        This may perform blocking player I/O and must not be called from an asyncio
        event loop. Runtime consumers should use :meth:`latest` instead.
        """
        from .pause import is_detection_paused

        if is_detection_paused():
            return None
        for detector in self._detectors:
            if not self._enabled.get(detector.name, True):
                continue
            candidate = detector.detect()
            if candidate is not None:
                return candidate
        return None

    def start_polling(self, interval: float = 1.0) -> None:
        """Continuously detect in a daemon thread and publish the latest result."""
        if self._poll_thread is not None and self._poll_thread.is_alive():
            return
        self._stop_event.clear()
        self._poll_thread = Thread(
            target=self._poll,
            args=(interval,),
            name="nyanko-media-detector",
            daemon=True,
        )
        self._poll_thread.start()

    def _poll(self, interval: float) -> None:
        while not self._stop_event.is_set():
            try:
                candidate = self.detect()
            except Exception:
                logger.exception("Unhandled detector failure")
                candidate = None
            self._publish(candidate)
            self._stop_event.wait(interval)

    def _publish(self, candidate: PlaybackCandidate | None) -> None:
        now = time.monotonic()
        fingerprint = (
            (candidate.source, candidate.raw_title, candidate.season, candidate.episode)
            if candidate is not None
            else None
        )
        with self._latest_lock:
            if fingerprint is None:
                if self._latest is not None and now - self._last_seen_at < self._grace_seconds:
                    return
                self._pending_fingerprint = None
                self._pending_since = 0.0
                self._latest = None
                return
            self._last_seen_at = now
            required = (
                self._trusted_stability_seconds
                if candidate.source in self._trusted_sources
                else self._stability_seconds
            )
            if fingerprint != self._pending_fingerprint:
                self._pending_fingerprint = fingerprint
                self._pending_since = now
                self._latest = None
                if required == 0:
                    self._latest = candidate
                return
            if now - self._pending_since >= required:
                self._latest = candidate

    def latest(self) -> PlaybackCandidate | None:
        """Return the last background result without performing player I/O."""
        from .pause import is_detection_paused

        if is_detection_paused():
            return None
        with self._latest_lock:
            candidate = self._latest
            if candidate is not None and not self._enabled.get(candidate.source, True):
                return None
            return candidate

    def list(self) -> list[DetectorInfo]:
        return [
            DetectorInfo(
                name=info.name,
                available=info.available,
                priority=info.priority,
                enabled=self._enabled.get(info.name, True),
            )
            for detector in self._detectors
            for info in (detector.info(),)
        ]

    def set_enabled(self, name: str, enabled: bool) -> bool:
        if name not in self._enabled:
            return False
        self._enabled[name] = enabled
        return True

    def stop(self) -> None:
        self._stop_event.set()
        if self._poll_thread is not None:
            self._poll_thread.join(timeout=0.5)
            self._poll_thread = None
        for detector in self._detectors:
            detector.stop()
