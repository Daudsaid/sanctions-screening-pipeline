"""Scoring: turn each candidate into one 0-100 score with readable reasons.

Works per entity pair (one officer or company against one sanctions target),
keeping the best-scoring pair of names between them.

1. Name (0-100): words are matched one to one, allowing small spelling
   differences (MOHAMED / MOHAMMED). Each word is weighted by rarity
   (inverse document frequency over both sides), so a shared ROMASHKA counts
   far more than a shared MANAGEMENT or MOHAMMED. Unmatched words on either
   side pull the score down. Words of four letters or fewer must match
   exactly: one letter is too much of a short word (IFC / IFDC, TACO /
   TAFCO) to count as a spelling variant.
2. Date of birth (persons only), added to the name score:
     same year and month                 +15
     same year, target gives year only   +10
     same year, different month           +5
     no target date within a year        -40
     either side missing                   0
   Companies House gives year and month, so that is the finest comparison.
   A clear conflict is strong evidence of a different person.
3. Nationality (persons only): +5 if any officer nationality is among the
   target's countries, -5 if both are known and none overlap. Small, because
   OFAC "countries" mixes nationality, citizenship and residence.

The weights are set by hand and are a starting point. The evaluation set
decides the alert threshold, and whether these weights need changing.
"""

import math
from collections import Counter
from dataclasses import dataclass, field

from rapidfuzz import fuzz

WORD_MATCH = 85  # fuzz.ratio needed for two words to count as the same
SHORT_WORD = 4  # words this short must match exactly (IFC is not IFDC)
MIN_WEIGHT = 0.1

DOB_MONTH = 15
DOB_YEAR_ONLY_TARGET = 10
DOB_YEAR = 5
DOB_CONFLICT = -40
NAT_MATCH = 5
NAT_MISMATCH = -5


def word_weights(names_by_entity: dict[str, list[str]]) -> dict[str, float]:
    """IDF weight per word: log(entities / entities containing the word)."""
    df: Counter[str] = Counter()
    for names in names_by_entity.values():
        df.update({w for name in names for w in name.split()})
    n = len(names_by_entity)
    return {w: max(math.log(n / c), MIN_WEIGHT) for w, c in df.items()}


def name_score(a: str, b: str, weights: dict[str, float]) -> float:
    """Weighted word overlap, 0-100. Each word matches at most one word."""
    a_words, b_words = a.split(), b.split()
    if not a_words or not b_words:
        return 0.0

    def w(word: str) -> float:
        return weights.get(word, max(weights.values(), default=1.0))

    def similarity(x: str, y: str) -> float:
        if min(len(x), len(y)) <= SHORT_WORD:
            return 100.0 if x == y else 0.0
        return fuzz.ratio(x, y)

    pairs = sorted(
        ((similarity(x, y), i, j) for i, x in enumerate(a_words) for j, y in enumerate(b_words)),
        reverse=True,
    )
    used_a, used_b, matched = set(), set(), 0.0
    for sim, i, j in pairs:
        if sim < WORD_MATCH:
            break
        if i in used_a or j in used_b:
            continue
        used_a.add(i)
        used_b.add(j)
        matched += (w(a_words[i]) + w(b_words[j])) * sim / 100

    total = sum(map(w, a_words)) + sum(map(w, b_words))
    return 100 * matched / total


def dob_evidence(year: int | None, month: int | None, target_dates: list[str]) -> tuple[int, str]:
    if year is None or not target_dates:
        return 0, "date of birth unknown on one side"
    best = None
    for d in target_dates:
        t_year = int(d[:4])
        t_month = int(d[5:7]) if len(d) >= 7 else None
        if t_year != year:
            continue
        if t_month is None:
            score = (DOB_YEAR_ONLY_TARGET, f"birth year {year} matches (target gives year only)")
        elif month is not None and t_month == month:
            score = (DOB_MONTH, f"birth month {year}-{month:02d} matches")
        else:
            score = (DOB_YEAR, f"birth year {year} matches, month differs")
        if best is None or score[0] > best[0]:
            best = score
    if best:
        return best
    if any(abs(int(d[:4]) - year) <= 1 for d in target_dates):
        return 0, f"birth year {year} within a year of {', '.join(target_dates)}"
    return DOB_CONFLICT, f"birth year {year} conflicts with {', '.join(target_dates)}"


def nationality_evidence(subject: set[str], target: set[str]) -> tuple[int, str]:
    if not subject or not target:
        return 0, "nationality unknown on one side"
    shared = subject & target
    if shared:
        return NAT_MATCH, f"nationality matches ({', '.join(sorted(shared))})"
    return NAT_MISMATCH, (
        f"nationality differs ({', '.join(sorted(subject))} vs {', '.join(sorted(target))})"
    )


@dataclass
class Scored:
    score: float
    name: float
    subject_name: str
    target_name: str
    reasons: list[str] = field(default_factory=list)


def score_pair(
    name_pairs: list[tuple[str, str]],
    weights: dict[str, float],
    kind: str,
    subject_dob: tuple[int | None, int | None] = (None, None),
    target_dates: list[str] | None = None,
    subject_nat: set[str] | None = None,
    target_nat: set[str] | None = None,
) -> Scored:
    """Score one subject-target entity pair from its candidate name pairs."""
    best_name, s_name, t_name = max((name_score(s, t, weights), s, t) for s, t in name_pairs)
    result = Scored(
        best_name, best_name, s_name, t_name, [f"name {best_name:.0f}: {s_name} / {t_name}"]
    )
    if kind == "person":
        for points, reason in (
            dob_evidence(*subject_dob, target_dates or []),
            nationality_evidence(subject_nat or set(), target_nat or set()),
        ):
            result.score += points
            if points:
                result.reasons.append(f"{points:+d} {reason}")
    result.score = max(0.0, min(100.0, result.score))
    return result


def load_weights(conn) -> dict[str, dict[str, float]]:
    """Word weights per entity kind, over every subject and target name."""
    from collections import defaultdict

    weights = {}
    for kind in ("person", "organization"):
        names = defaultdict(list)
        for side, e_id, core in conn.execute(
            "select side, entity_id, name_core from int_name_norm where entity_kind = %s",
            (kind,),
        ):
            names[(side, e_id)].append(core)
        weights[kind] = word_weights(names)
    return weights


def load_targets(conn) -> dict[str, tuple[list[str], set[str]]]:
    """Birth dates and countries per sanctions target."""
    return {
        t: (dates, set(countries))
        for t, dates, countries in conn.execute(
            "select target_id, birth_dates, countries from stg_sanctions_target"
        )
    }


def run() -> None:
    from collections import defaultdict

    from ingest.loader import get_connection

    conn = get_connection()
    conn.execute(
        """
        create table if not exists match_score (
            subject_type  text not null,
            subject_id    text not null,
            target_id     text not null,
            entity_kind   text not null,
            score         real not null,
            name_score    real not null,
            subject_name  text not null,
            target_name   text not null,
            reasons       text not null,
            created_at    timestamptz not null default now(),
            primary key (subject_type, subject_id, target_id)
        )
        """
    )
    conn.execute("truncate match_score")

    rows = conn.execute(
        """
        select c.entity_kind, s.entity_type, s.entity_id, s.name_core, t.entity_id, t.name_core
        from match_candidate c
        join int_name_norm s on s.name_id = c.subject_name_id
        join int_name_norm t on t.name_id = c.target_name_id
        """
    ).fetchall()
    pairs = defaultdict(list)
    for kind, s_type, s_id, s_name, t_id, t_name in rows:
        pairs[(kind, s_type, s_id, t_id)].append((s_name, t_name))

    weights = load_weights(conn)
    dob = {
        o: (y, m)
        for o, y, m in conn.execute(
            "select officer_id, max(birth_year), max(birth_month) from stg_ch_officer "
            "where officer_kind = 'person' group by officer_id"
        )
    }
    nat = defaultdict(set)
    for o, iso in conn.execute(
        "select o.officer_id, n.iso2 from int_officer_nationality n "
        "join stg_ch_officer o using (appointment_id) where n.iso2 is not null"
    ):
        nat[o].add(iso)
    targets = load_targets(conn)

    out = []
    for (kind, s_type, s_id, t_id), name_pairs in pairs.items():
        t_dates, t_countries = targets[t_id]
        r = score_pair(
            name_pairs,
            weights[kind],
            kind,
            subject_dob=dob.get(s_id, (None, None)),
            target_dates=t_dates,
            subject_nat=nat.get(s_id),
            target_nat=t_countries,
        )
        out.append(
            (
                s_type,
                s_id,
                t_id,
                kind,
                round(r.score, 1),
                round(r.name, 1),
                r.subject_name,
                r.target_name,
                "; ".join(r.reasons),
            )
        )

    with (
        conn.cursor() as cur,
        cur.copy(
            "COPY match_score (subject_type, subject_id, target_id, entity_kind, score, "
            "name_score, subject_name, target_name, reasons) FROM STDIN"
        ) as copy,
    ):
        for row in out:
            copy.write_row(row)
    conn.commit()
    print(f"scored {len(out)} subject-target pairs")


if __name__ == "__main__":
    run()
