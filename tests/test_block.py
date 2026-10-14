"""Tests for candidate generation. No database needed."""

from matching.block import Name, candidate_pairs


def names(*texts: str, prefix: str) -> list[Name]:
    return [Name(f"{prefix}{i}", f"{prefix}{i}", t) for i, t in enumerate(texts)]


def pairs_as_text(subjects, targets):
    s = {n.name_id: n.text for n in subjects}
    t = {n.name_id: n.text for n in targets}
    return {(s[c.subject_name_id], t[c.target_name_id]) for c in candidate_pairs(subjects, targets)}


def test_word_order_and_spelling_variants_are_candidates():
    s = names("MOHAMED ALI", prefix="s")
    t = names("ALI MOHAMMED", prefix="t")
    assert pairs_as_text(s, t) == {("MOHAMED ALI", "ALI MOHAMMED")}


def test_extra_name_parts_are_candidates():
    s = names("JOHN ANDREW SMITH", prefix="s")
    t = names("JOHN SMITH", prefix="t")
    assert ("JOHN ANDREW SMITH", "JOHN SMITH") in pairs_as_text(s, t)


def test_single_word_target_does_not_match_everything_containing_it():
    s = names("PAUL MARTIN HOLLOWAY", "MARTIN FOXLEY", prefix="s")
    t = names("MARTIN", prefix="t")
    assert pairs_as_text(s, t) == set()


def test_repeated_word_counts_once_for_the_guard():
    s = names("PETER ANTHONY GRANT", prefix="s")
    t = names("ANTHONY ANTHONY", prefix="t")
    assert pairs_as_text(s, t) == set()


def test_unrelated_names_are_not_candidates():
    s = names("KAREN WHITLOW", prefix="s")
    t = names("VLADIMIR IVANOV", prefix="t")
    assert pairs_as_text(s, t) == set()


def test_scores_are_reported():
    s = names("KAREN WHITLOW", prefix="s")
    t = names("KAREN WHITLOW", prefix="t")
    [c] = candidate_pairs(s, t)
    assert (c.sort_score, c.set_score) == (100, 100)


def test_empty_inputs():
    assert candidate_pairs([], names("A B", prefix="t")) == []
