from nyanko_api.matcher import build_token_index, find_best_match, match_from_index, rank_matches
from nyanko_api.models import MediaItem


def _item(media_id: int, title: str, synonyms: list[str] | None = None) -> MediaItem:
    return MediaItem(id=media_id, title=title, status="CURRENT", progress=0, episodes=12, synonyms=synonyms or [])


def test_token_index_prunes_but_keeps_fuzzy_matches():
    library = [
        _item(1, "Sousou no Frieren"),
        _item(2, "One Piece"),
        _item(3, "Hataraku Maou-sama!"),
    ]
    index = build_token_index(library)
    # Tag-laden / near titles still match via the pruned fuzzy pass.
    m, score = match_from_index("[Group] Sousou no Frieren - 12 [1080p]", index)
    assert m and m.id == 1 and score > 0.8
    m, score = match_from_index("Hataraku Maou-sama!!", index)  # sequel "!!" vs list "!"
    assert m and m.id == 3 and score > 0.8
    m, _ = match_from_index("Totally Unrelated Show", index)
    assert m is None


def test_symbols_in_catalog_titles_match_windows_filenames():
    # Los nombres de archivo de Windows no admiten / \ : * ? — el título del catálogo
    # con símbolos debe igualar a su forma "aplanada" de archivo.
    library = [
        _item(1, "Fate/stay night"),
        _item(2, "Re:Zero kara Hajimeru Isekai Seikatsu"),
        _item(3, "Steins;Gate"),
    ]
    index = build_token_index(library)
    m, score = match_from_index("Fate stay night", index)
    assert m and m.id == 1 and score == 1.0
    m, score = match_from_index("Re Zero kara Hajimeru Isekai Seikatsu", index)
    assert m and m.id == 2 and score == 1.0
    m, score = match_from_index("Steins Gate", index)
    assert m and m.id == 3 and score == 1.0


def test_scan_match_does_not_cross_seasons():
    # Un archivo de la temporada 1 no debe asociarse a la II solo porque el título
    # la contiene, ni un subtítulo de temporada al título base.
    library = [_item(1, "Shuumatsu no Valkyrie II")]
    index = build_token_index(library)
    m, _ = match_from_index("Shuumatsu no Valkyrie", index)
    assert m is None
    library = [_item(2, "JoJo no Kimyou na Bouken")]
    index = build_token_index(library)
    m, _ = match_from_index("JoJo no Kimyou na Bouken - Stone Ocean", index)
    assert m is None


def test_scan_match_franchise_resolves_each_season_exactly():
    library = [
        _item(1, "Strike the Blood"),
        _item(2, "Strike the Blood II"),
        _item(3, "Strike the Blood III"),
        _item(4, "Strike the Blood: Valkyria no Oukoku-hen", synonyms=["Strike the Blood OVA"]),
    ]
    index = build_token_index(library)
    for title, expected in [
        ("Strike the Blood", 1),
        ("Strike the Blood II", 2),
        ("Strike the Blood III", 3),
        ("Strike the Blood꞉ Valkyria no Oukoku-hen", 4),
    ]:
        m, score = match_from_index(title, index)
        assert m and m.id == expected, f"{title} -> {m and m.id}"
        assert score == 1.0


def test_scan_match_ignores_cross_provider_duplicates():
    # La misma obra existe duplicada (una copia canónica por proveedor): el empate
    # entre títulos idénticos no debe tratarse como ambigüedad.
    library = [_item(1, "Tsugumomo"), _item(2, "Tsugumomo"), _item(3, "Tsugu Tsugumomo")]
    index = build_token_index(library)
    m, score = match_from_index("Tsugumomo", index)
    assert m and score == 1.0 and m.title == "Tsugumomo"


def test_scan_match_strips_trailing_ova_and_year_from_files_only():
    library = [_item(1, "Boku no Kokoro no Yabai Yatsu")]
    index = build_token_index(library)
    m, score = match_from_index("Boku no Kokoro no Yabai Yatsu - OVA", index)
    assert m and m.id == 1 and score == 1.0
    # …pero un título de catálogo que termina en OVA es una obra distinta y no debe
    # igualar exacto a un archivo sin ese sufijo.
    library = [
        _item(1, "Strike the Blood"),
        _item(2, "Strike the Blood: Valkyria no Oukoku-hen", synonyms=["Strike the Blood OVA"]),
    ]
    index = build_token_index(library)
    m, score = match_from_index("Strike the Blood", index)
    assert m and m.id == 1


def test_scan_match_rejects_word_overlap_noise():
    # "Dungeon Meshi" comparte "dungeon" con DanMachi pero es otra obra: con el umbral
    # anterior (0.4, bajo el ruido de SequenceMatcher) el escaneo asociaba los archivos
    # y la card mostraba título correcto con portada/detalle de la serie equivocada.
    library = [_item(1, "Dungeon ni Deai wo Motomeru no wa Machigatteiru Darou ka")]
    index = build_token_index(library)
    m, _ = match_from_index("Dungeon Meshi", index)
    assert m is None


def test_rank_matches_orders_by_relevance_and_drops_noise():
    library = [
        _item(1, "Frieren: Beyond Journey's End"),
        _item(2, "Sousou no Frieren"),
        _item(3, "One Piece"),
    ]
    ranked = rank_matches("Frieren 12", "Frieren", library, limit=5)
    ids = [item.id for _, item in ranked]
    assert ids[0] == 1  # closest title first
    assert 3 not in ids  # irrelevant series filtered out by the floor
    assert all(score >= 0.55 for score, _ in ranked)


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
