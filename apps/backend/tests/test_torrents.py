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


from nyanko_api.models import MediaItem


def _lib_entry(**kw):
    base = dict(id=1, title="Frieren", status="CURRENT", progress=27, media_type="ANIME")
    base.update(kw)
    return MediaItem(**base)


def _parsed(**kw):
    base = dict(
        raw_title="[SubsPlease] Frieren - 28 (1080p).mkv",
        link="magnet:?x", guid="g1", source_id=1, title="Frieren",
        episode=28, group="SubsPlease", resolution="1080p", seeders=10,
    )
    base.update(kw)
    return torrents.ParsedTorrent(**base)


def test_passes_filters_exclude_wins():
    filt = [{"field": "group", "op": "equals", "value": "SubsPlease",
             "action": "exclude", "enabled": 1, "priority": 0}]
    assert torrents.passes_filters(_parsed(), filt) is False


def test_passes_filters_resolution_contains():
    filt = [{"field": "resolution", "op": "equals", "value": "720p",
             "action": "exclude", "enabled": 1, "priority": 0}]
    assert torrents.passes_filters(_parsed(resolution="1080p"), filt) is True
    assert torrents.passes_filters(_parsed(resolution="720p"), filt) is False


def test_passes_filters_episode_gt():
    filt = [{"field": "episode", "op": "lt", "value": "10",
             "action": "exclude", "enabled": 1, "priority": 0}]
    assert torrents.passes_filters(_parsed(episode=5), filt) is False
    assert torrents.passes_filters(_parsed(episode=28), filt) is True


def test_passes_filters_disabled_ignored():
    filt = [{"field": "group", "op": "equals", "value": "SubsPlease",
             "action": "exclude", "enabled": 0, "priority": 0}]
    assert torrents.passes_filters(_parsed(), filt) is True


def test_build_feed_new_episode_only():
    library = [_lib_entry(progress=27)]
    items = torrents.build_feed([_parsed(episode=28)], library, [], set(), set())
    assert len(items) == 1
    assert items[0].media_id == 1
    assert items[0].episode == 28
    assert items[0].is_new is True


def test_build_feed_skips_already_watched():
    library = [_lib_entry(progress=28)]
    items = torrents.build_feed([_parsed(episode=28)], library, [], set(), set())
    assert items == []


def test_build_feed_skips_non_current_status():
    library = [_lib_entry(status="COMPLETED", progress=12)]
    items = torrents.build_feed([_parsed(episode=28)], library, [], set(), set())
    assert items == []


def test_build_feed_skips_unmatched():
    library = [_lib_entry(title="Totally Other Show")]
    items = torrents.build_feed([_parsed(episode=28)], library, [], set(), set())
    assert items == []


def test_build_feed_marks_not_new_and_skips_discarded():
    library = [_lib_entry(progress=27)]
    sig = torrents.signature(1, "g1")
    items = torrents.build_feed([_parsed(episode=28)], library, [], {sig}, set())
    assert items[0].is_new is False
    discarded = torrents.build_feed([_parsed(episode=28)], library, [], {sig}, {sig})
    assert discarded == []


def test_parse_feed_extended_fields():
    items = torrents.parse_feed(FIXTURE, source_id=1)
    first = items[0]
    assert first.size == "1.4 GiB"
    assert first.torrent_date == "Mon, 23 Jun 2025 12:00:00 +0000"
    assert first.description and "comments" in first.description
    assert first.filename == first.raw_title
    # item sin esos tags -> None
    assert items[1].size is None
    assert items[1].torrent_date is None
    assert items[1].description is None


def test_build_feed_preferred_resolution_ordering():
    """preferred_resolution sorts matching items before non-matching; user prefer still dominates."""
    library = [_lib_entry(progress=27)]
    item_1080 = _parsed(resolution="1080p", guid="g1080", seeders=10)
    item_720 = _parsed(resolution="720p", guid="g720", seeders=10)

    # preferred_resolution="1080p": 1080p ranks before 720p (input order: 720p first).
    feed = torrents.build_feed(
        [item_720, item_1080], library, [], set(), set(), preferred_resolution="1080p"
    )
    assert feed[0].resolution == "1080p"
    assert feed[1].resolution == "720p"

    # A user prefer rule on 720p dominates over preferred_resolution="1080p".
    prefer_720 = [{"field": "resolution", "op": "equals", "value": "720p",
                   "action": "prefer", "enabled": 1, "priority": 0}]
    feed2 = torrents.build_feed(
        [item_1080, item_720], library, prefer_720, set(), set(), preferred_resolution="1080p"
    )
    assert feed2[0].resolution == "720p"   # user prefer wins
    assert feed2[1].resolution == "1080p"
