# server/app/services/fuzzy_match.py
"""Typo-tolerant product name ranking for the assistant (task 9b, command 2).

`match_product` used to fall back to the first four letters, so a typo inside them found
nothing. This ranks every candidate name by how close it is to what was typed (a missing,
extra, swapped or wrong letter, a prefix, a part of the name) so the assistant can offer
the real products to choose from. Pure Python: no database, no network.
"""
import re
from difflib import SequenceMatcher
from typing import Iterable, List, Optional, Sequence, Tuple

MIN_SCORE = 0.6

_ARABIC_MARKS = re.compile("[\u0610-\u061a\u064b-\u065f\u0670\u0640]")
_ARABIC_LETTERS = str.maketrans({
    "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا",
    "ى": "ي", "ئ": "ي", "ة": "ه", "ؤ": "و",
})
_SPACES = re.compile(r"\s+")


def normalize(text: Optional[str]) -> str:
    """Lower case, no Arabic marks, one spelling per Arabic letter family, single spaces."""
    value = _ARABIC_MARKS.sub("", str(text or "")).translate(_ARABIC_LETTERS).lower().strip()
    return _SPACES.sub(" ", value)


def score_name(query: str, name: str) -> float:
    """0 to 1: how close `query` is to `name` (both already normalized)."""
    if not query or not name:
        return 0.0
    if query == name:
        return 1.0
    best = SequenceMatcher(None, query, name).ratio()
    if name.startswith(query) or query.startswith(name):
        best = max(best, 0.92)
    elif len(query) >= 3 and query in name:
        best = max(best, 0.85)
    # A typo in one word of a longer name ("panadol extra"): compare word by word.
    for word in name.split(" "):
        if len(word) >= 3 and len(query) >= 3:
            best = max(best, SequenceMatcher(None, query, word).ratio() * 0.95)
    return best


def rank_matches(
    query: str,
    candidates: Iterable[Tuple[int, Sequence[Optional[str]]]],
    limit: int = 5,
    min_score: float = MIN_SCORE,
) -> List[int]:
    """Ids of the closest candidates, best first. Each candidate is (id, [names...]).
    Ties break on the lower id so the order is stable."""
    needle = normalize(query)
    scored: List[Tuple[float, int]] = []
    for ident, names in candidates:
        top = max((score_name(needle, normalize(name)) for name in names if name), default=0.0)
        if top >= min_score:
            scored.append((top, ident))
    scored.sort(key=lambda pair: (-pair[0], pair[1]))
    return [ident for _, ident in scored[:limit]]