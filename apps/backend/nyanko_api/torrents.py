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


_ELEMENT_GETTERS = {
    "filename": lambda p: p.filename or p.raw_title,
    "title": lambda p: p.title or p.raw_title,
    "group": lambda p: p.group or "",
    "resolution": lambda p: p.resolution or "",
    "episode": lambda p: p.episode,
    "size": lambda p: p.size or "",
    "seeders": lambda p: p.seeders,
}
_NUMERIC_ELEMENTS = {"episode", "seeders"}
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


def _size_to_bytes(text: str) -> float | None:
    m = re.match(r"\s*([\d.]+)\s*([KMGT]?i?B)\b", text or "", re.IGNORECASE)
    if not m:
        return None
    units = {"B": 1, "KIB": 1024, "MIB": 1024**2, "GIB": 1024**3, "TIB": 1024**4,
             "KB": 1000, "MB": 1000**2, "GB": 1000**3, "TB": 1000**4}
    return float(m.group(1)) * units.get(m.group(2).upper(), 1)


def _op(operator: str, field_value, target: str, element: str) -> bool:
    if operator in ("gt", "lt"):
        if element == "size":
            number = _size_to_bytes(str(field_value)); bound = _size_to_bytes(target)
        else:
            try:
                number = float(field_value) if field_value is not None else None
                bound = float(target)
            except (TypeError, ValueError):
                return False
        if number is None or bound is None:
            return False
        return number > bound if operator == "gt" else number < bound
    text = ("" if field_value is None else str(field_value)).casefold()
    needle = target.casefold()
    if operator in ("is", "equals"):
        return text == needle
    if operator in ("is_not", "not_equals"):
        return text != needle
    if operator == "contains":
        return needle in text
    if operator == "not_contains":
        return needle not in text
    if operator == "begins_with":
        return text.startswith(needle)
    if operator == "ends_with":
        return text.endswith(needle)
    if operator == "regex":
        try:
            return re.search(target, str(field_value or ""), re.IGNORECASE) is not None
        except re.error:
            return False
    return False


def _condition_true(parsed: ParsedTorrent, cond: dict) -> bool:
    getter = _ELEMENT_GETTERS.get(cond["element"])
    if getter is None:
        return False
    return _op(cond["operator"], getter(parsed), cond["value"], cond["element"])


def _filter_applies(filt: dict, media_id: int | None) -> bool:
    if filt.get("scope", "all") != "limited":
        return True
    return media_id is not None and media_id in set(filt.get("anime_ids") or [])


def _filter_matches(parsed: ParsedTorrent, filt: dict) -> bool:
    conds = filt.get("conditions") or []
    if not conds:
        return False
    if filt.get("match", "all") == "any":
        return any(_condition_true(parsed, c) for c in conds)
    return all(_condition_true(parsed, c) for c in conds)


def build_feed(
    parsed_items: list[ParsedTorrent],
    library: list[MediaItem],
    filters: list[dict],
    seen: set[str],
    discarded: set[str],
    *,
    filters_enabled: bool = True,
    globals_: dict | None = None,
    min_confidence: float = 0.6,
    preferred_resolution: str | None = None,
) -> list[FeedItem]:
    g = globals_ or {}
    index = build_token_index(library)
    by_id = {item.id: item for item in library}
    active = [f for f in filters if f.get("enabled", True)] if filters_enabled else []
    results: list[tuple[int, FeedItem]] = []
    for parsed in parsed_items:
        sig = signature(parsed.source_id, parsed.guid)
        if sig in discarded:
            continue
        match, score = match_from_index(parsed.title, index, min_score=min_confidence)
        media_id = match.id if match else None
        applicable = [f for f in active if _filter_applies(f, media_id) and _filter_matches(parsed, f)]
        if any(f["action"] == "discard" for f in applicable):
            continue
        selected = any(f["action"] == "select" for f in applicable)
        if not selected:
            if g.get("discard_not_in_list") and match is None:
                continue
            if g.get("discard_seen") and match is not None:
                entry = by_id[match.id]
                fresh = parsed.episode is not None and parsed.episode > entry.progress
                if not (entry.status in _WATCHING_STATUSES and fresh):
                    continue
        prefer_rank = sum(1 for f in applicable if f["action"] == "prefer")
        results.append((
            prefer_rank,
            FeedItem(
                signature=sig, raw_title=parsed.raw_title, link=parsed.link,
                media_id=media_id, media_title=match.title if match else None,
                episode=parsed.episode, resolution=parsed.resolution, group=parsed.group,
                seeders=parsed.seeders, size=parsed.size, description=parsed.description,
                filename=parsed.filename, torrent_date=parsed.torrent_date,
                confidence=score, is_new=sig not in seen,
            ),
        ))
    pref_res = preferred_resolution if g.get("prefer_resolution") else None
    results.sort(key=lambda r: (
        -r[0],
        0 if (pref_res and r[1].resolution == pref_res) else 1,
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
