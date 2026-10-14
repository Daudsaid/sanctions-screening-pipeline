# Sanctions Screening Pipeline

[![CI](https://github.com/Daudsaid/sanctions-screening-pipeline/actions/workflows/ci.yml/badge.svg)](https://github.com/Daudsaid/sanctions-screening-pipeline/actions/workflows/ci.yml)

An end-to-end pipeline that screens UK companies and their officers from
Companies House against the US OFAC sanctions list. Every potential match
gets a 0-100 score with the reasons behind it, and the alert threshold is
chosen from a measured evaluation, not by guesswork.

Built as a portfolio project on a defined slice of the register: 5,406
active fund-management companies (SIC 66300), their 9,856 current person
officers and 275 corporate officers, screened against 20,346 OFAC targets.
It is not a production screening system, and the gaps that would need
closing first are listed [below](#known-limitations-and-next-steps).

## At a glance

| Area | Detail |
| --- | --- |
| **Stack** | Python 3.12, PostgreSQL 16, dbt 1.12 + dbt-expectations, rapidfuzz, uv, Docker, GitHub Actions |
| **Pattern** | ELT: raw JSON landed unchanged, all cleaning in dbt, matching in Python |
| **Recall** | 97% of 300 planted true matches at the chosen threshold |
| **Alert volume** | 26 alerts to review across about 15,500 real subjects |
| **False alerts from birth-date conflicts** | 0 of 100 |
| **Quality gates** | 72 dbt data tests, 3 dbt unit tests, 112 pytest tests, CI on every push |

Every design choice, including the ones that turned out wrong, is written
up in [docs/decisions.md](docs/decisions.md). The evaluation method and full
results are in [docs/evaluation.md](docs/evaluation.md).

## Why sanctions screening is hard

Matching names sounds simple. In practice:

- **The same name is written many ways.** OFAC writes "Forenames SURNAME",
  Companies House "SURNAME, Forenames". Middle names come and go, and typos
  are common.
- **Transliteration.** One Arabic or Russian name has several legitimate
  Latin spellings: MOHAMMED, MUHAMMAD, MOHAMED; SERGEY, SERGEI. About 18% of
  OFAC aliases are not in Latin script at all.
- **Common words carry little signal.** Most fund managers share words like
  CAPITAL, MANAGEMENT or GROUP with some sanctioned entity, and many people
  share a first name. A match on a rare word means far more than a match on
  MOHAMMED or MANAGEMENT.
- **Legal forms hide identical names.** ROMASHKA OOO, ROMASHKA LIMITED and
  AKTSIONERNOE OBSHCHESTVO ROMASHKA are the same name once the legal form is
  removed.
- **True matches are rare.** Almost every candidate is a false positive, so
  recall cannot be measured from the real data alone.

## Architecture

```text
OpenSanctions (us_ofac_sdn) ─┐
Companies House bulk file ───┼─> ingest/ ─> raw tables (Postgres, JSONB, content-hashed)
Companies House officers API ┘                       │
                                                     v
                          dbt staging        typed, filtered, one row per entity
                                                     │   + data quality tests
                          dbt intermediate   int_name_norm: one normalisation for
                                             both sides, legal forms stripped,
                                             nationality mapped to ISO codes
                                                     │
                          matching/block.py  ─> match_candidate
                                             every name vs every name (rapidfuzz)
                                                     │
                          matching/score.py  ─> match_score
                                             rarity-weighted name score
                                             + birth date + nationality, with reasons
                                                     │
                          matching/alert.py  ─> match_alert
                                             one alert per subject at score >= 70
                                                     │
                          eval/evaluate.py   ─> docs/evaluation.md
                                             planted matches: recall vs alert volume
```

| Stage | What it does |
| --- | --- |
| [Ingest](ingest/) | Downloads and caches the source files, then loads each record unchanged as JSON with a content hash. Volatile fields such as `last_seen` are excluded from the hash, so a rerun against an unchanged export loads 0 rows. |
| [dbt](dbt/sanctions_screening_dbt/) | Turns raw JSON into typed staging views, then builds `int_name_norm`, where subjects and targets are normalised by the same macro. Parsing repairs live here: "SURNAME, Forenames, Title" splitting, leading titles stripped as whole words only, companies filed under a person role reclassified, and non-Latin names dropped without losing any target. |
| [Candidates](matching/block.py) | Compares every subject name with every target name of the same kind, about 330M pairs in two minutes on a laptop. There is no blocking, so this step cannot miss a pair. |
| [Scoring](matching/score.py) | Matches words one to one, weighted by rarity (IDF), then adds or subtracts points for birth date (compared to the month) and nationality. Every score carries its reasons. |
| [Alerts](matching/alert.py) | Groups scored pairs into one alert per subject, listing every target it hits. Folds together officer records for the same person at the same company. |
| [Evaluation](eval/evaluate.py) | Plants synthetic matches, runs them through the production matching code, and reports recall and alert volume at each threshold. |

## How a match is scored

A subject-target pair is scored on its best pair of names:

- **Name (0-100).** Words are matched one to one, allowing spelling variants
  (MOHAMED / MOHAMMED). Each word is weighted by how rare it is, so sharing
  ROMASHKA counts far more than sharing MANAGEMENT. Words of four letters or
  fewer must match exactly, because one letter changes too much of a short
  word (IFC is not IFDC).
- **Birth date (persons).** +15 for the same year and month, +10 for the
  same year when the target gives only a year, +5 within eleven months, and
  -40 when no target date is within a year. A clear
  conflict is strong evidence of a different person. Companies House gives
  only year and month, so that is the finest comparison possible.
- **Nationality (persons).** +5 or -5. Kept small, because OFAC's
  "countries" mixes nationality, citizenship and residence.

Each alert explains itself. For example:

```text
96.4  [officer]  vs  Ali Muhammad Abu Turab (alias ALI MOHAMMED)
      name 96: [officer] / ALI MOHAMMED;
      +5 birth month [birth month] within 1 month of 1968-01;
      -5 nationality differs (gb vs pk, sa)
```

## Evaluation

Natural true matches are too rare in this slice to measure recall, so the
evaluation plants them:

- **Plants.** A seeded sample of 200 OFAC persons and 200 organisations
  each get one fake subject with one realistic change: a typo, swapped word
  order, a middle name dropped or added, a transliteration variant, or an
  added UK legal suffix or "UK" / "GROUP".
- **Negatives.** Half the person plants get a birth date at least two years
  from the target's. Every real Companies House subject is also treated as a
  negative.
- **Same code as production.** Plants go through the production candidate
  generation and scoring, with the production word weights. Nothing was
  tuned to the plants.

Results at the chosen threshold of 70:

| Measure | Result |
| --- | --- |
| Recall, all 300 true plants | 97% |
| Recall, persons (with matching birth date / on name alone) | 100% / 96% |
| Recall, organisations | 96% |
| Recall, organisation names with a typo (weakest change type) | 84% |
| Pairs scoring 70+ on real subjects | 33 (5 person, 28 organisation) |
| Alerts to review after grouping per subject | 26 |
| Birth-date-conflict plants alerting | 0 of 100 |

**Why 70.** Raising the threshold to 80 would roughly halve the alerting
pairs (16), but it loses six true plants and drops name-only person recall
from 96% to 86%. A missed designated party is a regulatory breach, while an
extra alert costs minutes of analyst time. Going below 65 lets birth-date
conflicts through for almost no gain in recall.

**What the evaluation shows doesn't work yet.**

- **Organisation typos in short words.** The word-level similarity counts a
  substituted letter as two edits, so words under seven letters cannot
  absorb a typo.
- **A one-word company name with GROUP added** (TRIALKOM / TRIALKOM GROUP)
  never becomes a candidate.

Both are explained in [docs/evaluation.md](docs/evaluation.md) and left
untuned on purpose. The figures come from synthetic, single-change plants,
so read them as an upper bound on real-world performance, not an estimate
of it.

## Data quality

Every check from the initial data profiling is now a permanent test that
runs on each `dbt build`. These use built-in dbt tests,
[dbt-expectations](https://github.com/metaplane/dbt-expectations) for
regex, range and row-count checks, and singular SQL tests for checks that
span models.

- **Errors (48 tests)** block the build before matching runs. They cover
  anything that would make screening wrong:
  - fewer than 15,000 sanctions targets, which guards against an empty or
    truncated upstream export
  - a malformed birth date or company number
  - a date in the future
  - a name that no longer normalises cleanly
  - a sanctions target left with no screenable name
- **Warnings (24 tests)** track known source quirks that staging already
  handles, such as officers who resigned before they were appointed, or one
  person filed under several officer IDs. Each records its expected count,
  so a change shows up in every build.

The full list of warnings and their counts is in
[docs/decisions.md](docs/decisions.md#data-quality-checks-dbt-tests--dbt-expectations).

## Getting started

**Requirements:** Docker, [uv](https://docs.astral.sh/uv/), make, and a free
[Companies House API key](https://developer.company-information.service.gov.uk/)
for the officers step.

```sh
git clone https://github.com/Daudsaid/sanctions-screening-pipeline.git
cd sanctions-screening-pipeline
cp .env.example .env            # add COMPANIES_HOUSE_API_KEY
uv sync
make up                         # Postgres 16; creates the raw tables on first start
```

**Load the sources.** Download the Companies House bulk file
("BasicCompanyDataAsOneFile") from the
[free data product page](https://download.companieshouse.gov.uk/en_output.html)
and unzip it into `data/raw/`, then run:

```sh
uv run --env-file .env python -m ingest.opensanctions
uv run --env-file .env python -m ingest.companies_house_bulk --sic 66300
uv run --env-file .env python -m ingest.companies_house_officers   # ~1 hour, rate-limited, resumable
```

**Transform, match and evaluate:**

```sh
make dbt-build      # dbt deps, seeds, models and data quality tests
make candidates     # -> match_candidate
make score          # -> match_score
make alerts         # -> match_alert, one row per subject to review
make eval           # regenerates the results tables in docs/evaluation.md
```

## Testing and CI

```sh
make check          # workflow-file check, ruff, pytest, dbt unit tests
```

GitHub Actions runs on every push and pull request:

- validates the workflow files
- lints with ruff
- runs pytest
- builds the full dbt project against a fresh Postgres 16 service

The CI database is empty, so the row-count checks are switched off there
with a dbt variable (`min_rows_check`).

## Project layout

```text
ingest/                     extract and load: OpenSanctions, Companies House bulk file and API
schema/001_raw.sql          raw landing tables
dbt/sanctions_screening_dbt staging and intermediate models, seeds, data quality tests
matching/                   candidate generation, scoring, alert grouping
eval/                       planted-match evaluation
tests/                      pytest suite (no database needed)
scripts/                    workflow-file check used by make lint and CI
docs/decisions.md           design decisions and data findings
docs/evaluation.md          evaluation method, results and threshold choice
```

## Known limitations and next steps

- **UK Sanctions List not yet included.** OFSI's Consolidated List closed in
  January 2026, and the FCDO's UK Sanctions List (OpenSanctions
  `gb_fcdo_sanctions`) is now the UK source. A pipeline screening UK
  companies should screen against it. It is the next dataset to add, with
  deduplication of targets designated by both the UK and the US.
- **Current officers only.** Resigned officers stay in staging but don't
  alert, so an officer who resigned after being designated is missed.
- **No incremental rescreening.** Every run rescreens everything. There is
  no step that screens only new designations or new appointments.
- **No LLPs.** The slice is selected by SIC code, and LLPs don't file one,
  so fund-management LLPs are missing.
- **No blocking.** Comparing every pair works at this size but not for the
  whole register (about 5M companies). [docs/decisions.md](docs/decisions.md)
  sets out the blocking plan and how to measure the recall it costs.
- **Hand-set weights.** Scoring weights were set by hand and checked against
  the evaluation, not learned.
- **Duplicate people.** Companies House sometimes holds one person under
  several officer IDs. They are merged only within a company, so one person
  can still raise more than one alert.
- **Typo tolerance in short words.** A word-level edit distance that counts
  a substitution as one edit would likely lift organisation typo recall. Any
  such change should be measured against both recall and the alert volume on
  real subjects.

## Contact

Daud Abdi

- GitHub: [github.com/Daudsaid](https://github.com/Daudsaid)
- LinkedIn: [linkedin.com/in/daudabdi0506](https://www.linkedin.com/in/daudabdi0506)
- Website: [daudabdi.com](https://daudabdi.com)
