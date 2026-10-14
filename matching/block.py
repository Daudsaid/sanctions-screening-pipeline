"""Candidate generation: which subject-target name pairs are worth scoring.

v1 compares every subject name with every target name of the same kind
(person with person, organisation with organisation). At this size that is
about 180M person pairs and 146M organisation pairs, which rapidfuzz scores
in a few seconds, so there is no blocking and no recall lost to it. See
docs/decisions.md for when that stops being true.

A pair becomes a candidate when either:
- token_sort_ratio >= SORT_CUTOFF: same words in any order, allowing
  spelling variation (MOHAMED ALI / ALI MOHAMMED), or
- token_set_ratio >= SET_CUTOFF and both names have at least two words: one
  name contains the other (MOHAMED ALI / MOHAMED ALI BADAS). The two-word
  guard stops single-word names (MARTIN, IM) matching everything that
  contains them. Words are counted once each, so ANTHONY ANTHONY is
  one word.

Candidates are deliberately generous. Deciding which ones alert is the job
of scoring, which adds dates of birth, nationality and word rarity.
"""

from dataclasses import dataclass

import numpy as np
from rapidfuzz import fuzz, process

SORT_CUTOFF = 80
SET_CUTOFF = 90
KINDS = ("person", "organization")


@dataclass(frozen=True)
class Name:
    name_id: str
    entity_id: str
    text: str  # name_core from int_name_norm


@dataclass(frozen=True)
class Candidate:
    subject_name_id: str
    target_name_id: str
    sort_score: int
    set_score: int


def candidate_pairs(subjects: list[Name], targets: list[Name]) -> list[Candidate]:
    """All subject-target pairs that pass either rule. Pure function."""
    if not subjects or not targets:
        return []
    s_text = [n.text for n in subjects]
    t_text = [n.text for n in targets]

    sort = process.cdist(
        s_text,
        t_text,
        scorer=fuzz.token_sort_ratio,
        score_cutoff=SORT_CUTOFF,
        dtype=np.uint8,
        workers=-1,
    )
    set_ = process.cdist(
        s_text,
        t_text,
        scorer=fuzz.token_set_ratio,
        score_cutoff=SET_CUTOFF,
        dtype=np.uint8,
        workers=-1,
    )
    # Distinct words: token_set_ratio ignores repeats, so ANTHONY ANTHONY is
    # one word and must not pass the guard.
    s_words = np.array([len(set(t.split())) for t in s_text])[:, None]
    t_words = np.array([len(set(t.split())) for t in t_text])[None, :]
    set_ok = (set_ > 0) & (s_words >= 2) & (t_words >= 2)

    rows, cols = np.nonzero((sort > 0) | set_ok)
    return [
        Candidate(
            subject_name_id=subjects[i].name_id,
            target_name_id=targets[j].name_id,
            sort_score=int(sort[i, j]),
            set_score=int(set_[i, j]),
        )
        for i, j in zip(rows, cols, strict=True)
    ]


def load_names(conn, side: str, kind: str) -> list[Name]:
    rows = conn.execute(
        "select name_id, entity_id, name_core from int_name_norm "
        "where side = %s and entity_kind = %s order by name_id",
        (side, kind),
    ).fetchall()
    return [Name(*r) for r in rows]


def run() -> None:
    from ingest.loader import get_connection

    conn = get_connection()
    conn.execute(
        """
        create table if not exists match_candidate (
            subject_name_id text not null,
            target_name_id  text not null,
            entity_kind     text not null,
            sort_score      smallint not null,
            set_score       smallint not null,
            created_at      timestamptz not null default now(),
            primary key (subject_name_id, target_name_id)
        )
        """
    )
    conn.execute("truncate match_candidate")
    for kind in KINDS:
        subjects = load_names(conn, "subject", kind)
        targets = load_names(conn, "target", kind)
        pairs = candidate_pairs(subjects, targets)
        with (
            conn.cursor() as cur,
            cur.copy(
                "COPY match_candidate (subject_name_id, target_name_id, entity_kind, "
                "sort_score, set_score) FROM STDIN"
            ) as copy,
        ):
            for p in pairs:
                copy.write_row(
                    [p.subject_name_id, p.target_name_id, kind, p.sort_score, p.set_score]
                )
        print(f"{kind}: {len(subjects)} x {len(targets)} names -> {len(pairs)} candidates")
    conn.commit()


if __name__ == "__main__":
    run()
