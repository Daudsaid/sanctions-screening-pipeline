# Sanctions Screening Pipeline

[![CI](https://github.com/Daudsaid/sanctions-screening-pipeline/actions/workflows/ci.yml/badge.svg)](https://github.com/Daudsaid/sanctions-screening-pipeline/actions/workflows/ci.yml)

An end-to-end pipeline that screens UK companies and their officers from
Companies House against the UK Sanctions List and the US OFAC list. Every
potential match gets a 0-100 score with the reasons behind it, and the alert
threshold is chosen from a measured evaluation, not by guesswork.

Built as a portfolio project on a defined slice of the register: 5,406
active fund-management companies (SIC 66300) and their officers (10,700
people and 290 companies, current or resigned within the last 12 months),
screened against 23,271 sanctioned parties (UK and US lists merged, 3,534
of them on both).
It is not a production screening system, and the gaps that would need
closing first are listed [below](#known-limitations-and-next-steps).

## At a glance

| Area | Detail |
| --- | --- |
| **Stack** | Python 3.12, PostgreSQL 16, dbt 1.12 + dbt-expectations, rapidfuzz, uv, Docker, GitHub Actions |
| **Pattern** | ELT: raw JSON landed unchanged, all cleaning in dbt, matching in Python |
| **Sanctions lists** | UK Sanctions List (FCDO) and US OFAC SDN, via OpenSanctions, merged per party |
| **Recall** | 93-96% of about 300 planted true matches at the chosen threshold, across five samples |
| **Alert volume** | 30 alerts to review across about 16,400 real subjects |
| **False alerts from birth-date conflicts** | 0 on every sample |
| **Quality gates** | 83 dbt data tests (51 with dbt-expectations), 5 dbt unit tests, 114 pytest tests, CI on every push |

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
OpenSanctions (UK FCDO, US OFAC) ─┐
Companies House bulk file ────────┼─> ingest/ ─> raw tables (Postgres, JSONB, content-hashed)
Companies House officers API ─────┘                  │
                                                     v
                          dbt staging        typed, filtered, one row per entity;
                                             sanctions lists merged, delisted dropped
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
| [Ingest](ingest/) | Downloads and caches the source files, then loads each record unchanged as JSON with a content hash. Volatile fields such as `last_seen` are excluded from the hash, so a rerun against an unchanged export loads 0 rows. Each sanctions load also records its full id list, so a target that drops off a list stops being screened. |
| [dbt](dbt/sanctions_screening_dbt/) | Turns raw JSON into typed staging views, then builds `int_name_norm`, where subjects and targets are normalised by the same macro. Merges a party listed by both the UK and the US into one target, keeping every name and birth date from both lists. Parsing repairs live here: "SURNAME, Forenames, Title" splitting, leading titles stripped as whole words only, companies filed under a person role reclassified, and non-Latin names dropped without losing any target. |
| [Candidates](matching/block.py) | Compares every subject name with every target name of the same kind, about 410M pairs in two to three minutes on a laptop. There is no blocking, so this step cannot miss a pair. |
| [Scoring](matching/score.py) | Matches words one to one, weighted by rarity (IDF), then adds or subtracts points for birth date (compared to the month) and nationality. Every score carries its reasons. |
| [Alerts](matching/alert.py) | Groups scored pairs into one alert per subject, listing every target it hits. Folds together officer records for the same person at the same company, and flags alerts on officers who have resigned. |
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

Each alert explains itself. For example, an alert from the real run, with
the Companies House officer anonymised (the sanctioned party's alias is a
public designation):

```text
96.4  [officer]  vs  Ali Muhammad Abu Turab (alias ALI MOHAMMED)
      name 96: [officer's name, same words in another order] / ALI MOHAMMED;
      +5 birth month within 1 month of 1968-01;
      -5 nationality differs (gb vs pk, sa)
```

The docs refer to real Companies House officers and companies by
description, never by name: appearing in a screening run is not evidence
of anything, and none of the alerts here is a confirmed match.

## Evaluation

Natural true matches are too rare in this slice to measure recall, so the
evaluation plants them:

- **Plants.** A seeded sample of 200 sanctioned persons and 200
  organisations, from both lists, each get one fake subject with one
  realistic change: a typo, swapped word
  order, a middle name dropped or added, a transliteration variant, or an
  added UK legal suffix or "UK" / "GROUP".
- **Negatives.** About half the person plants get a birth date at least two years
  from the target's. Every real Companies House subject is also treated as a
  negative.
- **Same code as production.** Plants go through the production candidate
  generation and scoring, with the production word weights. Nothing was
  tuned to the plants.
- **Several samples.** Recall is reported as the range over five seeds,
  because a single sample of 200 per kind moves by a couple of points, and
  a single change type by ten or more.

Results at the chosen threshold of 70:

| Measure | Range over five samples |
| --- | --- |
| Recall, all true plants | 93-96% |
| Recall, persons with a matching birth date | 96-99% |
| Recall, persons on name alone | 87-98% |
| Recall, organisations | 91-94% |
| Recall, organisation names with a typo (weakest change type) | 72-92% |
| Birth-date-conflict plants alerting | 0 on every sample |
| Pairs scoring 70+ on real subjects (not sampled) | 38 (8 person, 30 organisation) |
| Alerts to review after grouping per subject | 30 |

**Why 70.** Raising the threshold to 80 would roughly halve the work
(20 pairs, 18 alerts), but costs 1-3 points of recall and drops name-only
person recall to 74-88%. A missed designated party is a regulatory breach,
while an extra alert costs minutes of analyst time. Going below 65 lets
birth-date conflicts through for about a point of recall.

**What the evaluation shows doesn't work yet.**

- **Organisation typos in short words.** The word-level similarity counts a
  substituted letter as two edits, so words under seven letters cannot
  absorb a typo.
- **A one-word company name with GROUP added** (PLANAR / PLANAR GROUP)
  never becomes a candidate.

Both are explained in [docs/evaluation.md](docs/evaluation.md) and left
untuned on purpose. The figures come from synthetic, single-change plants,
so read them as an upper bound on real-world performance, not an estimate
of it.

## Data quality

Every check from the initial data profiling, and every inconsistency found
since, is a permanent test that runs on each `dbt build`. They are written
with [dbt-expectations](https://github.com/metaplane/dbt-expectations)
wherever it can express them (51 of 83), as declarative rules in YAML:

- **Formats and ranges:** company numbers, birth dates (including each
  element of an array), normalised names, no dates in the future.
- **Consistency within groups:** one officer ID with several names or birth
  dates, one person filed under several officer IDs, two sanctions lists
  disagreeing on whether a target is a person or an organisation.
- **Coverage between tables:** every company has officers, and every
  sanctioned party keeps at least one screenable name.
- **Rules on the raw JSON**, before staging: an officer's link names the
  company it was fetched for, previous company names have no gaps.

The rest are dbt's built-in tests, plus two SQL tests that need a join
across models or the sanctions load manifest.

- **Errors (53 tests)** block the build before matching runs. They cover
  anything that would make screening wrong:
  - a sanctions list missing or below its floor (15,000 rows for OFAC,
    4,500 for the UK list), which guards against an empty or truncated
    upstream export
  - a malformed birth date or company number
  - a date in the future
  - a name that no longer normalises cleanly
  - a sanctions target left with no screenable name
- **Warnings (30 tests)** track known source quirks that staging already
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
uv run --env-file .env python -m ingest.opensanctions          # UK and US lists (or --dataset NAME)
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

- **Two lists only.** The UK and US lists cover most designations relevant
  to UK firms, but not the EU or UN lists. OpenSanctions publishes both in
  the same format, so adding one is a dataset name in ingest and dbt.
- **Resigned officers for 12 months only.** Officers who resigned within
  the last 12 months are screened (and flagged in alerts); earlier
  resignations are not. The window is a dbt variable.
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
