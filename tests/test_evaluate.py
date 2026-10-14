"""Tests for the evaluation's plant generation and summary. No database needed."""

import random

import pytest

from eval.evaluate import (
    ORG_CHANGES,
    PERSON_CHANGES,
    RESULTS_END,
    RESULTS_START,
    VARIANTS,
    Plant,
    apply_change,
    make_plants,
    middle_dropped,
    plant_dob,
    summarise,
    transliteration,
    typo,
    uk_group,
    word_order,
    write_results,
)
from matching.score import DOB_CONFLICT, dob_evidence


def rng():
    return random.Random(0)


@pytest.mark.parametrize("seed", range(50))
def test_typo_changes_exactly_one_word(seed):
    name = "ROMASHKA TRADING HOUSE"
    out = typo(name, random.Random(seed))
    changed = [(a, b) for a, b in zip(name.split(), out.split(), strict=True) if a != b]
    assert len(changed) == 1


def test_word_order_puts_person_surname_first():
    assert word_order("ALI HASSAN MOHAMED", rng(), "person") == "HASSAN MOHAMED ALI"


def test_word_order_needs_two_distinct_words():
    assert word_order("ROMASHKA", rng(), "organization") is None
    assert word_order("ANTHONY ANTHONY", rng(), "person") is None


def test_middle_dropped_keeps_first_and_last_names():
    out = middle_dropped("JUAN LUIS GUZMAN ENRIQUEZ", rng())
    words = out.split()
    assert len(words) == 3 and words[0] == "JUAN" and words[-1] == "ENRIQUEZ"
    assert middle_dropped("SAJJAD AHADZADEH", rng()) is None


def test_transliteration_swaps_for_a_variant_of_the_same_name():
    out = transliteration("MOHAMMED ALI", rng())
    assert out.split()[0] in VARIANTS["MOHAMMED"] and out.endswith(" ALI")
    assert transliteration("JOHN SMITH", rng()) is None


def test_uk_group_adds_a_word_and_a_legal_suffix():
    out = uk_group("CRYSTAL GROUP", rng())
    assert out.startswith("CRYSTAL GROUP UK ")
    assert uk_group("ACME UK GROUP", rng()) is None


def test_every_change_type_applies_to_a_typical_name():
    for change in PERSON_CHANGES:
        assert apply_change(change, "MOHAMMED JAVAD IMANIRAD", "person", rng())
    for change in ORG_CHANGES:
        assert apply_change(change, "SILOVYE MASHINY", "organization", rng())


@pytest.mark.parametrize(
    "dates", [["1975-03-14"], ["1975"], ["1958-06-13", "1963-05-06", "1963-08-06"]]
)
def test_plant_dob_agrees_or_conflicts_as_scoring_sees_it(dates):
    r = rng()
    for _ in range(20):
        assert dob_evidence(*plant_dob(dates, True, r), dates)[0] > 0
        assert dob_evidence(*plant_dob(dates, False, r), dates)[0] == DOB_CONFLICT


SOURCES = [
    (f"T{i:03d}", name, ["1970-01-01"])
    for i, name in enumerate(
        ["MOHAMMED ALI HASSAN", "SERGEY IVANOV", "JUAN LUIS GUZMAN ENRIQUEZ", "AHMED KHALED"] * 30
    )
]


def test_make_plants_is_seeded_and_balanced():
    a = make_plants("person", SOURCES, seed=1, n=50)
    b = make_plants("person", SOURCES, seed=1, n=50)
    assert [(p.target_id, p.raw, p.dob) for p in a] == [(p.target_id, p.raw, p.dob) for p in b]
    assert len(a) == 50
    assert len({p.target_id for p in a}) == 50  # one plant per target
    for change in PERSON_CHANGES:
        assert sum(p.change == change for p in a) == 10
    assert 15 <= sum(p.is_true for p in a) <= 35  # about half agree on birth date


def test_a_different_seed_gives_a_different_sample():
    a = make_plants("person", SOURCES, seed=1, n=50)
    b = make_plants("person", SOURCES, seed=2, n=50)
    assert {p.target_id for p in a} != {p.target_id for p in b}


def test_removing_a_target_leaves_other_plants_unchanged():
    full = make_plants("person", SOURCES, seed=1, n=50)
    dropped = full[0].target_id
    fewer = make_plants("person", [s for s in SOURCES if s[0] != dropped], seed=1, n=50)
    plant = {p.target_id: (p.change, p.raw, p.dob, p.is_true) for p in full}
    kept = [p for p in fewer if p.target_id in plant]
    unchanged = sum(plant[p.target_id] == (p.change, p.raw, p.dob, p.is_true) for p in kept)
    assert unchanged >= len(full) - 5  # only a handful move, not the whole sample


def test_organisation_plants_are_all_true_and_have_no_dob():
    plants = make_plants("organization", [(t, n, []) for t, n, _ in SOURCES], n=40)
    assert all(p.is_true and p.dob is None for p in plants)


def plant(pid, kind, change, is_true):
    return Plant(pid, kind, "T", change, "SRC", "RAW", is_true)


def test_summarise_counts_recall_and_alerts():
    plants = [
        plant("p1", "person", "typo", True),
        plant("p2", "person", "typo", False),
        plant("o1", "organization", "typo", True),
        plant("o2", "organization", "uk_group", True),
    ]
    scores = {"p1": 90, "p2": 55, "o1": 72, "o2": 0}
    real = [("person", 81), ("organization", 70), ("organization", 40)]
    s = summarise(plants, scores, real, name_only={"p1": 75, "p2": 15}, thresholds=[50, 75])
    low, high = s["rows"]
    assert low["recall"] == pytest.approx(2 / 3)
    assert high["recall"] == pytest.approx(1 / 3)
    assert high["recall_person_name_only"] == 1.0
    assert (low["real_person"], low["real_org"]) == (1, 1)
    assert (high["real_person"], high["real_org"]) == (1, 0)
    assert (low["conflict"], high["conflict"]) == (1, 0)
    assert low["by_change"]["org typo"] == 1.0
    assert s["not_candidates"]["org uk group"] == 1


def test_write_results_keeps_hand_written_text(tmp_path):
    doc = tmp_path / "evaluation.md"
    doc.write_text(f"# Intro\n\n{RESULTS_START}\nold\n{RESULTS_END}\n\n## Why\n")
    write_results(doc, f"{RESULTS_START}\nnew\n{RESULTS_END}")
    assert doc.read_text() == f"# Intro\n\n{RESULTS_START}\nnew\n{RESULTS_END}\n\n## Why\n"
