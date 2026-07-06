"""Canonical mappings and conversions for multi-provider support.

Nyanko keeps a provider-neutral model. This module converts status, format and
score values between the canonical form and each supported provider, preserving
the original value when a round-trip would lose precision.
"""

from __future__ import annotations

from enum import StrEnum


class CanonicalStatus(StrEnum):
    CURRENT = "CURRENT"
    PLANNING = "PLANNING"
    COMPLETED = "COMPLETED"
    PAUSED = "PAUSED"
    DROPPED = "DROPPED"
    REPEATING = "REPEATING"


class CanonicalFormat(StrEnum):
    TV = "TV"
    TV_SHORT = "TV_SHORT"
    MOVIE = "MOVIE"
    SPECIAL = "SPECIAL"
    OVA = "OVA"
    ONA = "ONA"
    MUSIC = "MUSIC"
    MANGA = "MANGA"
    NOVEL = "NOVEL"
    ONE_SHOT = "ONE_SHOT"
    UNKNOWN = "UNKNOWN"


class ScoreFormat(StrEnum):
    POINT_100 = "POINT_100"
    POINT_10_DECIMAL = "POINT_10_DECIMAL"
    POINT_10 = "POINT_10"
    POINT_5 = "POINT_5"
    POINT_3 = "POINT_3"


_STATUS_TO_CANONICAL: dict[str, dict[str, CanonicalStatus]] = {
    "anilist": {
        "CURRENT": CanonicalStatus.CURRENT,
        "PLANNING": CanonicalStatus.PLANNING,
        "COMPLETED": CanonicalStatus.COMPLETED,
        "PAUSED": CanonicalStatus.PAUSED,
        "DROPPED": CanonicalStatus.DROPPED,
        "REPEATING": CanonicalStatus.REPEATING,
    },
    "mal": {
        "watching": CanonicalStatus.CURRENT,
        "reading": CanonicalStatus.CURRENT,
        "completed": CanonicalStatus.COMPLETED,
        "on_hold": CanonicalStatus.PAUSED,
        "dropped": CanonicalStatus.DROPPED,
        "plan_to_watch": CanonicalStatus.PLANNING,
        "plan_to_read": CanonicalStatus.PLANNING,
    },
}

_STATUS_FROM_CANONICAL: dict[str, dict[CanonicalStatus, str]] = {
    "anilist": {
        CanonicalStatus.CURRENT: "CURRENT",
        CanonicalStatus.PLANNING: "PLANNING",
        CanonicalStatus.COMPLETED: "COMPLETED",
        CanonicalStatus.PAUSED: "PAUSED",
        CanonicalStatus.DROPPED: "DROPPED",
        CanonicalStatus.REPEATING: "REPEATING",
    },
    "mal": {
        CanonicalStatus.CURRENT: "watching",
        CanonicalStatus.PLANNING: "plan_to_watch",
        CanonicalStatus.COMPLETED: "completed",
        CanonicalStatus.PAUSED: "on_hold",
        CanonicalStatus.DROPPED: "dropped",
        # MyAnimeList has no REPEATING state; it tracks rewatches via num_times_rewatched.
        CanonicalStatus.REPEATING: "watching",
    },
}

_FORMAT_TO_CANONICAL: dict[str, dict[str, CanonicalFormat]] = {
    "anilist": {
        "TV": CanonicalFormat.TV,
        "TV_SHORT": CanonicalFormat.TV_SHORT,
        "MOVIE": CanonicalFormat.MOVIE,
        "SPECIAL": CanonicalFormat.SPECIAL,
        "OVA": CanonicalFormat.OVA,
        "ONA": CanonicalFormat.ONA,
        "MUSIC": CanonicalFormat.MUSIC,
        "MANGA": CanonicalFormat.MANGA,
        "NOVEL": CanonicalFormat.NOVEL,
        "ONE_SHOT": CanonicalFormat.ONE_SHOT,
    },
    "mal": {
        "tv": CanonicalFormat.TV,
        "tv_special": CanonicalFormat.SPECIAL,
        "ona": CanonicalFormat.ONA,
        "ova": CanonicalFormat.OVA,
        "movie": CanonicalFormat.MOVIE,
        "music": CanonicalFormat.MUSIC,
        "special": CanonicalFormat.SPECIAL,
        "manga": CanonicalFormat.MANGA,
        "doujinshi": CanonicalFormat.MANGA,
        "manhwa": CanonicalFormat.MANGA,
        "manhua": CanonicalFormat.MANGA,
        "novel": CanonicalFormat.NOVEL,
        "one_shot": CanonicalFormat.ONE_SHOT,
    },
}

_FORMAT_FROM_CANONICAL: dict[str, dict[CanonicalFormat, str]] = {
    "anilist": {
        CanonicalFormat.TV: "TV",
        CanonicalFormat.TV_SHORT: "TV_SHORT",
        CanonicalFormat.MOVIE: "MOVIE",
        CanonicalFormat.SPECIAL: "SPECIAL",
        CanonicalFormat.OVA: "OVA",
        CanonicalFormat.ONA: "ONA",
        CanonicalFormat.MUSIC: "MUSIC",
        CanonicalFormat.MANGA: "MANGA",
        CanonicalFormat.NOVEL: "NOVEL",
        CanonicalFormat.ONE_SHOT: "ONE_SHOT",
    },
    "mal": {
        CanonicalFormat.TV: "tv",
        CanonicalFormat.MOVIE: "movie",
        CanonicalFormat.SPECIAL: "special",
        CanonicalFormat.OVA: "ova",
        CanonicalFormat.ONA: "ona",
        CanonicalFormat.MUSIC: "music",
        CanonicalFormat.MANGA: "manga",
        CanonicalFormat.NOVEL: "novel",
        CanonicalFormat.ONE_SHOT: "one_shot",
    },
}


def _normalize(value: str | None) -> str:
    return (value or "").strip().upper()


def to_canonical_status(provider: str, value: str | None) -> CanonicalStatus:
    """Convert a provider-specific status to the canonical model."""
    mapping = _STATUS_TO_CANONICAL.get(provider)
    if mapping is None:
        raise ValueError(f"Unknown provider: {provider}")
    canonical = mapping.get(value)
    if canonical is None:
        raise ValueError(f"Unsupported {provider} status: {value}")
    return canonical


def from_canonical_status(provider: str, status: CanonicalStatus | str) -> str:
    """Convert a canonical status to the provider-specific value."""
    if isinstance(status, str):
        status = CanonicalStatus(_normalize(status))
    mapping = _STATUS_FROM_CANONICAL.get(provider)
    if mapping is None:
        raise ValueError(f"Unknown provider: {provider}")
    provider_value = mapping.get(status)
    if provider_value is None:
        raise ValueError(f"Unsupported canonical status for {provider}: {status}")
    return provider_value


def to_canonical_format(provider: str, value: str | None) -> CanonicalFormat:
    """Convert a provider-specific format to the canonical model."""
    if not value:
        return CanonicalFormat.UNKNOWN
    mapping = _FORMAT_TO_CANONICAL.get(provider)
    if mapping is None:
        raise ValueError(f"Unknown provider: {provider}")
    canonical = mapping.get(value)
    if canonical is None:
        canonical = mapping.get(value.lower())
    return canonical if canonical is not None else CanonicalFormat.UNKNOWN


def from_canonical_format(provider: str, format_value: CanonicalFormat | str) -> str | None:
    """Convert a canonical format to the provider-specific value."""
    if isinstance(format_value, str):
        format_value = CanonicalFormat(_normalize(format_value))
    if format_value == CanonicalFormat.UNKNOWN:
        return None
    mapping = _FORMAT_FROM_CANONICAL.get(provider)
    if mapping is None:
        raise ValueError(f"Unknown provider: {provider}")
    provider_value = mapping.get(format_value)
    if provider_value is None:
        raise ValueError(f"Unsupported canonical format for {provider}: {format_value}")
    return provider_value


def _to_point_100(value: float, from_format: ScoreFormat) -> float:
    if from_format == ScoreFormat.POINT_100:
        return float(value)
    if from_format == ScoreFormat.POINT_10_DECIMAL:
        return value * 10
    if from_format == ScoreFormat.POINT_10:
        return value * 10
    if from_format == ScoreFormat.POINT_5:
        return value * 20
    if from_format == ScoreFormat.POINT_3:
        if value == 0:
            return 0
        # Common 3-point mapping: 1 = 33, 2 = 66, 3 = 100.
        return value * 33 + 1
    raise ValueError(f"Unknown score format: {from_format}")


def _from_point_100(value: float, to_format: ScoreFormat) -> float:
    if to_format == ScoreFormat.POINT_100:
        return value
    if to_format == ScoreFormat.POINT_10_DECIMAL:
        return round(value / 10, 1)
    if to_format == ScoreFormat.POINT_10:
        return round(value / 10)
    if to_format == ScoreFormat.POINT_5:
        return round(value / 20)
    if to_format == ScoreFormat.POINT_3:
        if value == 0:
            return 0
        # Reverse common 3-point mapping.
        if value >= 90:
            return 3
        if value >= 55:
            return 2
        return 1
    raise ValueError(f"Unknown score format: {to_format}")


def convert_score(
    value: float | None,
    from_format: ScoreFormat | str,
    to_format: ScoreFormat | str,
) -> float | None:
    """Convert a score between two provider formats.

    Returns None when the input is None or zero (treated as unset).
    """
    if value is None or value == 0:
        return None
    if isinstance(from_format, str):
        from_format = ScoreFormat(from_format)
    if isinstance(to_format, str):
        to_format = ScoreFormat(to_format)
    if from_format == to_format:
        return float(value)
    point_100 = _to_point_100(value, from_format)
    return _from_point_100(point_100, to_format)
