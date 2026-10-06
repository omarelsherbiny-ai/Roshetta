# tests/test_fuzzy_match.py
"""Typo-tolerant product ranking (task 9b, command 2)."""
from server.app.services.fuzzy_match import normalize, rank_matches, score_name

CATALOG = [
    (1, ["بانادول", "Panadol"]),
    (2, ["بانادول اكسترا", "Panadol Extra"]),
    (3, ["اوجمنتين", "Augmentin"]),
    (4, ["فولتارين", "Voltaren"]),
    (5, ["بروفين", "Brufen"]),
]


def top(query, **kw):
    return rank_matches(query, CATALOG, **kw)


def test_exact_and_case_do_not_matter():
    assert top("PANADOL")[0] == 1


def test_missing_letter_is_found():
    assert top("panadl")[0] == 1
    assert top("augmentn")[0] == 3


def test_typo_inside_the_first_four_letters_is_found():
    # the old four-letter prefix fallback missed all of these
    assert top("pnadol")[0] == 1
    assert top("vltaren")[0] == 4
    assert top("aguemntin")[0] == 3


def test_extra_and_swapped_letters_are_found():
    assert top("panadoll")[0] == 1
    assert top("voltarne")[0] == 4


def test_arabic_spelling_variants():
    assert top("بنادول")[0] == 1
    assert top("أوجمنتين")[0] == 3
    assert top("بروفن")[0] == 5


def test_prefix_returns_every_product_that_starts_with_it():
    assert set(top("panadol")) >= {1, 2}
    assert set(top("pana")) >= {1, 2}


def test_unrelated_text_returns_nothing():
    assert top("zzzzqqq") == []
    assert top("") == []


def test_limit_and_stable_order():
    assert len(top("panadol", limit=1)) == 1
    assert top("panadol") == top("panadol")


def test_normalize_and_score_edges():
    assert normalize("  أَوجمنتين  ") == "اوجمنتين"
    assert normalize(None) == ""
    assert score_name("", "x") == 0.0
    assert score_name("abc", "abc") == 1.0