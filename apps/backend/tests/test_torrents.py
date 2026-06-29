from pathlib import Path

from nyanko_api import torrents

FIXTURE = (Path(__file__).parent / "fixtures" / "nyaa_sample.xml").read_text(encoding="utf-8")


def test_extract_group():
    assert torrents.extract_group("[SubsPlease] Frieren - 28 (1080p).mkv") == "SubsPlease"
    assert torrents.extract_group("Frieren - 28.mkv") is None


def test_extract_resolution():
    assert torrents.extract_resolution("Frieren - 28 (1080p).mkv") == "1080p"
    assert torrents.extract_resolution("Show [720p][HEVC].mkv") == "720p"
    assert torrents.extract_resolution("Show [2160p].mkv") == "2160p"
    assert torrents.extract_resolution("Show.mkv") is None


def test_parse_feed_basic():
    items = torrents.parse_feed(FIXTURE, source_id=1)
    assert len(items) == 3
    first = items[0]
    assert first.group == "SubsPlease"
    assert first.title == "Frieren"
    assert first.episode == 28
    assert first.resolution == "1080p"
    assert first.seeders == 120
    assert first.link.startswith("magnet:")
    assert first.guid == "https://nyaa.si/view/1000001"


def test_parse_feed_season_episode():
    items = torrents.parse_feed(FIXTURE, source_id=1)
    third = items[2]
    assert third.episode == 3            # S02E03 -> episode 3
    assert third.seeders is None


def test_signature_stable():
    assert torrents.signature(1, "g") == torrents.signature(1, "g")
    assert torrents.signature(1, "g") != torrents.signature(2, "g")
