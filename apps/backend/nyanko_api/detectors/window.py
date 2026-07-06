import ctypes
import sys
from ctypes import wintypes

from ..models import PlaybackCandidate
from ..normalizer import normalize
from .base import Detector, DetectorInfo


PLAYER_MARKERS = ("vlc media player", "mpv", "mpc-hc", "potplayer")
# Browsers carry the extension; their OS window title is browser chrome ("… — Mozilla
# Firefox", other-tab counts), never a clean anime title, so the window detector must
# skip them and let the extension be the source.
BROWSER_MARKERS = (
    "mozilla firefox",
    "google chrome",
    "chromium",
    "microsoft edge",
    "brave",
    "opera",
    "vivaldi",
    "librewolf",
    "waterfox",
    "tor browser",
    "zen browser",
)


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
        lowered = title.lower()
        if any(marker in lowered for marker in BROWSER_MARKERS):
            return None
        normalized = normalize(title)
        looks_like_player = any(marker in lowered for marker in PLAYER_MARKERS)
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


# Known desktop media players, by executable basename (lowercased). Taiga-style:
# we read the window title of whichever of these is running, with no per-player
# configuration. Browsers are intentionally absent — the extension handles those.
PLAYER_EXECUTABLES = frozenset(
    {
        "mpv.exe",
        "mpvnet.exe",
        "mpc-hc.exe",
        "mpc-hc64.exe",
        "mpc-be.exe",
        "mpc-be64.exe",
        "mpc-qt.exe",
        "vlc.exe",
        "potplayer.exe",
        "potplayermini.exe",
        "potplayermini64.exe",
        "smplayer.exe",
        "kmplayer.exe",
        "gom.exe",
        "wmplayer.exe",
        "mpc-hc-clsid.exe",
    }
)

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


def _process_executable(pid: int) -> str:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ""
    try:
        size = wintypes.DWORD(260)
        buffer = ctypes.create_unicode_buffer(size.value)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return buffer.value
        return ""
    finally:
        kernel32.CloseHandle(handle)


def iter_player_windows() -> list[tuple[str, str]]:
    """(exe_basename, window_title) for every visible window of a known media player.

    Scans all top-level windows (not just the foreground one) so detection works
    even when the player isn't focused — the way Taiga does it.
    """
    if sys.platform != "win32":
        return []
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    results: list[tuple[str, str]] = []
    enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def callback(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        title = buffer.value.strip()
        if not title:
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        executable = _process_executable(pid.value)
        if executable:
            base = executable.replace("/", "\\").rsplit("\\", 1)[-1].lower()
            if base in PLAYER_EXECUTABLES:
                results.append((base, title))
        return True

    user32.EnumWindows(enum_proc(callback), 0)
    return results


def _candidate_from_player_windows(
    windows: list[tuple[str, str]], source: str
) -> PlaybackCandidate | None:
    """Pick the best playback candidate from scanned player windows.

    Prefer a window whose title parses to an episode; fall back to one that at least
    yields an anime title (e.g. a movie with no episode number).
    """
    fallback: PlaybackCandidate | None = None
    for _base, title in windows:
        candidate = parse_media_title(title, source=source)
        if candidate.episode is not None:
            return candidate
        if fallback is None and candidate.anime_title:
            fallback = candidate
    return fallback


class MediaPlayerWindowDetector(Detector):
    """No-config detection for any desktop player by scanning window titles (Taiga-style)."""

    name = "media-window"
    priority = 12

    def info(self) -> DetectorInfo:
        return DetectorInfo(name=self.name, available=sys.platform == "win32", priority=self.priority)

    def detect(self) -> PlaybackCandidate | None:
        return _candidate_from_player_windows(iter_player_windows(), self.name)
