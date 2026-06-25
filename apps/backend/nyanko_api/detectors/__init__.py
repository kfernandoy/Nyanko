from .base import Detector, DetectorInfo, DetectorManager, looks_finished
from .browser import BrowserDetector
from .mpc_hc import MpcHcDetector
from .mpv import MpvDetector
from .pause import is_detection_paused, set_detection_paused
from .potplayer import PotPlayerDetector
from .smtc import SmtcDetector
from .vlc import VlcDetector
from .window import ActiveWindowDetector, parse_media_title

__all__ = [
    "Detector",
    "DetectorInfo",
    "DetectorManager",
    "BrowserDetector",
    "ActiveWindowDetector",
    "MpcHcDetector",
    "MpvDetector",
    "PotPlayerDetector",
    "SmtcDetector",
    "VlcDetector",
    "is_detection_paused",
    "looks_finished",
    "set_detection_paused",
    "parse_media_title",
]
