from nyanko_api.provider_mappings import (
    CanonicalFormat,
    CanonicalStatus,
    ScoreFormat,
    convert_score,
    from_canonical_format,
    from_canonical_status,
    to_canonical_format,
    to_canonical_status,
)


def test_anilist_status_roundtrip():
    for value in ("CURRENT", "PLANNING", "COMPLETED", "PAUSED", "DROPPED", "REPEATING"):
        canonical = to_canonical_status("anilist", value)
        assert from_canonical_status("anilist", canonical) == value


def test_mal_status_roundtrip():
    for value in ("watching", "completed", "on_hold", "dropped", "plan_to_watch"):
        canonical = to_canonical_status("mal", value)
        assert from_canonical_status("mal", canonical) == value


def test_repeating_maps_to_watching_for_mal():
    assert from_canonical_status("mal", CanonicalStatus.REPEATING) == "watching"


def test_unknown_provider_raises():
    try:
        to_canonical_status("unknown", "CURRENT")
    except ValueError as error:
        assert "Unknown provider" in str(error)
    else:
        raise AssertionError("Expected ValueError")


def test_unknown_status_raises():
    try:
        to_canonical_status("mal", "archived")
    except ValueError as error:
        assert "Unsupported" in str(error)
    else:
        raise AssertionError("Expected ValueError")


def test_anilist_format_roundtrip():
    for value in ("TV", "TV_SHORT", "MOVIE", "SPECIAL", "OVA", "ONA", "MUSIC"):
        canonical = to_canonical_format("anilist", value)
        assert from_canonical_format("anilist", canonical) == value


def test_mal_format_mapping():
    assert to_canonical_format("mal", "tv") == CanonicalFormat.TV
    assert to_canonical_format("mal", "movie") == CanonicalFormat.MOVIE
    assert to_canonical_format("mal", "tv_special") == CanonicalFormat.SPECIAL
    assert to_canonical_format("mal", "doujinshi") == CanonicalFormat.MANGA
    assert to_canonical_format("mal", "unknown") == CanonicalFormat.UNKNOWN


def test_unknown_format_maps_to_unknown():
    assert to_canonical_format("anilist", "VR") == CanonicalFormat.UNKNOWN


def test_convert_score_between_formats():
    assert convert_score(85, ScoreFormat.POINT_100, ScoreFormat.POINT_10) == 8
    assert convert_score(95, ScoreFormat.POINT_100, ScoreFormat.POINT_10) == 10
    assert convert_score(85, ScoreFormat.POINT_100, ScoreFormat.POINT_10_DECIMAL) == 8.5
    assert convert_score(85, ScoreFormat.POINT_100, ScoreFormat.POINT_5) == 4
    assert convert_score(100, ScoreFormat.POINT_100, ScoreFormat.POINT_5) == 5
    assert convert_score(0, ScoreFormat.POINT_100, ScoreFormat.POINT_5) is None
    assert convert_score(None, ScoreFormat.POINT_100, ScoreFormat.POINT_5) is None


def test_convert_score_same_format_returns_value():
    assert convert_score(7.5, ScoreFormat.POINT_10_DECIMAL, ScoreFormat.POINT_10_DECIMAL) == 7.5


def test_convert_score_point_3_mapping():
    assert convert_score(1, ScoreFormat.POINT_3, ScoreFormat.POINT_100) == 34
    assert convert_score(2, ScoreFormat.POINT_3, ScoreFormat.POINT_100) == 67
    assert convert_score(3, ScoreFormat.POINT_3, ScoreFormat.POINT_100) == 100
