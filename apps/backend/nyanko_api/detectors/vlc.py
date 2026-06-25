import sys

from ..models import PlaybackCandidate
from ..normalizer import normalize
from .base import Detector, DetectorInfo, looks_finished


class VlcDetector(Detector):
    name = "vlc"
    priority = 20

    def __init__(self, host: str = "127.0.0.1", port: int = 8080, password: str | None = None):
        self.base_url = f"http://{host}:{port}"
        self.password = password or ""

    def info(self) -> DetectorInfo:
        return DetectorInfo(name=self.name, available=sys.platform == "win32", priority=self.priority)

    def detect(self) -> PlaybackCandidate | None:
        try:
            import httpx
        except ImportError:  # pragma: no cover
            return None

        try:
            with httpx.Client(timeout=2.0) as client:
                response = client.get(
                    f"{self.base_url}/requests/status.json",
                    auth=("", self.password) if self.password else None,
                )
                response.raise_for_status()
                data = response.json()
        except Exception:
            return None

        title = self._extract_title(data)
        if not title:
            return None
        normalized = normalize(title)
        if normalized.anime_title is None:
            return None
        position = self._extract_position(data)
        duration = self._extract_duration(data)
        return PlaybackCandidate(
            source=self.name,
            raw_title=title,
            anime_title=normalized.anime_title,
            season=normalized.season,
            episode=normalized.episode.number if normalized.episode else None,
            episode_type=normalized.episode.type if normalized.episode else None,
            confidence=min(1.0, normalized.confidence + 0.1),
            position_seconds=position,
            duration_seconds=duration,
            paused=data.get("state") == "paused",
            finished=looks_finished(position, duration),
        )

    def _extract_title(self, data: dict) -> str | None:
        info = data.get("information", {})
        category = info.get("category", {})
        if isinstance(category, dict):
            meta = category.get("meta", {})
            if isinstance(meta, dict):
                return meta.get("filename") or meta.get("title")
        return data.get("title")

    @staticmethod
    def _extract_position(data: dict) -> float | None:
        value = data.get("time")
        if isinstance(value, (int, float)) and value >= 0:
            return float(value)
        return None

    @staticmethod
    def _extract_duration(data: dict) -> float | None:
        value = data.get("length")
        if isinstance(value, (int, float)) and value > 0:
            return float(value)
        return None
