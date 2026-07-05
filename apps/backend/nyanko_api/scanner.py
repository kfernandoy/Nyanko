from __future__ import annotations

import os
import re
from collections.abc import Iterator
from pathlib import Path

from .normalizer import normalize

VIDEO_EXTENSIONS = frozenset(
    ".mkv .mp4 .avi .webm .mov .ts .m2ts .wmv .flv .ogm .mpg .mpeg".split()
)

# Folders that hold episodes but aren't the series itself — skip them when falling
# back to the parent folder for a title (the series name is one level up).
_SEASON_DIR = re.compile(
    r"^(?:season\s*\d+|s\d+|cour\s*\d+|part\s*\d+|\d+(?:st|nd|rd|th)?\s*season|specials?|extras?|ova|movies?)$",
    re.IGNORECASE,
)


def iter_video_files(folders: list[dict]) -> Iterator[str]:
    """Yield absolute paths of video files across the configured folders.

    Each folder is ``{"path": str, "recursive": bool}``. Missing or unreadable
    folders are skipped silently — a removed drive shouldn't abort the scan.
    """
    seen: set[str] = set()
    for folder in folders:
        root = folder.get("path")
        if not root or not os.path.isdir(root):
            continue
        recursive = bool(folder.get("recursive", True))
        if recursive:
            for dirpath, _dirs, files in os.walk(root):
                for name in files:
                    yield from _emit(os.path.join(dirpath, name), seen)
        else:
            try:
                entries = os.scandir(root)
            except OSError:
                continue
            with entries:
                for entry in entries:
                    if entry.is_file():
                        yield from _emit(entry.path, seen)


def _emit(path: str, seen: set[str]) -> Iterator[str]:
    if Path(path).suffix.lower() in VIDEO_EXTENSIONS and path not in seen:
        seen.add(path)
        yield path


def _title_from_folders(path: Path) -> str | None:
    """Series title from the folder tree, for files named only by episode number
    (``Series/01.mkv`` or ``Series/Season 1/01.mkv``)."""
    for parent in path.parents:
        name = parent.name
        if not name:
            break
        if _SEASON_DIR.match(name.strip()):
            continue
        return normalize(name).anime_title or name
    return None


def parse_file(path: str) -> tuple[str | None, int | None]:
    """Parse a filename into (anime_title, episode) using the shared normalizer.

    When the filename carries no title (bare ``01.mkv`` inside a per-series folder),
    fall back to the series folder name — the same convention Taiga uses.
    """
    p = Path(path)
    normalized = normalize(p.stem)
    episode = normalized.episode.number if normalized.episode else None
    title = normalized.anime_title or _title_from_folders(p)
    return title, episode
