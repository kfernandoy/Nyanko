from __future__ import annotations

import asyncio
import sys
from typing import Any

from ..models import PlaybackCandidate
from ..normalizer import normalize
from .base import Detector, DetectorInfo, looks_finished


class SmtcDetector(Detector):
    """Windows System Media Transport Controls fallback detector.

    Reads metadata published by any media player that integrates with the Windows
    media overlay. It is intentionally lower priority than dedicated player
    detectors because the metadata is less structured than filenames or player
    IPC.
    """

    name = "smtc"
    priority = 15

    def __init__(self) -> None:
        self._winsdk: Any | None = None
        self._manager: Any | None = None
        try:
            from winsdk.windows.media.control import (  # type: ignore[import-not-found]
                GlobalSystemMediaTransportControlsSessionManager,
            )

            self._winsdk = GlobalSystemMediaTransportControlsSessionManager
        except Exception:
            self._winsdk = None

    def info(self) -> DetectorInfo:
        return DetectorInfo(
            name=self.name,
            available=sys.platform == "win32" and self._winsdk is not None,
            priority=self.priority,
        )

    def detect(self) -> PlaybackCandidate | None:
        if self._winsdk is None or sys.platform != "win32":
            return None
        try:
            return asyncio.run(self._detect_async())
        except Exception:
            return None

    async def _detect_async(self) -> PlaybackCandidate | None:
        manager = await self._get_manager()
        if manager is None:
            return None
        session = manager.get_current_session()
        if session is None:
            sessions = manager.get_sessions()
            if sessions is not None and sessions.size > 0:
                session = sessions[0]
        if session is None:
            return None

        properties = await session.try_get_media_properties_async()
        if properties is None:
            return None
        title = properties.title or ""
        artist = properties.artist or ""
        if not title:
            return None

        timeline = session.get_timeline_properties()
        position_seconds = None
        duration_seconds = None
        if timeline is not None:
            try:
                position = timeline.position
                duration = timeline.end_time
                position_seconds = position.total_seconds() if position else None
                duration_seconds = duration.total_seconds() if duration else None
            except Exception:
                pass

        playback = session.get_playback_info()
        paused = None
        if playback is not None:
            try:
                paused = playback.playback_status.name == "PAUSED"
            except Exception:
                pass

        raw_title = title
        if artist and artist.lower() not in title.lower():
            raw_title = f"{artist} - {title}"
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
            confidence=normalized.confidence,
            position_seconds=position_seconds,
            duration_seconds=duration_seconds,
            paused=paused,
            finished=looks_finished(position_seconds, duration_seconds),
        )

    async def _get_manager(self) -> Any | None:
        if self._manager is not None:
            return self._manager
        try:
            self._manager = await self._winsdk.request_async()
        except Exception:
            self._manager = None
        return self._manager
