"""Alerts: one row per subject to review, from the scored pairs.

match_score holds one row per subject-target pair. An analyst reviews a
subject, not a pair, so pairs at or above THRESHOLD are grouped:

- One subject, several targets: a company named only with the words of a
  currency exchange that scores against six sanctioned exchange houses is
  one alert listing six targets, not six alerts.
- One person, several officer IDs: Companies House sometimes files the same
  person twice at one company (as director and as secretary, only one of
  them with a birth date). Officers with the same matched name who share a
  current company are folded into one alert. Officer IDs that merely share
  a name, at different companies, stay separate: merging those would be
  entity resolution, and a wrong merge is worse than a duplicate alert.

Officers who resigned within the lookback window (stg_ch_officer.is_screened)
are screened too. An alert whose officers hold no current appointment is
marked resigned_only, so a reviewer knows to check the resignation date
against the designation date.

Scores are unchanged; this only changes how alerts are counted and shown.
"""

from collections import defaultdict
from dataclasses import dataclass

THRESHOLD = 70  # chosen in docs/evaluation.md


@dataclass(frozen=True)
class Pair:
    subject_type: str  # officer or company
    subject_id: str
    target_id: str
    entity_kind: str
    score: float
    subject_name: str
    reasons: str


@dataclass
class Alert:
    subject_type: str
    entity_kind: str
    subject_ids: list[str]
    subject_name: str
    top_score: float
    targets: list[tuple[str, float]]  # (target_id, best score), best first
    top_reasons: str
    resigned_only: bool = False

    @property
    def alert_id(self) -> str:
        return f"{self.subject_type}:{self.subject_ids[0]}"


def group_alerts(
    pairs: list[Pair],
    officer_companies: dict[str, set[str]],
    threshold: float = THRESHOLD,
    current_officers: set[str] | None = None,
) -> list[Alert]:
    """Group alerting pairs into one alert per subject. Pure function.

    officer_companies: companies of each screened officer (current or
    recently resigned). current_officers: officers with a current
    appointment; None treats every officer as current.
    """
    hits = [p for p in pairs if p.score >= threshold]

    # Union-find over subjects: fold officers with the same matched name and
    # a shared current company.
    parent: dict[tuple[str, str], tuple[str, str]] = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    first_seen: dict[tuple[str, str], tuple[str, str]] = {}
    for p in hits:
        key = (p.subject_type, p.subject_id)
        find(key)
        if p.subject_type != "officer":
            continue
        for company in officer_companies.get(p.subject_id, ()):
            shared = (p.subject_name, company)
            if shared in first_seen:
                parent[find(key)] = find(first_seen[shared])
            else:
                first_seen[shared] = key

    groups: dict[tuple[str, str], list[Pair]] = defaultdict(list)
    for p in hits:
        groups[find((p.subject_type, p.subject_id))].append(p)

    alerts = []
    for members in groups.values():
        best_per_target: dict[str, float] = {}
        for p in members:
            best_per_target[p.target_id] = max(best_per_target.get(p.target_id, 0), p.score)
        top = max(members, key=lambda p: (p.score, p.subject_id))
        alerts.append(
            Alert(
                subject_type=top.subject_type,
                entity_kind=top.entity_kind,
                subject_ids=sorted({p.subject_id for p in members}),
                subject_name=top.subject_name,
                top_score=top.score,
                targets=sorted(best_per_target.items(), key=lambda t: (-t[1], t[0])),
                top_reasons=top.reasons,
                resigned_only=(
                    current_officers is not None
                    and top.subject_type == "officer"
                    and not any(p.subject_id in current_officers for p in members)
                ),
            )
        )
    return sorted(alerts, key=lambda a: (-a.top_score, a.alert_id))


def run() -> None:
    from ingest.loader import get_connection

    conn = get_connection()
    pairs = [
        Pair(*row)
        for row in conn.execute(
            "select subject_type, subject_id, target_id, entity_kind, score, subject_name, "
            "reasons from match_score"
        )
    ]
    if not pairs:
        raise SystemExit("match_score is empty: run `make candidates score` first")
    officer_companies: dict[str, set[str]] = defaultdict(set)
    current_officers: set[str] = set()
    for officer_id, company, is_current in conn.execute(
        "select officer_id, company_number, is_current from stg_ch_officer where is_screened"
    ):
        officer_companies[officer_id].add(company)
        if is_current:
            current_officers.add(officer_id)

    alerts = group_alerts(pairs, officer_companies, current_officers=current_officers)

    conn.execute("drop table if exists match_alert")
    conn.execute(
        """
        create table match_alert (
            alert_id       text primary key,
            subject_type   text not null,
            entity_kind    text not null,
            subject_ids    text[] not null,
            subject_name   text not null,
            top_score      real not null,
            n_targets      int not null,
            target_ids     text[] not null,
            target_scores  real[] not null,
            top_reasons    text not null,
            resigned_only  boolean not null,
            created_at     timestamptz not null default now()
        )
        """
    )
    with conn.cursor() as cur:
        cur.executemany(
            "insert into match_alert (alert_id, subject_type, entity_kind, subject_ids, "
            "subject_name, top_score, n_targets, target_ids, target_scores, top_reasons, "
            "resigned_only) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            [
                (
                    a.alert_id,
                    a.subject_type,
                    a.entity_kind,
                    a.subject_ids,
                    a.subject_name,
                    a.top_score,
                    len(a.targets),
                    [t for t, _ in a.targets],
                    [s for _, s in a.targets],
                    a.top_reasons,
                    a.resigned_only,
                )
                for a in alerts
            ],
        )
    conn.commit()
    n_pairs = sum(p.score >= THRESHOLD for p in pairs)
    resigned = sum(a.resigned_only for a in alerts)
    print(
        f"{len(alerts)} alerts ({resigned} resigned officers only) "
        f"from {n_pairs} pairs at threshold {THRESHOLD}"
    )


if __name__ == "__main__":
    run()
