import re
import sys

from ..models import PlaybackCandidate
from ..normalizer import normalize
from .base import Detector, DetectorInfo, looks_finished


class MpcHcDetector(Detector):
    name = "mpc-hc"
    priority = 25

    def __init__(self, host: str = "127.0.0.1", port: int = 13579):
        self.base_url = f"http://{host}:{port}"

    def info(self) -> DetectorInfo:
        return DetectorInfo(name=self.name, available=sys.platform == "win32", priority=self.priority)

    def detect(self) -> PlaybackCandidate | None:
        try:
            import httpx
        except ImportError:  # pragma: no cover
            return None

        try:
            with httpx.Client(timeout=2.0) as client:
                response = client.get(f"{self.base_url}/variables.html")
                response.raise_for_status()
                text = response.text
        except Exception:
            return None

        state = self._extract_int(text, "state")
        if state != 2:  # 0 = stopped, 1 = paused, 2 = playing
            return None

        raw_title = self._extract_title(text)
        if not raw_title:
            return None

        normalized = normalize(raw_title)
        if normalized.anime_title is None:
            return None

        position = self._extract_float(text, "position")
        duration = self._extract_float(text, "duration")
        return PlaybackCandidate(
            source=self.name,
            raw_title=raw_title,
            anime_title=normalized.anime_title,
            season=normalized.season,
            episode=normalized.episode.number if normalized.episode else None,
            episode_type=normalized.episode.type if normalized.episode else None,
            confidence=min(1.0, normalized.confidence + 0.15),
            position_seconds=position,
            duration_seconds=duration,
            paused=state == 1,
            finished=looks_finished(position, duration),
        )

    @staticmethod
    def _extract_int(text: str, name: str) -> int | None:
        match = re.search(rf"<p\s+id=[\"']{name}[\"'][^>]*>(\d+)</p>", text, re.IGNORECASE)
        if match:
            return int(match.group(1))
        # Fallback for older MPC-HC builds that use bare variable lines.
        match = re.search(rf"{name}\s*[:=]\s*(\d+)", text, re.IGNORECASE)
        if match:
            return int(match.group(1))
        return None

    @staticmethod
    def _extract_title(text: str) -> str | None:
        # Try the file path first, then the media title.
        for variable in ("filepath", "file", "title"):
            match = re.search(
                rf"<p\s+id=[\"']{variable}[\"'][^>]*>(.*?)</p>", text, re.IGNORECASE | re.DOTALL
            )
            if match:
                value = match.group(1).strip()
                value = value.split("\\")[-1].split("/")[-1]
                if value:
                    return value
        return None

    @staticmethod
    def _extract_float(text: str, name: str) -> float | None:
        match = re.search(rf"<p\s+id=[\"']{name}[\"'][^>]*>([\d.]+)</p>", text, re.IGNORECASE)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                return None
        match = re.search(rf"{name}\s*[:=]\s*([\d.]+)", text, re.IGNORECASE)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                return None
        return None
