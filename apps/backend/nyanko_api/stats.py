from collections import Counter

from .models import MediaItem, MediaStatistics, StatisticGroup, StatisticsResponse


def statistics_from_items(anime: list[MediaItem], manga: list[MediaItem]) -> StatisticsResponse:
    """Derive StatisticsResponse from live library lists (ponytail: avoids stale/empty native distributions)."""
    return StatisticsResponse(anime=_media_stats(anime), manga=_media_stats(manga))


def _media_stats(items: list[MediaItem]) -> MediaStatistics:
    scores = [i.score for i in items if i.score]
    status_counts: Counter = Counter(i.status for i in items)
    format_counts: Counter = Counter(i.format for i in items if i.format)
    year_counts: Counter = Counter(str(i.year) for i in items if i.year)
    genre_counts: Counter = Counter(g for i in items for g in i.genres)
    return MediaStatistics(
        count=len(items),
        episodes_watched=sum(i.progress for i in items),
        minutes_watched=0,
        mean_score=round(sum(scores) / len(scores), 1) if scores else 0.0,
        statuses=[StatisticGroup(label=s, count=c) for s, c in status_counts.most_common()],
        formats=[StatisticGroup(label=f, count=c) for f, c in format_counts.most_common()],
        release_years=[StatisticGroup(label=y, count=c) for y, c in sorted(year_counts.items(), key=lambda x: -x[1])],
        genres=[StatisticGroup(label=g, count=c) for g, c in genre_counts.most_common(10)],
        studios=[],
        countries=[],
    )
