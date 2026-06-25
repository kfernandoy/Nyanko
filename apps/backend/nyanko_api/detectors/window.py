import ctypes
import sys
from ctypes import wintypes

from ..models import PlaybackCandidate
from ..normalizer import normalize
from .base import Detector, DetectorInfo


PLAYER_MARKERS = ("vlc media player", "mpv", "mpc-hc", "potplayer")


def get_active_window_title() -> str:
    if sys.platform != "win32":
        return ""
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetForegroundWindow.restype = wintypes.HWND
    window = user32.GetForegroundWindow()
    if not window:
        return ""
    length = user32.GetWindowTextLengthW(window)
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(window, buffer, length + 1)
    return buffer.value.strip()


def parse_media_title(raw_title: str, source: str = "active-window") -> PlaybackCandidate:
    normalized = normalize(raw_title)
    return PlaybackCandidate(
        source=source,
        raw_title=raw_title,
        anime_title=normalized.anime_title,
        season=normalized.season,
        episode=normalized.episode.number if normalized.episode else None,
        episode_type=normalized.episode.type if normalized.episode else None,
        confidence=normalized.confidence,
    )


class ActiveWindowDetector(Detector):
    name = "active-window"
    priority = 10

    def info(self) -> DetectorInfo:
        return DetectorInfo(name=self.name, available=sys.platform == "win32", priority=self.priority)

    def detect(self) -> PlaybackCandidate | None:
        title = get_active_window_title()
        if not title:
            return None
        normalized = normalize(title)
        looks_like_player = any(marker in title.lower() for marker in PLAYER_MARKERS)
        if not looks_like_player and normalized.episode is None:
            return None
        return PlaybackCandidate(
            source=self.name,
            raw_title=title,
            anime_title=normalized.anime_title,
            season=normalized.season,
            episode=normalized.episode.number if normalized.episode else None,
            episode_type=normalized.episode.type if normalized.episode else None,
            confidence=normalized.confidence,
        )
