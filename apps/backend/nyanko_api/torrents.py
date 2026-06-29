"""Parseo de feeds RSS de torrents (estilo Nyaa) y motor de filtros.

Lógica pura: no hace I/O salvo el cliente httpx que se le inyecta. Reutiliza el
normalizer del proyecto para extraer título/episodio del nombre del torrent.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from xml.etree import ElementTree as ET

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
            )
        )
    return parsed
