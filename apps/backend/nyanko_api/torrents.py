"""Parseo de feeds RSS de torrents (estilo Nyaa) y motor de filtros.

Lógica pura: no hace I/O salvo el cliente httpx que se le inyecta. Reutiliza el
normalizer del proyecto para extraer título/episodio del nombre del torrent.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from xml.etree import ElementTree as ET

from .matcher import build_token_index, match_from_index
from .models import MediaItem
from .normalizer import normalize

_GROUP_RE = re.compile(r"^\s*\[([^\]]+)\]")
_RES_RE = re.compile(r"\b(480|720|1080|2160)p\b", re.IGNORECASE)


@dataclass(slots=True)
class ParsedTorrent:
    raw_title: str
    link: str
    guid: str
    source_id: int
    title: str | None
    episode: int | None
    group: str | None
    resolution: str | None
    seeders: int | None
    size: str | None = None
    description: str | None = None
    filename: str | None = None
    torrent_date: str | None = None


def extract_group(raw_title: str) -> str | None:
    match = _GROUP_RE.search(raw_title)
    return match.group(1).strip() if match else None


def extract_resolution(raw_title: str) -> str | None:
    match = _RES_RE.search(raw_title)
    return f"{match.group(1)}p" if match else None


def signature(source_id: int, guid: str) -> str:
    return hashlib.sha1(f"{source_id}:{guid}".encode("utf-8")).hexdigest()


def _text(item: ET.Element, tag: str) -> str | None:
    # Soporta tags con y sin namespace (nyaa:seeders -> local name 'seeders').
    for child in item:
        local = child.tag.rsplit("}", 1)[-1]
        if local == tag:
            return (child.text or "").strip() or None
    return None


_FIELD_GETTERS = {
    "group": lambda p: p.group or "",
    "resolution": lambda p: p.resolution or "",
    "title": lambda p: p.title or p.raw_title,
    "episode": lambda p: p.episode,
}
_WATCHING_STATUSES = {"CURRENT", "REPEATING"}


@dataclass(slots=True)
class FeedItem:
    signature: str
    raw_title: str
    link: str
    media_id: int | None
    media_title: str | None
    episode: int | None
    resolution: str | None
    group: str | None
    seeders: int | None
    size: str | None = None
    description: str | None = None
    filename: str | None = None
    torrent_date: str | None = None
    confidence: float = 0.0
    is_new: bool = False


def _match_op(op: str, field_value, target: str) -> bool:
    if op in ("gt", "lt"):
        try:
            number = int(field_value) if field_value is not None else None
            bound = int(target)
        except (TypeError, ValueError):
            return False
        if number is None:
            return False
        return number > bound if op == "gt" else number < bound
    text = ("" if field_value is None else str(field_value)).casefold()
    needle = target.casefold()
    if op == "contains":
        return needle in text
    if op == "not_contains":
        return needle not in text
    if op == "equals":
        return text == needle
    if op == "regex":
        try:
            return re.search(target, str(field_value or ""), re.IGNORECASE) is not None
        except re.error:
            return False
    return False


def _rule_matches(parsed: ParsedTorrent, rule: dict) -> bool:
    getter = _FIELD_GETTERS.get(rule["field"])
    if getter is None:
        return False
    return _match_op(rule["op"], getter(parsed), rule["value"])


def passes_filters(parsed: ParsedTorrent, filters: list[dict]) -> bool:
    """False solo si una regla `exclude` activa coincide. `include`/`prefer` no excluyen."""
    for rule in filters:
        if not rule.get("enabled", 1):
            continue
        if rule["action"] == "exclude" and _rule_matches(parsed, rule):
            return False
    return True


def _forced_include(parsed: ParsedTorrent, filters: list[dict]) -> bool:
    return any(
        rule.get("enabled", 1) and rule["action"] == "include" and _rule_matches(parsed, rule)
        for rule in filters
    )


def _prefer_rank(parsed: ParsedTorrent, filters: list[dict]) -> int:
    return sum(
        1 for rule in filters
        if rule.get("enabled", 1) and rule["action"] == "prefer" and _rule_matches(parsed, rule)
    )


def build_feed(
    parsed_items: list[ParsedTorrent],
    library: list[MediaItem],
    filters: list[dict],
    seen: set[str],
    discarded: set[str],
    min_confidence: float = 0.6,
    preferred_resolution: str | None = None,
) -> list[FeedItem]:
    index = build_token_index(library)
    by_id = {item.id: item for item in library}
    results: list[tuple[int, FeedItem]] = []
    for parsed in parsed_items:
        sig = signature(parsed.source_id, parsed.guid)
        if sig in discarded:
            continue
        if not passes_filters(parsed, filters):
            continue
        match, score = match_from_index(parsed.title, index, min_score=min_confidence)
        forced = _forced_include(parsed, filters)
        keep = False
        media_id = match.id if match else None
        if match is not None:
            entry = by_id[match.id]
            is_new_episode = parsed.episode is not None and parsed.episode > entry.progress
            keep = entry.status in _WATCHING_STATUSES and is_new_episode
        if forced:
            keep = True
        if not keep:
            continue
        results.append((
            _prefer_rank(parsed, filters),
            FeedItem(
                signature=sig,
                raw_title=parsed.raw_title,
                link=parsed.link,
                media_id=media_id,
                media_title=match.title if match else None,
                episode=parsed.episode,
                resolution=parsed.resolution,
                group=parsed.group,
                seeders=parsed.seeders,
                size=parsed.size,
                description=parsed.description,
                filename=parsed.filename,
                torrent_date=parsed.torrent_date,
                confidence=score,
                is_new=sig not in seen,
            ),
        ))
    # prefer primero; luego preferred_resolution como desempate; dentro, nuevos antes y mayor seeders.
    results.sort(key=lambda r: (
        -r[0],
        0 if (preferred_resolution and r[1].resolution == preferred_resolution) else 1,
        not r[1].is_new,
        -(r[1].seeders or 0),
    ))
    return [item for _, item in results]


def parse_feed(xml_text: str, source_id: int) -> list[ParsedTorrent]:
    root = ET.fromstring(xml_text)
    parsed: list[ParsedTorrent] = []
    for item in root.iter("item"):
        raw_title = _text(item, "title") or ""
        link = _text(item, "link") or ""
        guid = _text(item, "guid") or link
        if not raw_title or not link:
            continue
        norm = normalize(raw_title)
        seeders_raw = _text(item, "seeders")
        seeders = int(seeders_raw) if seeders_raw and seeders_raw.isdigit() else None
        parsed.append(
            ParsedTorrent(
                raw_title=raw_title,
                link=link,
                guid=guid,
                source_id=source_id,
                title=norm.anime_title,
                episode=norm.episode.number if norm.episode else None,
                group=extract_group(raw_title),
                resolution=extract_resolution(raw_title),
                seeders=seeders,
                size=_text(item, "size"),
                description=_text(item, "description"),
                filename=raw_title,
                torrent_date=_text(item, "pubDate"),
            )
        )
    return parsed
