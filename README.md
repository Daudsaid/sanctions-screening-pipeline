# Sanctions screening pipeline

Screens UK companies and their officers from Companies House against the US
OFAC sanctions list (SDN), and gives every potential match a 0-100 score
with readable reasons.

It is a portfolio project, built on a slice of the register (about 5,400
active fund management companies, SIC 66300, and their 10,100 current
officers), not a production screening system. The design decisions, and the
data problems behind them, are written up in
[docs/decisions.md](docs/decisions.md).

## Why screening is hard

Name matching sounds simple and isn't:

- **Names are written differently.** OFAC writes "Forenames SURNAME",
  Companies House "SURNAME, Forenames". Middle names come and go, and
  people misspell names.
- **Transliteration.** One Arabic or Russian name has several legitimate
  Latin spellings: MOHAMMED, MUHAMMAD, MOHAMED; SERGEY, SERGEI. About 18%
  of OFAC aliases aren't in Latin script at all.
- **Common words.** Most company names share words like ASSET, MANAGEMENT,
  CAPITAL or GROUP with some sanctioned entity, and many people share first
  names. A match on MOHAMMED or MANAGEMENT means little; a match on a rare
  word means a lot.
- **Legal forms.** ROMASHKA OOO, ROMASHKA LIMITED and AKTSIONERNOE
  OBSHCHESTVO ROMASHKA are the same name once the legal form is removed.
- **Few true matches.** Almost every candidate is a false positive, so you
  can't measure how many real matches are missed by looking at the data
  alone.

## Architecture

ELT: raw data is landed unchanged, and all cleaning happens in the database.

```text
OpenSanctions (us_ofac_sdn) ─┐
Companies House bulk file ───┼─> ingest/ ─> raw tables (Postgres, JSONB)
Companies House officers API ┘                       │
                                                     v
                          dbt staging (typed, filtered, one row per entity)
                                                     │
                          dbt intermediate (int_name_norm: normalised names,
                          legal forms stripped, nationality mapped to ISO)
                                                     │
                          matching/block.py  ─> match_candidate
                          (every name vs every name, rapidfuzz)
                                                     │
                          matching/score.py  ─> match_score
                          (rarity-weighted name score + birth date
                           + nationality, with reasons)
                                                     │
                          eval/evaluate.py   ─> docs/evaluation.md
                          (planted matches, recall vs alert volume)
```

- **Ingest** ([ingest/](ingest/)) downloads and caches source files under
  `data/raw/`, and loads each record as JSON with a content hash, so reruns
  only add records that actually changed.
- **dbt** ([dbt/sanctions_screening_dbt/](dbt/sanctions_screening_dbt/))
  turns raw JSON into typed staging views and builds `int_name_norm`, where
  subjects and targets are normalised by the same macro. Data and unit tests
  cover the parsing rules.
- **Candidates** ([matching/block.py](matching/block.py)) compare every
  subject name with every target name of the same kind (about 330M pairs,
  two minutes on a laptop). No blocking, so this step can't miss a pair.
- **Scoring** ([matching/score.py](matching/score.py)) matches words one to
  one, weighted by rarity, then adds or subtracts for birth year and month
  and for nationality. Every score comes with its reasons, for example
  `name 96: [officer] / ALI MOHAMMED; -5 nationality differs (gb vs pk, sa)`.

## Data quality

The data quality checks from profiling run as dbt tests on every
`dbt build`: built-in tests, [dbt-expectations](https://github.com/metaplane/dbt-expectations)
for regex, range and row-count checks, and singular SQL tests for checks
across models. A check is an error if a failure would make screening wrong:
fewer than 15,000 sanctions targets (an empty or truncated export), a
malformed birth date or company number, a date in the future, a name that
no longer normalises cleanly, or a sanctions target left with no name. An
error stops the build before matching runs. Known source quirks, such as
2 officers who resigned before they were appointed or 645 people split
across several officer IDs, are warnings, with the expected count in each
test's description. The full list is in
[docs/decisions.md](docs/decisions.md#data-quality-checks-dbt-tests--dbt-expectations).

## Evaluation

True matches are too rare in this data to measure recall, so the evaluation
plants 400 synthetic subjects built from real OFAC names, each with one
realistic change (typo, word order, middle name, transliteration, added UK
legal suffix or GROUP). Half of the person plants have a conflicting birth
date and should not alert. Real Companies House subjects are counted as
negatives. Full method and tables: [docs/evaluation.md](docs/evaluation.md).

At the chosen threshold of 70:

| Measure | Result |
| --- | --- |
| Recall on 300 true plants | 97% |
| Persons (with matching birth date / name only) | 100% / 96% |
| Organisations | 96% |
| Organisations with a typo | 84% |
| Alerts on real subjects (about 15,500) | 33 (5 person, 28 organisation) |
| Alerts on birth-date-conflict plants | 0 of 100 |

These are measured on synthetic, single-change plants, so they are an upper
bound on real-world performance, not an estimate of it. The weak spots
(typos in short words, a one-word company name with GROUP added) are
explained in the evaluation doc and have not been tuned away.

## Running it

Requirements: Docker, [uv](https://docs.astral.sh/uv/), make, and a free
[Companies House API key](https://developer.company-information.service.gov.uk/)
for the officers step.

```sh
cp .env.example .env               # add COMPANIES_HOUSE_API_KEY
uv sync
make up                            # Postgres 16; creates the raw tables on first start
make schema                        # (re)apply schema/001_raw.sql, safe to rerun
```

Load the sources. The Companies House bulk file ("BasicCompanyDataAsOneFile",
from the [free data product page](https://download.companieshouse.gov.uk/en_output.html))
has to be downloaded and unzipped into `data/raw/` by hand.

```sh
uv run --env-file .env python -m ingest.opensanctions
uv run --env-file .env python -m ingest.companies_house_bulk --sic 66300
uv run --env-file .env python -m ingest.companies_house_officers   # about an hour, rate-limited, resumable
```

Transform, match and evaluate:

```sh
make dbt-build      # dbt deps, then seeds, models and data quality tests
make candidates     # match_candidate
make score          # match_score
make eval           # rewrites the tables in docs/evaluation.md
```

Development checks: `make lint`, `make test`, `make dbt-unit`, or all three
with `make check`. CI runs lint, pytest, and `dbt build` against an empty
Postgres, with the row-count checks switched off
(`--vars '{min_rows_check: false}'`).

## Known gaps

- **UK Sanctions List not yet included.** OFSI's Consolidated List closed in
  January 2026, and the FCDO's UK Sanctions List (OpenSanctions
  `gb_fcdo_sanctions`) is now the UK source. A pipeline screening UK
  companies should screen against it. It is the next dataset to add, with
  deduplication of targets listed by both the UK and the US.
- **Current officers only.** Resigned officers stay in staging but don't
  alert, so an officer who resigned after being designated is missed.
- **No incremental rescreening.** Every run rescreens everything. There is
  no "what changed since the last run" step for new designations or new
  appointments.
- **No LLPs.** The slice is selected by SIC code, and LLPs don't file one,
  so fund management LLPs are missing.
- **No blocking.** Comparing every pair works at this size but not for the
  whole register (about 5M companies). See docs/decisions.md for the plan.
- **Hand-set weights.** Scoring weights were set by hand and checked against
  the evaluation, not learned. Duplicate Companies House records for the same
  person are not merged, so one person can alert twice.

## Contact

Daud Abdi

- GitHub: [github.com/Daudsaid](https://github.com/Daudsaid)
- LinkedIn: [linkedin.com/in/daudabdi0506](https://www.linkedin.com/in/daudabdi0506)
- Website: [daudabdi.com](https://daudabdi.com)
