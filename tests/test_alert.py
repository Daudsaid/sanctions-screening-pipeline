"""Tests for alert grouping. No database needed."""

from matching.alert import Pair, group_alerts


def pair(subject_id, target_id, score, name="[officer]", subject_type="officer"):
    kind = "person" if subject_type == "officer" else "organization"
    return Pair(subject_type, subject_id, target_id, kind, score, name, f"name {score}")


def test_pairs_below_threshold_do_not_alert():
    assert group_alerts([pair("O1", "T1", 69.9)], {}, threshold=70) == []


def test_one_subject_hitting_several_targets_is_one_alert():
    pairs = [
        pair("C1", f"T{i}", s, "[company]", "company")
        for i, s in enumerate([78.1, 71.6, 77.8])
    ]
    [alert] = group_alerts(pairs, {}, threshold=70)
    assert alert.alert_id == "company:C1"
    assert alert.top_score == 78.1
    assert [t for t, _ in alert.targets] == ["T0", "T2", "T1"]  # best first


def test_same_name_officers_at_one_company_fold_into_one_alert():
    pairs = [pair("O1", "T1", 100), pair("O2", "T1", 95)]
    [alert] = group_alerts(pairs, {"O1": {"C1"}, "O2": {"C1", "C9"}}, threshold=70)
    assert alert.subject_ids == ["O1", "O2"]
    assert alert.targets == [("T1", 100)]  # best score per target


def test_same_name_officers_at_different_companies_stay_separate():
    pairs = [pair("O1", "T1", 100), pair("O2", "T1", 100)]
    alerts = group_alerts(pairs, {"O1": {"C1"}, "O2": {"C2"}}, threshold=70)
    assert len(alerts) == 2


def test_different_names_at_one_company_stay_separate():
    pairs = [pair("O1", "T1", 100, "[officer]"), pair("O2", "T2", 90, "[officer]")]
    alerts = group_alerts(pairs, {"O1": {"C1"}, "O2": {"C1"}}, threshold=70)
    assert len(alerts) == 2


def test_folding_is_transitive_through_shared_companies():
    pairs = [pair("O1", "T1", 100), pair("O2", "T1", 90), pair("O3", "T1", 80)]
    companies = {"O1": {"C1"}, "O2": {"C1", "C2"}, "O3": {"C2"}}
    [alert] = group_alerts(pairs, companies, threshold=70)
    assert alert.subject_ids == ["O1", "O2", "O3"]
