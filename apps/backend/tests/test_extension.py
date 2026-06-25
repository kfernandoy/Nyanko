import hashlib
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from nyanko_api.config import Settings
from nyanko_api.database import Database
from nyanko_api.detectors import BrowserDetector
from nyanko_api.main import (
    app,
    extension_playback_event,
    pair_extension,
    start_extension_pairing,
    _playback_ready_for_auto_confirm,
)
from nyanko_api.models import PlaybackPreferences
from nyanko_api.models import ExtensionPairRequest, ExtensionPlaybackEvent, PlaybackMatchRequest


@pytest.fixture
def database(monkeypatch):
    database = Database(Path(":memory:"))
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row

    @contextmanager
    def connect():
        yield connection
        connection.commit()

    monkeypatch.setattr(database, "connect", connect)
    database.initialize()
    return database


def test_pairing_is_one_time_and_creates_valid_token(database):
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(instance_token="instance-secret"))
    )
    pairing = start_extension_pairing(request, "instance-secret", database, Settings())
    token = pair_extension(
        ExtensionPairRequest(code=pairing.code, label="Firefox"), database
    )

    assert database.validate_extension_token(
        hashlib.sha256(token.token.encode()).hexdigest()
    )
    with pytest.raises(HTTPException):
        pair_extension(ExtensionPairRequest(code=pairing.code, label="Replay"), database)


def test_pairing_requires_instance_token(database):
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(instance_token="expected"))
    )

    with pytest.raises(HTTPException):
        start_extension_pairing(
            request,
            "wrong",
            database,
            Settings(),
        )


def test_authenticated_extension_event_reaches_browser_detector():
    detector = BrowserDetector()
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(browser_detector=detector))
    )

    extension_playback_event(
        ExtensionPlaybackEvent(
            raw_title="Page player title",
            page_url="https://example.test/watch/12",
            position_seconds=120,
            duration_seconds=1440,
            paused=False,
            anime_title="Frieren",
            season=2,
            episode=12,
            content_kind="episode",
            site_adapter="crunchyroll",
        ),
        request,
        "authenticated",
    )

    candidate = detector.detect()
    assert candidate is not None
    assert candidate.source == "browser"
    assert candidate.anime_title == "Frieren"
    assert candidate.season == 2
    assert candidate.episode == 12
    assert candidate.position_seconds == 120
    assert candidate.site_adapter == "crunchyroll"


def test_cors_accepts_extensions_but_not_web_pages():
    client = TestClient(app)
    headers = {
        "Origin": "chrome-extension://abcdefghijklmnop",
        "Access-Control-Request-Method": "POST",
    }

    allowed = client.options("/api/extension/pair", headers=headers)
    denied = client.options(
        "/api/extension/pair",
        headers={**headers, "Origin": "https://example.com"},
    )

    assert allowed.headers["access-control-allow-origin"] == headers["Origin"]
    assert "access-control-allow-origin" not in denied.headers


def test_browser_auto_confirm_waits_for_real_progress():
    started = PlaybackMatchRequest(
        source="browser",
        raw_title="Frieren Episode 12",
        episode=12,
        content_kind="episode",
        position_seconds=120,
        duration_seconds=1440,
    )
    almost_done = started.model_copy(update={"position_seconds": 1380})

    prefs = PlaybackPreferences(auto_confirm=True, progress_policy="end")
    assert not _playback_ready_for_auto_confirm(started, prefs)
    assert _playback_ready_for_auto_confirm(almost_done, prefs)
