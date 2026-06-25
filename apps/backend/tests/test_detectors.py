import time

from nyanko_api import detectors
from nyanko_api.detectors import BrowserDetector, Detector, DetectorInfo, parse_media_title
from nyanko_api.models import PlaybackCandidate
from nyanko_api.detectors.base import looks_finished
from nyanko_api.detectors.mpc_hc import MpcHcDetector
from nyanko_api.detectors.mpv import MpvDetector
from nyanko_api.detectors.potplayer import PotPlayerDetector
from nyanko_api.detectors.smtc import SmtcDetector
from nyanko_api.detectors.vlc import VlcDetector


def test_parses_episode_label():
    candidate = parse_media_title("Frieren - Episode 12 - VLC media player")
    assert candidate.anime_title == "Frieren"
    assert candidate.episode == 12
    assert candidate.confidence > 0.8


def test_preserves_unknown_title():
    candidate = parse_media_title("Crunchyroll - Google Chrome")
    assert candidate.anime_title == "Crunchyroll"
    assert candidate.episode is None


def test_detection_paused_returns_none(monkeypatch):
    from nyanko_api.detectors import pause

    monkeypatch.setattr(pause, "_detection_paused", False)
    monkeypatch.setattr(detectors.window, "get_active_window_title", lambda: "Frieren - Episode 12 - VLC media player")

    manager = detectors.DetectorManager()
    manager.register(detectors.ActiveWindowDetector())
    assert manager.detect() is not None

    detectors.set_detection_paused(True)
    assert manager.detect() is None

    detectors.set_detection_paused(False)
    assert manager.detect() is not None


def test_mpc_hc_extracts_title_from_variables_html():
    html = """
    <html><body>
    <p id="state">2</p>
    <p id="filepath">C:\\Videos\\[Group] Frieren - 12.mkv</p>
    </body></html>
    """
    detector = MpcHcDetector()
    assert detector._extract_int(html, "state") == 2
    assert detector._extract_title(html) == "[Group] Frieren - 12.mkv"


def test_mpc_hc_ignores_when_not_playing():
    html = """
    <html><body>
    <p id='state'>0</p>
    <p id='filepath'>C:\\Videos\\Frieren - 12.mkv</p>
    </body></html>
    """
    detector = MpcHcDetector()
    assert detector._extract_int(html, "state") == 0


def test_potplayer_extracts_title_from_html():
    html = """
    <html><head><title>[Group] Frieren - 12.mkv</title></head><body></body></html>
    """
    detector = PotPlayerDetector()
    assert detector._extract_title(html) == "[Group] Frieren - 12.mkv"


def test_potplayer_falls_back_to_filename_meta():
    html = """
    <html><body><input name="title" value="Frieren - 12.mkv"></body></html>
    """
    detector = PotPlayerDetector()
    assert detector._extract_title(html) == "Frieren - 12.mkv"


def test_background_polling_does_not_block_latest_reads():
    class SlowDetector(Detector):
        name = "slow"

        def info(self) -> DetectorInfo:
            return DetectorInfo(name=self.name, available=True, priority=1)

        def detect(self):
            time.sleep(0.15)
            return None

    manager = detectors.DetectorManager()
    manager.register(SlowDetector())
    manager.start_polling(interval=0.01)
    time.sleep(0.02)

    started = time.perf_counter()
    for _ in range(100):
        assert manager.latest() is None
    elapsed = time.perf_counter() - started
    manager.stop()

    assert elapsed < 0.05


def test_disabled_detector_is_skipped(monkeypatch):
    monkeypatch.setattr(detectors.window, "get_active_window_title", lambda: "Frieren - 12 - mpv")
    manager = detectors.DetectorManager()
    manager.register(detectors.ActiveWindowDetector(), enabled=False)

    assert manager.detect() is None
    assert manager.list()[0].enabled is False
    assert manager.set_enabled("active-window", True) is True
    assert manager.detect() is not None
    assert manager.set_enabled("unknown", False) is False


def test_candidate_is_published_only_after_stability_threshold(monkeypatch):
    now = 100.0
    monkeypatch.setattr("nyanko_api.detectors.base.time.monotonic", lambda: now)
    manager = detectors.DetectorManager(stability_seconds=3.0)
    candidate = parse_media_title("Frieren - Episode 12 - VLC media player")

    manager._publish(candidate)
    assert manager.latest() is None
    now = 102.9
    manager._publish(candidate)
    assert manager.latest() is None
    now = 103.1
    manager._publish(candidate)
    assert manager.latest() == candidate

    manager._publish(None)
    assert manager.latest() == candidate

    now = 108.1
    manager._publish(None)
    assert manager.latest() is None


def test_browser_detector_expires_and_ignores_paused_events(monkeypatch):
    now = 100.0
    monkeypatch.setattr("nyanko_api.detectors.browser.time.monotonic", lambda: now)
    detector = BrowserDetector(timeout_seconds=10)
    candidate = PlaybackCandidate(
        source="browser", raw_title="Frieren - 12", episode=12, paused=False
    )

    detector.push(candidate)
    assert detector.detect() == candidate
    detector.push(candidate.model_copy(update={"paused": True}))
    assert detector.detect() is None
    detector.push(candidate.model_copy(update={"content_kind": "trailer"}))
    assert detector.detect() is None
    detector.push(candidate)
    now = 111.0
    assert detector.detect() is None


def test_mpc_hc_extracts_position_duration_and_paused_state():
    html = """
    <html><body>
    <p id="state">1</p>
    <p id="filepath">C:\\Videos\\Frieren - 12.mkv</p>
    <p id="position">123.5</p>
    <p id="duration">1500.0</p>
    </body></html>
    """
    detector = MpcHcDetector()
    # Detection relies on a real HTTP server; test the extraction helpers instead.
    assert detector._extract_float(html, "position") == 123.5
    assert detector._extract_float(html, "duration") == 1500.0
    assert detector._extract_int(html, "state") == 1


def test_vlc_extracts_position_duration_and_paused_state():
    detector = VlcDetector()
    playing = {
        "state": "playing",
        "time": 123,
        "length": 1500,
        "information": {"category": {"meta": {"filename": "Frieren - 12.mkv"}}},
    }
    paused = {
        "state": "paused",
        "time": 0,
        "length": 0,
        "information": {"category": {"meta": {"filename": "Frieren - 12.mkv"}}},
    }
    assert detector._extract_position(playing) == 123.0
    assert detector._extract_duration(playing) == 1500.0
    assert detector._extract_position(paused) == 0.0
    assert detector._extract_duration(paused) is None


def test_mpv_parses_property_responses():
    detector = MpvDetector()
    assert detector._parse_float(123.5) == 123.5
    assert detector._parse_float("none") is None
    assert detector._parse_bool(True) is True
    assert detector._parse_bool(False) is False
    assert detector._parse_property_value({"data": 123.5, "error": "success"}) == 123.5
    assert detector._parse_property_value({"error": "property unavailable"}) is None


def test_smtc_detector_unavailable_without_winsdk():
    detector = SmtcDetector()
    # On non-Windows or when winsdk is missing the detector reports unavailable.
    assert detector.info().available is False
    assert detector.detect() is None


def test_smtc_detector_reads_metadata(monkeypatch):
    from datetime import timedelta

    class FakeStatus:
        name = "PAUSED"

    class FakePlayback:
        playback_status = FakeStatus()

    class FakeTimeline:
        position = timedelta(seconds=123)
        end_time = timedelta(seconds=1500)

    class FakeProperties:
        title = "Frieren - Episode 12"
        artist = ""

    class FakeSession:
        async def try_get_media_properties_async(self):
            return FakeProperties()

        def get_timeline_properties(self):
            return FakeTimeline()

        def get_playback_info(self):
            return FakePlayback()

    class FakeManager:
        def get_current_session(self):
            return FakeSession()

    class FakeWinsdk:
        @staticmethod
        async def request_async():
            return FakeManager()

    monkeypatch.setattr(
        "sys.platform", "win32"
    )
    detector = SmtcDetector()
    detector._winsdk = FakeWinsdk
    assert detector.info().available is True
    candidate = detector.detect()
    assert candidate is not None
    assert candidate.source == "smtc"
    assert candidate.anime_title == "Frieren"
    assert candidate.episode == 12
    assert candidate.position_seconds == 123.0
    assert candidate.duration_seconds == 1500.0
    assert candidate.paused is True
    assert candidate.finished is False


def test_looks_finished_heuristic():
    assert looks_finished(None, 100) is None
    assert looks_finished(50, None) is None
    assert looks_finished(50, 0) is None
    assert looks_finished(95, 100) is True
    assert looks_finished(99, 100) is True
    assert looks_finished(100, 100) is True
    assert looks_finished(40, 100) is True
    assert looks_finished(30, 100) is False
