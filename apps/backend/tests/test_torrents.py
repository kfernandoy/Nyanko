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


_GLOBALS = {"discard_not_in_list": True, "discard_seen": True, "prefer_resolution": True}


def test_build_feed_new_episode_only():
    library = [_lib_entry(progress=27)]
    items = torrents.build_feed([_parsed(episode=28)], library, [], set(), set(),
                                filters_enabled=True, globals_=_GLOBALS)
    assert len(items) == 1
    assert items[0].media_id == 1
    assert items[0].episode == 28
    assert items[0].is_new is True


def test_build_feed_skips_already_watched():
    library = [_lib_entry(progress=28)]
    items = torrents.build_feed([_parsed(episode=28)], library, [], set(), set(),
                                filters_enabled=True, globals_=_GLOBALS)
    assert items == []


def test_build_feed_skips_non_current_status():
    library = [_lib_entry(status="COMPLETED", progress=12)]
    items = torrents.build_feed([_parsed(episode=28)], library, [], set(), set(),
                                filters_enabled=True, globals_=_GLOBALS)
    assert items == []


def test_build_feed_skips_unmatched():
    library = [_lib_entry(title="Totally Other Show")]
    items = torrents.build_feed([_parsed(episode=28)], library, [], set(), set(),
                                filters_enabled=True, globals_=_GLOBALS)
    assert items == []


def test_build_feed_marks_not_new_and_skips_discarded():
    library = [_lib_entry(progress=27)]
    sig = torrents.signature(1, "g1")
    items = torrents.build_feed([_parsed(episode=28)], library, [], {sig}, set(),
                                filters_enabled=True, globals_=_GLOBALS)
    assert items[0].is_new is False
    discarded = torrents.build_feed([_parsed(episode=28)], library, [], {sig}, {sig},
                                    filters_enabled=True, globals_=_GLOBALS)
    assert discarded == []


def _filter(action="discard", match="all", scope="all", conditions=None, anime_ids=None):
    return {"action": action, "match": match, "scope": scope, "enabled": True,
            "conditions": conditions or [], "anime_ids": anime_ids or []}


def test_engine_discard_condition():
    f = _filter(action="discard", conditions=[{"element": "group", "operator": "is", "value": "SubsPlease"}])
    lib = [_lib_entry(progress=27)]
    out = torrents.build_feed([_parsed(episode=28)], lib, [f], set(), set(),
                              filters_enabled=True, globals_=_GLOBALS)
    assert out == []  # descartado por grupo


def test_engine_select_overrides_globals():
    # serie NO en lista; un select fuerza incluir aunque discard_not_in_list esté on
    f = _filter(action="select", conditions=[{"element": "resolution", "operator": "equals", "value": "1080p"}])
    out = torrents.build_feed([_parsed(title="Desconocida", episode=5)], [], [f], set(), set(),
                              filters_enabled=True, globals_=_GLOBALS)
    assert len(out) == 1


def test_engine_match_any():
    f = _filter(action="discard", match="any",
                conditions=[{"element": "group", "operator": "is", "value": "Nope"},
                            {"element": "resolution", "operator": "equals", "value": "1080p"}])
    lib = [_lib_entry(progress=27)]
    out = torrents.build_feed([_parsed(episode=28, resolution="1080p")], lib, [f], set(), set(),
                              filters_enabled=True, globals_=_GLOBALS)
    assert out == []  # una condición (resolution) basta con match=any


def test_engine_scope_limited():
    f = _filter(action="discard", scope="limited", anime_ids=[999],
                conditions=[{"element": "group", "operator": "is", "value": "SubsPlease"}])
    lib = [_lib_entry(id=1, progress=27)]  # media_id 1, no 999 -> filtro no aplica
    out = torrents.build_feed([_parsed(episode=28)], lib, [f], set(), set(),
                              filters_enabled=True, globals_=_GLOBALS)
    assert len(out) == 1  # no descartado: el filtro limited no aplica a media 1


def test_globals_discard_not_in_list():
    out = torrents.build_feed([_parsed(title="Desconocida", episode=5)], [], [], set(), set(),
                              filters_enabled=True, globals_=_GLOBALS)
    assert out == []


def test_filters_disabled_skips_user_rules_keeps_globals():
    f = _filter(action="discard", conditions=[{"element": "group", "operator": "is", "value": "SubsPlease"}])
    lib = [_lib_entry(progress=27)]
    out = torrents.build_feed([_parsed(episode=28)], lib, [f], set(), set(),
                              filters_enabled=False, globals_=_GLOBALS)
    assert len(out) == 1  # la regla de usuario se ignora; globales mantienen el item válido


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
        [item_720, item_1080], library, [], set(), set(),
        filters_enabled=True, globals_=_GLOBALS, preferred_resolution="1080p",
    )
    assert feed[0].resolution == "1080p"
    assert feed[1].resolution == "720p"

    # A user prefer rule on 720p dominates over preferred_resolution="1080p".
    prefer_720 = [_filter(action="prefer",
                          conditions=[{"element": "resolution", "operator": "equals", "value": "720p"}])]
    feed2 = torrents.build_feed(
        [item_1080, item_720], library, prefer_720, set(), set(),
        filters_enabled=True, globals_=_GLOBALS, preferred_resolution="1080p",
    )
    assert feed2[0].resolution == "720p"   # user prefer wins
    assert feed2[1].resolution == "1080p"


def test_extract_version():
    assert torrents.extract_version("[Grp] Frieren - 12v2 (1080p).mkv") == 2
    assert torrents.extract_version("[Grp] Frieren - 12 V3.mkv") == 3
    assert torrents.extract_version("[Grp] Frieren - 12.mkv") == 1


def test_engine_user_status_element():
    # Descartar abandonados (preset de Taiga).
    f = _filter(action="discard", conditions=[{"element": "user_status", "operator": "is", "value": "DROPPED"}])
    lib = [_lib_entry(status="DROPPED", progress=2)]
    out = torrents.build_feed([_parsed(episode=28)], lib, [f], set(), set(),
                              filters_enabled=True, globals_={})
    assert out == []
    # NOT_IN_LIST cuando no hay match.
    f2 = _filter(action="discard", conditions=[{"element": "user_status", "operator": "is", "value": "NOT_IN_LIST"}])
    out = torrents.build_feed([_parsed(title="Desconocida", episode=5)], [], [f2], set(), set(),
                              filters_enabled=True, globals_={})
    assert out == []


def test_engine_media_status_and_user_status_combo():
    # "Seleccionar en emisión que planeas ver": media_status RELEASING + user_status PLANNING.
    f = _filter(action="select", match="all", conditions=[
        {"element": "media_status", "operator": "is", "value": "RELEASING"},
        {"element": "user_status", "operator": "is", "value": "PLANNING"},
    ])
    lib = [_lib_entry(status="PLANNING", progress=0, media_status="RELEASING")]
    # select fuerza incluir pese a discard_seen (PLANNING no es CURRENT).
    out = torrents.build_feed([_parsed(episode=1)], lib, [f], set(), set(),
                              filters_enabled=True, globals_=_GLOBALS)
    assert len(out) == 1


def test_engine_version_element():
    f = _filter(action="prefer", conditions=[{"element": "version", "operator": "gt", "value": "1"}])
    lib = [_lib_entry(progress=27)]
    v1 = _parsed(guid="a", episode=28, version=1)
    v2 = _parsed(guid="b", episode=28, version=2)
    out = torrents.build_feed([v1, v2], lib, [f], set(), set(),
                              filters_enabled=True, globals_=_GLOBALS)
    assert [item.signature for item in out][0] == torrents.signature(1, "b")  # v2 primero


def test_engine_local_available_element():
    f = _filter(action="discard", conditions=[{"element": "local_available", "operator": "is", "value": "true"}])
    lib = [_lib_entry(progress=27)]
    out = torrents.build_feed([_parsed(episode=28)], lib, [f], set(), set(),
                              filters_enabled=True, globals_=_GLOBALS,
                              local_episodes={1: {28}})
    assert out == []  # el episodio 28 ya está en disco
    out = torrents.build_feed([_parsed(episode=28)], lib, [f], set(), set(),
                              filters_enabled=True, globals_=_GLOBALS,
                              local_episodes={1: {27}})
    assert len(out) == 1  # el 28 no está: pasa


def test_parse_feed_extracts_version():
    xml = """<rss><channel><item>
      <title>[Grp] Frieren - 28v2 (1080p).mkv</title>
      <link>magnet:?x</link><guid>g1</guid>
    </item></channel></rss>"""
    parsed = torrents.parse_feed(xml, 1)
    assert parsed[0].version == 2
