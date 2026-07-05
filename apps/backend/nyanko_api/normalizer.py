from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache


# Tags and metadata commonly added by release groups.
TAG_PATTERNS = (
    re.compile(r"\[[^\]]+\]"),
    re.compile(r"\{[^}]+\}"),
    re.compile(r"\([^)]*\d+\s*[pk]\s*[^)]*\)", re.IGNORECASE),
    re.compile(r"\([^)]*(?:x264|x265|hevc|h264|h265|av1|hdr|sdr)[^)]*\)", re.IGNORECASE),
)

CODEC_KEYWORDS = frozenset(
    "x264 x265 hevc h264 h265 av1 avc aac ac3 dts flac opus mp3".split()
)
RESOLUTION_KEYWORDS = frozenset("480p 720p 1080p 1440p 2160p 4k uhd hdr sdr".split())
CONTAINER_KEYWORDS = frozenset("mkv mp4 avi webm mov ts m2ts".split())
CHECKSUM_PATTERN = re.compile(r"\b[0-9a-f]{8}\b|\b[0-9a-f]{32}\b", re.IGNORECASE)
VERSION_PATTERN = re.compile(r"\bv\d+\b", re.IGNORECASE)

PLAYER_PATTERNS = (
    re.compile(r"\s+[-–—]\s+(VLC media player|mpv|MPC-HC|PotPlayer)\s*$", re.IGNORECASE),
    re.compile(r"\s+[-–—]\s+(Crunchyroll|YouTube|Netflix|Google Chrome|Mozilla Firefox|Microsoft Edge)\s*$", re.IGNORECASE),
)

def airing_season_from_date(date_str: str | None) -> str | None:
    """Temporada de emisión (WINTER/SPRING/SUMMER/FALL) a partir de YYYY-MM-DD."""
    if not date_str or len(date_str) < 7 or not date_str[5:7].isdigit():
        return None
    month = int(date_str[5:7])
    if not 1 <= month <= 12:
        return None
    return ("WINTER", "SPRING", "SUMMER", "FALL")[(month - 1) // 3]


SEASON_PATTERNS = (
    re.compile(r"\bS(\d{1,2})\b", re.IGNORECASE),
    re.compile(r"\bSeason\s*(\d{1,2})\b", re.IGNORECASE),
    re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)\s+Season\b", re.IGNORECASE),
)

SEASON_EPISODE_PATTERN = re.compile(r"\bS(\d{1,2})E(\d{1,4})\b", re.IGNORECASE)
EPISODE_PATTERNS = (
    re.compile(r"\b(?:Episode|Episodio|Ep)\s*[._-]?\s*(\d{1,4})\b", re.IGNORECASE),
    re.compile(r"\b(?:Special|OVA|ONA)\s*[._-]?\s*(\d{1,4})\b", re.IGNORECASE),
    re.compile(r"(?:^|[-–—]\s|\s)(\d{1,4})\s*$", re.IGNORECASE),
)


@dataclass(frozen=True, slots=True)
class EpisodeInfo:
    number: int | None = None
    type: str = "regular"  # regular, double, special, ova, ona, absolute
    raw_label: str | None = None


@dataclass(frozen=True, slots=True)
class NormalizedTitle:
    raw_title: str
    anime_title: str | None
    season: int | None
    episode: EpisodeInfo | None
    confidence: float


def _remove_tags(raw: str) -> str:
    cleaned = raw
    for pattern in TAG_PATTERNS:
        cleaned = pattern.sub(" ", cleaned)
    cleaned = CHECKSUM_PATTERN.sub(" ", cleaned)
    cleaned = VERSION_PATTERN.sub(" ", cleaned)
    return cleaned


def _remove_metadata_words(cleaned: str) -> str:
    words = []
    for word in re.split(r"[ ._]+", cleaned):
        lower = word.lower()
        if (
            lower in CODEC_KEYWORDS
            or lower in RESOLUTION_KEYWORDS
            or lower in CONTAINER_KEYWORDS
            or lower in ("hd", "sd", "bluray", "bd", "dvd", "web", "tv", "batch")
        ):
            continue
        words.append(word)
    return " ".join(words)


def _remove_player_suffixes(title: str) -> str:
    for pattern in PLAYER_PATTERNS:
        title = pattern.sub("", title)
    return title


def _extract_season_episode(title: str) -> tuple[str, int | None, int | None]:
    match = SEASON_EPISODE_PATTERN.search(title)
    if match:
        season = int(match.group(1))
        episode = int(match.group(2))
        cleaned = title[: match.start()] + title[match.end() :]
        return cleaned.strip(" -–—_."), season, episode
    return title, None, None


def _extract_season(title: str) -> tuple[str, int | None]:
    for pattern in SEASON_PATTERNS:
        match = pattern.search(title)
        if match:
            season = int(match.group(1))
            cleaned = title[: match.start()] + title[match.end() :]
            return cleaned.strip(" -–—_."), season
    return title, None


def _extract_episode(title: str) -> tuple[str, EpisodeInfo | None]:
    for pattern in EPISODE_PATTERNS:
        match = pattern.search(title)
        if match:
            number = int(match.group(1))
            raw_label = match.group(0).strip()
            lower_raw = raw_label.lower()
            if "ova" in lower_raw:
                episode_type = "ova"
            elif "ona" in lower_raw:
                episode_type = "ona"
            elif "special" in lower_raw:
                episode_type = "special"
            elif number >= 100 and not re.search(r"episode|ep|episodio", lower_raw):
                episode_type = "absolute"
            else:
                episode_type = "regular"
            cleaned = title[: match.start()] + title[match.end() :]
            return cleaned.strip(" -–—_."), EpisodeInfo(number=number, type=episode_type, raw_label=raw_label)
    return title, None


def _calculate_confidence(title: str | None, episode: EpisodeInfo | None) -> float:
    if not title:
        return 0.0
    confidence = 0.5
    if episode is not None and episode.number is not None:
        confidence += 0.4
    if len(title) >= 3:
        confidence += 0.05
    if not re.search(r"\d{4,}", title):
        confidence += 0.05
    return min(1.0, confidence)


def clean_filename(raw: str) -> str:
    """Remove file extension, release tags, codec/resolution metadata and checksums."""
    cleaned = re.sub(r"\.[a-zA-Z0-9]{2,4}$", "", raw)
    cleaned = _remove_tags(cleaned)
    cleaned = _remove_metadata_words(cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


# Alias used by match-correction keys to stay stable across minor title variants.
normalize_title = clean_filename


_FOLD_PATTERN = re.compile(r"[\W_]+", re.UNICODE)


def fold_title(value: str) -> str:
    """Forma de comparación insensible a símbolos: minúsculas y puntuación/underscore
    colapsados a un espacio. Los nombres de archivo de Windows no admiten `/ \\ : * ?`,
    así que 'Fate/stay night' y 'Fate stay night' deben compararse iguales."""
    return _FOLD_PATTERN.sub(" ", value.casefold()).strip()


@lru_cache(maxsize=32768)
def folded_title(value: str) -> str:
    """fold_title(normalize_title(...)) cacheado: los títulos de la biblioteca son
    estables y normalizarlos con regex en cada búsqueda costaba ~1.5 s por consulta."""
    return fold_title(clean_filename(value))


def normalize(raw: str) -> NormalizedTitle:
    """Normalize a raw media filename or window title into structured data."""
    cleaned = clean_filename(raw)
    cleaned = _remove_player_suffixes(cleaned)

    title, season, episode_number = _extract_season_episode(cleaned)
    if season is None:
        title, season = _extract_season(title)

    if episode_number is not None:
        episode = EpisodeInfo(number=episode_number, type="regular", raw_label=f"S{season:02d}E{episode_number:02d}" if season else f"E{episode_number:02d}")
    else:
        title, episode = _extract_episode(title)

    title = re.sub(r"\s+", " ", title).strip(" -–—_.")
    anime_title = title if title else None
    confidence = _calculate_confidence(anime_title, episode)

    return NormalizedTitle(
        raw_title=raw,
        anime_title=anime_title,
        season=season,
        episode=episode,
        confidence=confidence,
    )
