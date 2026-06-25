import re
import sys

from ..models import PlaybackCandidate
from ..normalizer import normalize
from .base import Detector, DetectorInfo


class PotPlayerDetector(Detector):
    name = "potplayer"
    priority = 24

    def __init__(self, host: str = "127.0.0.1", port: int = 8208):
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
                response = client.get(f"{self.base_url}/")
                response.raise_for_status()
                text = response.text
        except Exception:
            return None

        raw_title = self._extract_title(text)
        if not raw_title:
            return None

        normalized = normalize(raw_title)
        if normalized.anime_title is None:
            return None

        return PlaybackCandidate(
            source=self.name,
            raw_title=raw_title,
            anime_title=normalized.anime_title,
            season=normalized.season,
            episode=normalized.episode.number if normalized.episode else None,
            episode_type=normalized.episode.type if normalized.episode else None,
            confidence=min(1.0, normalized.confidence + 0.15),
        )

    @staticmethod
    def _extract_title(text: str) -> str | None:
        # PotPlayer's web control returns an HTML page with the current file/title.
        # The exact markup varies by version, so we use a few heuristics.
        for pattern in (
            r"<title[^>]*>(.*?)</title>",
            r"id=\"title\"[^>]*>(.*?)</",
            r"name=\"title\"[^>]*value=\"([^\"]+)\"",
            r"filename[:=]\s*([^<\n]+)",
        ):
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                value = match.group(1).strip()
                value = value.split("\\")[-1].split("/")[-1]
                if value and value.lower() not in ("potplayer", "web control", ""):
                    return value
        return None
