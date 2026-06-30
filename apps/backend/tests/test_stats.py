"""Tests for statistics_from_items helper (derives stats from live library lists)."""
from nyanko_api.models import MediaItem
from nyanko_api.stats import statistics_from_items


def _item(
    status: str,
    progress: int = 5,
    score: float | None = None,
    fmt: str | None = "TV",
    year: int | None = 2023,
    genres: list[str] | None = None,
) -> MediaItem:
    return MediaItem(
        id=1,
        title="X",
        status=status,
        progress=progress,
        score=score,
        format=fmt,
        year=year,
        genres=genres or [],
    )


def test_statistics_from_items_count_and_statuses():
    """7 CURRENT + 5 COMPLETED + 1 PLANNING → count=13, correct status buckets."""
    anime = (
        [_item("CURRENT") for _ in range(7)]
        + [_item("COMPLETED") for _ in range(5)]
        + [_item("PLANNING", progress=0)]
    )
    result = statistics_from_items(anime, [])

    assert result.anime.count == 13
    # 7 × progress 5 + 5 × progress 5 + 1 × progress 0
    assert result.anime.episodes_watched == 60
    status_map = {s.label: s.count for s in result.anime.statuses}
    assert status_map["CURRENT"] == 7
    assert status_map["COMPLETED"] == 5
    assert status_map["PLANNING"] == 1
    # Manga slice is empty
    assert result.manga.count == 0
    assert result.manga.episodes_watched == 0


def test_statistics_mean_score():
    anime = [_item("COMPLETED", score=80.0), _item("COMPLETED", score=60.0), _item("CURRENT")]
    result = statistics_from_items(anime, [])
    # mean of 80 + 60 = 70.0; unscored item excluded
    assert result.anime.mean_score == 70.0


def test_statistics_no_scores_returns_zero():
    assert statistics_from_items([_item("CURRENT")], []).anime.mean_score == 0.0


def test_statistics_formats_and_years():
    anime = [
        _item("COMPLETED", fmt="TV", year=2022),
        _item("COMPLETED", fmt="TV", year=2022),
        _item("COMPLETED", fmt="OVA", year=2023),
    ]
    result = statistics_from_items(anime, [])
    fmt_map = {f.label: f.count for f in result.anime.formats}
    assert fmt_map["TV"] == 2
    assert fmt_map["OVA"] == 1
    year_map = {y.label: y.count for y in result.anime.release_years}
    assert year_map["2022"] == 2
    assert year_map["2023"] == 1


def test_statistics_genres_top_10():
    # 12 distinct genres, top 10 only
    anime = [_item("COMPLETED", genres=[f"G{i}" for i in range(12)]) for _ in range(2)]
    result = statistics_from_items(anime, [])
    assert len(result.anime.genres) == 10


def test_statistics_manga_slice():
    manga = [_item("CURRENT", progress=10), _item("COMPLETED", progress=20)]
    result = statistics_from_items([], manga)
    assert result.manga.count == 2
    assert result.manga.episodes_watched == 30
    assert result.anime.count == 0
