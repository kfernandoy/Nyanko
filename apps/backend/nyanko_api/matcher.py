from difflib import SequenceMatcher
import re

from .models import MediaItem
from .normalizer import normalize_title


def _search_forms(value: str) -> list[str]:
    normalized = normalize_title(value).casefold()
    without_season = re.sub(r"\bseason\s+\d+\b", "", normalized).strip()
    return list(dict.fromkeys(form for form in (normalized, without_season) if form))


def _similarity(left: str, right: str) -> float:
    left_forms = _search_forms(left)
    right_forms = _search_forms(right)
    if not left_forms or not right_forms:
        return 0.0
    scores = []
    for normalized_left in left_forms:
        for normalized_right in right_forms:
            if normalized_left == normalized_right:
                scores.append(1.0)
            elif (
                min(len(normalized_left), len(normalized_right)) >= 4
                and (normalized_left in normalized_right or normalized_right in normalized_left)
            ):
                scores.append(0.9)
            else:
                scores.append(SequenceMatcher(None, normalized_left, normalized_right).ratio())
    return max(scores, default=0.0)


def _titles(item: MediaItem) -> list[str]:
    values = [
        item.title,
        item.title_romaji,
        item.title_english,
        item.title_native,
        *item.synonyms,
    ]
    return list(dict.fromkeys(title for title in values if title))


def find_best_match(
    raw_title: str | None,
    anime_title: str | None,
    season: int | None,
    library: list[MediaItem],
    corrections: dict[str, int] | None = None,
    search_hints: list[str] | None = None,
    min_score: float = 0.4,
) -> tuple[MediaItem | None, float]:
    if not library:
        return None, 0.0

    if corrections and raw_title:
        normalized_raw = normalize_title(raw_title)
        keys = {raw_title, normalized_raw}
        if anime_title:
            keys.add(anime_title)
            keys.add(normalize_title(anime_title))
        for key in keys:
            media_id = corrections.get(key)
            if media_id is not None:
                for item in library:
                    if item.id == media_id:
                        return item, 1.0
                break

    search_titles = [value for value in [anime_title, raw_title, *(search_hints or [])] if value]
    if not search_titles:
        return None, 0.0

    scored: list[tuple[float, MediaItem]] = []

    for item in library:
        titles = _titles(item)
        candidate_scores = [
            _similarity(search_title, title)
            for search_title in search_titles
            for title in titles
        ]
        score = max(candidate_scores, default=0.0)
        scored.append((score, item))

    scored.sort(key=lambda result: result[0], reverse=True)
    best_score, best_match = scored[0]

    effective_min_score = min_score if not corrections and not search_hints else 0.25
    # Season is a tie-breaker / penalty signal for now; AniList stores seasons as separate entries.
    if best_match and best_score < effective_min_score:
        return None, best_score
    if len(scored) > 1 and scored[1][0] >= effective_min_score and best_score - scored[1][0] < 0.03:
        return None, best_score
    return best_match, best_score
