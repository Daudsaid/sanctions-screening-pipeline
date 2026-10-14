"""Tests for scoring. No database needed."""

import pytest

from matching.score import (
    DOB_CONFLICT,
    DOB_MONTH,
    DOB_NEAR,
    DOB_YEAR_ONLY_TARGET,
    dob_evidence,
    name_score,
    nationality_evidence,
    score_pair,
    word_weights,
)

# A tiny corpus: MANAGEMENT and MOHAMMED are common, the rest are rare.
CORPUS = {
    "e1": ["ALPHA ASSET MANAGEMENT"],
    "e2": ["BETA MANAGEMENT"],
    "e3": ["GAMMA MANAGEMENT"],
    "e4": ["ROMASHKA"],
    "e5": ["MOHAMMED ALI"],
    "e6": ["MOHAMMED HASSAN"],
    "e7": ["MOHAMMED IQBAL"],
}
W = word_weights(CORPUS)


def test_rare_words_weigh_more_than_common_ones():
    assert W["ROMASHKA"] > W["MANAGEMENT"]


def test_identical_names_score_100():
    assert name_score("ROMASHKA", "ROMASHKA", W) == pytest.approx(100)


def test_sharing_a_common_word_scores_lower_than_sharing_a_rare_one():
    common = name_score("ALPHA MANAGEMENT", "BETA MANAGEMENT", W)
    rare = name_score("ALPHA MANAGEMENT", "ALPHA GAMMA", W)
    assert common < rare


def test_word_order_and_spelling_variants_score_high():
    assert name_score("MOHAMED ALI", "ALI MOHAMMED", W) > 90


def test_short_words_must_match_exactly():
    assert name_score("IFC", "IFDC", W) == 0
    assert name_score("TACO", "TAFCO", W) == 0


def test_each_word_matches_once():
    # ALI on one side cannot be matched twice by ALI ALI on the other
    assert name_score("ALI", "ALI ALI", W) < 100


@pytest.mark.parametrize(
    ("year", "month", "dates", "points"),
    [
        (1980, 6, ["1980-06-15"], DOB_MONTH),
        (1980, 6, ["1980"], DOB_YEAR_ONLY_TARGET),
        (1980, 6, ["1980-09-01"], DOB_NEAR),
        (1989, 12, ["1990-01-05"], DOB_NEAR),  # one month apart across new year
        (1991, 12, ["1992-05-07"], DOB_NEAR),
        (1980, 1, ["1980-12-01"], DOB_NEAR),  # 11 months, the widest "near"
        (1980, 1, ["1981-01-01"], 0),  # 12 months: within a year, neither way
        (1980, 6, ["1981"], 0),  # year-only target, one year out
        (1980, 6, ["1950-01-01"], DOB_CONFLICT),
        (1980, 6, ["1950-01-01", "1980-06-02"], DOB_MONTH),  # best date wins
        (None, None, ["1980-06-15"], 0),
        (1980, 6, [], 0),
    ],
)
def test_dob_evidence(year, month, dates, points):
    assert dob_evidence(year, month, dates)[0] == points


def test_nationality_evidence():
    assert nationality_evidence({"gb"}, {"gb", "ir"})[0] > 0
    assert nationality_evidence({"gb"}, {"ir"})[0] < 0
    assert nationality_evidence(set(), {"ir"})[0] == 0


def test_dob_conflict_sinks_an_exact_name_match():
    r = score_pair(
        [("MOHAMMED ALI", "MOHAMMED ALI")],
        W,
        "person",
        subject_dob=(1990, 1),
        target_dates=["1950-01-01"],
    )
    assert r.name == pytest.approx(100)
    assert r.score == pytest.approx(100 + DOB_CONFLICT)
    assert any("conflicts" in reason for reason in r.reasons)


def test_best_name_pair_is_used_and_score_is_capped():
    r = score_pair(
        [("BETA MANAGEMENT", "ROMASHKA"), ("ROMASHKA", "ROMASHKA")],
        W,
        "person",
        subject_dob=(1980, 6),
        target_dates=["1980-06-01"],
    )
    assert (r.subject_name, r.target_name) == ("ROMASHKA", "ROMASHKA")
    assert r.score == 100


def test_organisations_ignore_dob_and_nationality():
    r = score_pair(
        [("ROMASHKA", "ROMASHKA")],
        W,
        "organization",
        subject_dob=(1990, 1),
        target_dates=["1950-01-01"],
    )
    assert r.score == pytest.approx(100)
