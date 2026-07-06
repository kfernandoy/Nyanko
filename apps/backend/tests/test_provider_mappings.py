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


# --- Roundtrips que documentan pérdida de precisión (canónico = POINT_100) ---

def _roundtrip_score(value, fmt):
    """Canónico POINT_100 -> formato del proveedor -> POINT_100."""
    provider_value = convert_score(value, ScoreFormat.POINT_100, fmt)
    if provider_value is None:
        return None
    return convert_score(provider_value, fmt, ScoreFormat.POINT_100)


def test_score_roundtrip_lossless_for_fine_formats():
    # POINT_100 y el decimal de 10 puntos conservan el valor exacto (múltiplos de 10).
    for value in (10, 50, 80, 85, 100):
        assert _roundtrip_score(value, ScoreFormat.POINT_100) == value
        assert _roundtrip_score(value, ScoreFormat.POINT_10_DECIMAL) == value


def test_score_roundtrip_loses_precision_on_coarse_formats():
    # POINT_10 entero: 85 -> 8 (round bancario de 8.5) -> 80. Se pierden 5 puntos.
    assert _roundtrip_score(85, ScoreFormat.POINT_10) == 80
    # POINT_5: 85 -> 4 -> 80.
    assert _roundtrip_score(85, ScoreFormat.POINT_5) == 80
    # POINT_3: 85 -> 2 -> 67. La pérdida es grande en la escala más gruesa.
    assert _roundtrip_score(85, ScoreFormat.POINT_3) == 67
    # En todos los casos el valor no sobrevive intacto: la pérdida es real, no un bug.
    for fmt in (ScoreFormat.POINT_10, ScoreFormat.POINT_5, ScoreFormat.POINT_3):
        assert _roundtrip_score(85, fmt) != 85


def test_cross_provider_score_roundtrip_anilist_100_via_mal_10():
    # Usuario AniList en POINT_100 (85) sincroniza a MAL (entero 0-10) y vuelve: 85 -> 8 -> 80.
    to_mal = convert_score(85, ScoreFormat.POINT_100, ScoreFormat.POINT_10)
    assert to_mal == 8
    back = convert_score(to_mal, ScoreFormat.POINT_10, ScoreFormat.POINT_100)
    assert back == 80


def test_score_zero_is_unset_in_roundtrip():
    assert _roundtrip_score(0, ScoreFormat.POINT_10) is None


def test_status_roundtrip_loses_repeating_on_mal():
    # MAL no tiene REPEATING: se guarda como "watching" y al releer vuelve como CURRENT.
    mal_value = from_canonical_status("mal", CanonicalStatus.REPEATING)
    assert mal_value == "watching"
    assert to_canonical_status("mal", mal_value) == CanonicalStatus.CURRENT
    assert to_canonical_status("mal", mal_value) != CanonicalStatus.REPEATING


def test_format_roundtrip_collapses_mal_subtypes():
    # Subtipos de manga distintos colapsan a MANGA y vuelven como "manga" genérico.
    for subtype in ("doujinshi", "manhwa", "manhua"):
        canonical = to_canonical_format("mal", subtype)
        assert canonical == CanonicalFormat.MANGA
        assert from_canonical_format("mal", canonical) == "manga"
    # "tv_special" y "special" son ambos SPECIAL; el canónico vuelve como "special".
    assert to_canonical_format("mal", "tv_special") == CanonicalFormat.SPECIAL
    assert from_canonical_format("mal", CanonicalFormat.SPECIAL) == "special"
