from collections import defaultdict
from difflib import SequenceMatcher
from functools import lru_cache
import re

from .models import MediaItem
from .normalizer import fold_title, normalize_title

_TOKEN = re.compile(r"[a-z0-9]+")


# Cached: a library scan compares thousands of files against the same library titles,
# so the (expensive) anitomy normalisation of each title repeats endlessly otherwise.
_TRAILING_YEAR = re.compile(r"\s+(?:19|20)\d{2}$")
_TRAILING_EXTRA = re.compile(r"\s+(?:ova|ona|oad|special|specials)$")
# Marcadores de secuela: si la única diferencia entre dos títulos es esto, casi
# seguro son temporadas distintas de la misma franquicia, no la misma obra.
_SEQUEL_MARKER = re.compile(
    r"^(?:i{1,3}|iv|v|vi{0,3}|ix|x|\d{1,2}|2nd|3rd|\d{1,2}th|final|s\d{1,2}|"
    r"season\s*\d*|part\s*\d*|cour\s*\d*|shou|hen)(?:\s|$)"
)
# Numeración de episodio que puede quedar pegada al título en reproducción
# ("Sousou no Frieren Episode 12", "Frieren - 12"): no implica otra obra.
_EPISODE_JUNK = re.compile(r"^(?:(?:episode|episodio|ep|cap|capitulo)\s*)?\d{1,4}$")


@lru_cache(maxsize=8192)
def _search_forms(value: str, is_query: bool = False) -> tuple[str, ...]:
    # fold_title: los títulos con símbolos ("Fate/stay night") deben igualar a su
    # versión de nombre de archivo Windows ("Fate stay night").
    normalized = fold_title(normalize_title(value))
    without_season = " ".join(re.sub(r"\bseason\s+\d+\b", "", normalized).split())
    forms = [normalized, without_season]
    if is_query:
        # Solo del lado del archivo: "Título - OVA (2020)" debe igualar a "Título",
        # pero un título de catálogo que termina en OVA es una obra distinta.
        forms.append(_TRAILING_YEAR.sub("", normalized))
        forms.append(_TRAILING_EXTRA.sub("", _TRAILING_YEAR.sub("", normalized)))
    return tuple(dict.fromkeys(form for form in forms if form))


def _containment_score(shorter: str, longer: str, query_is_longer: bool) -> float:
    """Puntaje cuando un título contiene al otro.

    - Candidato más largo con sobrante de marcador de secuela ("Shuumatsu no
      Valkyrie" ⊂ "Shuumatsu no Valkyrie II"): 0.7 — es otra temporada.
    - Query más largo con sobrante de subtítulo ("JoJo ... Stone Ocean" ⊃
      "JoJo ..."): 0.7 — indica una entrada distinta que quizá no está en la
      biblioteca. Si lo sobrante es numeración de episodio ("Episode 12"), sí
      es la misma obra: 0.9.
    - Candidato más largo sin marcador ("Frieren" ⊂ "Sousou no Frieren"): 0.9.
    """
    index = longer.find(shorter)
    leftover = " ".join((longer[:index] + " " + longer[index + len(shorter):]).split())
    if query_is_longer:
        return 0.9 if not leftover or _EPISODE_JUNK.match(leftover) else 0.7
    if leftover and _SEQUEL_MARKER.match(leftover):
        return 0.7
    return 0.9


def _similarity(left: str, right: str) -> float:
    """Similitud entre el título buscado (``left``, p. ej. archivo) y un candidato."""
    left_forms = _search_forms(left, is_query=True)
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
                and normalized_left in normalized_right
            ):
                scores.append(
                    _containment_score(normalized_left, normalized_right, query_is_longer=False)
                )
            elif (
                min(len(normalized_left), len(normalized_right)) >= 4
                and normalized_right in normalized_left
            ):
                scores.append(
                    _containment_score(normalized_right, normalized_left, query_is_longer=True)
                )
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


def find_best_search_match(
    raw_title: str | None,
    anime_title: str | None,
    results: list,
    search_hints: list[str] | None = None,
    min_score: float = 0.6,
) -> tuple[object | None, float]:
    """Pick the provider-catalog search result whose titles best match the page title.

    Like MALSync: score every result against all of its titles (romaji/english/native/
    synonyms) and accept the best above ``min_score``. ``results`` are SearchResult-like
    objects exposing the same title fields as MediaItem (duck-typed via ``_titles``).
    """
    search_titles = [value for value in [anime_title, raw_title, *(search_hints or [])] if value]
    if not search_titles or not results:
        return None, 0.0
    scored = [
        (max((_similarity(st, t) for st in search_titles for t in _titles(item)), default=0.0), item)
        for item in results
    ]
    scored.sort(key=lambda result: result[0], reverse=True)
    best_score, best = scored[0]
    if best_score < min_score:
        return None, best_score
    return best, best_score


def rank_matches(
    raw_title: str | None,
    anime_title: str | None,
    items: list,
    search_hints: list[str] | None = None,
    limit: int = 5,
    floor: float = 0.55,
) -> list[tuple[float, object]]:
    """Top-``limit`` items scored against the page title, best first, above ``floor``.

    ``floor`` is deliberately above SequenceMatcher's noise level (unrelated short titles
    reach ~0.45 when they share filler words like "no"/"to") so suggestions stay relevant
    instead of listing loosely-similar series from the library.

    Used to offer alternative suggestions in Now Playing when the single best match is
    weak or ambiguous. Duck-typed via ``_titles`` so it works for library MediaItems and
    catalogue SearchResults alike.
    """
    search_titles = [value for value in [anime_title, raw_title, *(search_hints or [])] if value]
    if not search_titles or not items:
        return []
    scored = [
        (max((_similarity(st, t) for st in search_titles for t in _titles(item)), default=0.0), item)
        for item in items
    ]
    scored.sort(key=lambda result: result[0], reverse=True)
    return [(score, item) for score, item in scored[:limit] if score >= floor]


@lru_cache(maxsize=8192)
def _tokens(value: str) -> frozenset[str]:
    return frozenset(t for t in _TOKEN.findall(normalize_title(value).casefold()) if len(t) >= 2)


def build_token_index(library: list[MediaItem]) -> dict[str, list[MediaItem]]:
    """Inverted index token -> items, so a bulk scan only fuzzy-compares each file against
    library entries that share a word, instead of the whole (possibly huge) library."""
    index: dict[str, list[MediaItem]] = defaultdict(list)
    for item in library:
        for token in {tok for title in _titles(item) for tok in _tokens(title)}:
            index[token].append(item)
    return index


def match_from_index(
    title: str | None,
    index: dict[str, list[MediaItem]],
    min_score: float = 0.9,
    bucket_cap: int = 200,
) -> tuple[MediaItem | None, float]:
    """Fuzzy-match ``title`` against only the index entries that share a token.

    Tokens with an oversized bucket (common particles like "no"/"season") are skipped as
    non-discriminative; if that leaves nothing, the single smallest bucket is used so a
    title made only of common words still gets a chance.

    ``min_score`` 0.9 a propósito: esto corre desatendido sobre carpetas completas y
    solo la igualdad exacta (1.0) o la contención limpia (0.9) son evidencia suficiente.
    El ratio difuso llega a ~0.85 entre temporadas distintas de una franquicia (romaji
    alternativo + marcador), así que todo lo demás queda para asociación manual en vez
    de etiquetar mal los archivos.
    """
    if not title:
        return None, 0.0
    tokens = _tokens(title)
    candidates: dict[int, MediaItem] = {}
    smallest: list[MediaItem] | None = None
    for token in tokens:
        bucket = index.get(token)
        if not bucket:
            continue
        if smallest is None or len(bucket) < len(smallest):
            smallest = bucket
        if len(bucket) <= bucket_cap:
            for item in bucket:
                candidates[item.id] = item
    if not candidates and smallest is not None:
        candidates = {item.id: item for item in smallest}
    if not candidates:
        return None, 0.0
    return find_best_match(title, title, None, list(candidates.values()), min_score=min_score)


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
    if (
        len(scored) > 1
        and scored[1][0] >= effective_min_score
        and best_score - scored[1][0] < 0.03
        # La misma obra puede existir duplicada (una copia canónica por proveedor);
        # un empate entre títulos idénticos no es ambigüedad real.
        and fold_title(scored[1][1].title) != fold_title(best_match.title)
    ):
        return None, best_score
    return best_match, best_score
