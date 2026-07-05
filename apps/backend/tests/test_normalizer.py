import pytest

from nyanko_api.normalizer import EpisodeInfo, NormalizedTitle, normalize


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            "[SubsPlease] Frieren - Beyond Journey's End - 12 (1080p) [ABCD1234].mkv",
            NormalizedTitle(
                raw_title="[SubsPlease] Frieren - Beyond Journey's End - 12 (1080p) [ABCD1234].mkv",
                anime_title="Frieren - Beyond Journey's End",
                season=None,
                episode=EpisodeInfo(number=12, type="regular", raw_label="- 12"),
                confidence=1.0,
            ),
        ),
        (
            "Attack on Titan S04E05.mkv",
            NormalizedTitle(
                raw_title="Attack on Titan S04E05.mkv",
                anime_title="Attack on Titan",
                season=4,
                episode=EpisodeInfo(number=5, type="regular", raw_label="S04E05"),
                confidence=1.0,
            ),
        ),
        (
            "One Piece - Episode 1000 - HD.mkv",
            NormalizedTitle(
                raw_title="One Piece - Episode 1000 - HD.mkv",
                anime_title="One Piece",
                season=None,
                episode=EpisodeInfo(number=1000, type="regular", raw_label="Episode 1000"),
                confidence=1.0,
            ),
        ),
        (
            "Kaguya-sama wa Kokurasetai S2 - 01.mkv",
            NormalizedTitle(
                raw_title="Kaguya-sama wa Kokurasetai S2 - 01.mkv",
                anime_title="Kaguya-sama wa Kokurasetai",
                season=2,
                episode=EpisodeInfo(number=1, type="regular", raw_label="- 01"),
                confidence=1.0,
            ),
        ),
        (
            "Oregairu 2nd Season - 01.mkv",
            NormalizedTitle(
                raw_title="Oregairu 2nd Season - 01.mkv",
                anime_title="Oregairu",
                season=2,
                episode=EpisodeInfo(number=1, type="regular", raw_label="- 01"),
                confidence=1.0,
            ),
        ),
        (
            "Bleach - 366 [720p].mkv",
            NormalizedTitle(
                raw_title="Bleach - 366 [720p].mkv",
                anime_title="Bleach",
                season=None,
                episode=EpisodeInfo(number=366, type="absolute", raw_label="- 366"),
                confidence=1.0,
            ),
        ),
        (
            "Naruto Shippuden - Ep 500.mkv",
            NormalizedTitle(
                raw_title="Naruto Shippuden - Ep 500.mkv",
                anime_title="Naruto Shippuden",
                season=None,
                episode=EpisodeInfo(number=500, type="regular", raw_label="Ep 500"),
                confidence=1.0,
            ),
        ),
        (
            "Some Show - OVA 03.mkv",
            NormalizedTitle(
                raw_title="Some Show - OVA 03.mkv",
                anime_title="Some Show",
                season=None,
                episode=EpisodeInfo(number=3, type="ova", raw_label="OVA 03"),
                confidence=1.0,
            ),
        ),
        (
            "Frieren - Episode 12 - VLC media player",
            NormalizedTitle(
                raw_title="Frieren - Episode 12 - VLC media player",
                anime_title="Frieren",
                season=None,
                episode=EpisodeInfo(number=12, type="regular", raw_label="Episode 12"),
                confidence=1.0,
            ),
        ),
    ],
)
def test_normalize_real_filenames(raw: str, expected: NormalizedTitle):
    result = normalize(raw)
    assert result.anime_title == expected.anime_title
    assert result.season == expected.season
    assert result.episode == expected.episode
    assert result.confidence == expected.confidence


def test_normalize_returns_low_confidence_for_unknown_title():
    result = normalize("Crunchyroll - Google Chrome")
    assert result.anime_title == "Crunchyroll"
    assert result.episode is None
    assert result.confidence < 0.65


def test_airing_season_from_date():
    from nyanko_api.normalizer import airing_season_from_date

    assert airing_season_from_date("2024-01-07") == "WINTER"
    assert airing_season_from_date("2024-04-01") == "SPRING"
    assert airing_season_from_date("2024-08-15") == "SUMMER"
    assert airing_season_from_date("2024-10-02") == "FALL"
    assert airing_season_from_date("2024") is None
    assert airing_season_from_date("") is None
    assert airing_season_from_date(None) is None
