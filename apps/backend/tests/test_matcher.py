from nyanko_api.matcher import find_best_match
from nyanko_api.models import MediaItem


def _item(media_id: int, title: str) -> MediaItem:
    return MediaItem(id=media_id, title=title, status="CURRENT", progress=0, episodes=12)


def test_exact_correction_wins_over_fuzzy_match():
    library = [_item(1, "Frieren: Beyond Journey's End"), _item(2, "Sousou no Frieren")]
    corrections = {"Frieren - 12": 2}

    match, score = find_best_match(
        raw_title="Frieren - 12",
        anime_title="Frieren",
        season=None,
        library=library,
        corrections=corrections,
    )

    assert match is not None
    assert match.id == 2
    assert score == 1.0


def test_fuzzy_match_without_correction():
    library = [_item(1, "Frieren")]

    match, score = find_best_match(
        raw_title="Frieren - 12",
        anime_title="Frieren",
        season=None,
        library=library,
    )

    assert match is not None
    assert match.id == 1
    assert score > 0.5


def test_no_match_when_score_below_threshold():
    library = [_item(1, "Something Completely Different")]

    match, score = find_best_match(
        raw_title="xyz",
        anime_title="xyz",
        season=None,
        library=library,
    )

    assert match is None
    assert score < 0.4


def test_correction_ignores_missing_media_id():
    library = [_item(1, "Frieren")]
    corrections = {"unknown": 99}

    match, score = find_best_match(
        raw_title="unknown",
        anime_title="Frieren",
        season=None,
        library=library,
        corrections=corrections,
    )

    assert match is not None
    assert match.id == 1
    assert score <= 1.0


def test_matches_canonical_alias():
    item = _item(1, "Sousou no Frieren").model_copy(
        update={"synonyms": ["Frieren: Beyond Journey's End"]}
    )

    match, score = find_best_match(
        raw_title="Frieren Beyond Journeys End - 12",
        anime_title="Frieren Beyond Journeys End",
        season=None,
        library=[item],
    )

    assert match is not None
    assert match.id == 1
    assert score > 0.95


def test_ambiguous_equal_aliases_do_not_choose_arbitrarily():
    first = _item(1, "First").model_copy(update={"synonyms": ["Shared"]})
    second = _item(2, "Second").model_copy(update={"synonyms": ["Shared"]})

    match, score = find_best_match(
        raw_title="Shared - 01",
        anime_title="Shared",
        season=None,
        library=[first, second],
    )

    assert match is None
    assert score == 1.0


def test_raw_title_is_used_when_anime_title_is_missing():
    library = [_item(1, "Sousou no Frieren")]

    match, score = find_best_match(
        raw_title="Sousou no Frieren Episode 12",
        anime_title=None,
        season=None,
        library=library,
    )

    assert match is not None
    assert match.id == 1
    assert score >= 0.9


def test_dirty_extracted_title_can_match_contained_anilist_title():
    library = [_item(1, "Boku no Hero Academia")]

    match, score = find_best_match(
        raw_title="Boku no Hero Academia Season 7 Episode 12",
        anime_title="Boku no Hero Academia Season 7 Episode 12",
        season=7,
        library=library,
    )

    assert match is not None
    assert match.id == 1
    assert score >= 0.9


def test_crunchyroll_season_title_can_match_anilist_renamed_season():
    library = [_item(1, "Diamond no Ace: Act II").model_copy(update={
        "title_english": "Ace of Diamond Act II",
        "synonyms": ["Ace of the Diamond Act II"],
    })]

    match, score = find_best_match(
        raw_title="Ace of the Diamond Season 4",
        anime_title="Ace of the Diamond Season 4",
        season=4,
        library=library,
        min_score=0.25,
    )

    assert match is not None
    assert match.id == 1
    assert score >= 0.25
