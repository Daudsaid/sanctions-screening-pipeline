
## Sanctions sources: UK Sanctions List and US OFAC

The first choice was gb_hmt_sanctions (the OFSI Consolidated List). On
2026-09-19 OpenSanctions' bulk export for it returned a header-only CSV
(175 bytes) at the origin, confirmed via x-goog-stored-content-length on the
GCS-backed CDN response; a cache-busted request returned the same.

That was not an upstream bug. OFSI closed the Consolidated List on
28 January 2026, and the UK Sanctions List, published by the FCDO, is now the
only source of UK designations. The OFSI list is frozen, so pulling GOV.UK's
OFSI CSV directly is not an alternative either.

v1 used us_ofac_sdn alone: same OpenSanctions schema, 20,346 targets. The
pipeline now also screens OpenSanctions' gb_fcdo_sanctions dataset (the UK
Sanctions List), with targets listed on both merged; see "UK Sanctions List
and delisted targets" below.

## Idempotent raw loads: hashing excludes volatile fields

The first version hashed the whole source row to detect changes. A second
run doubled the table (20,346 to 40,692 rows) because OpenSanctions
re-stamps last_seen on every export, so every record looked new even though
nothing about the sanctioned party had changed. last_change was identical
across the two copies, which confirmed the diagnosis.

The hash now excludes last_seen. The column is still stored in the raw JSON;
it just doesn't decide whether a record counts as changed. A record only
lands as a new version when its content changes, which is what the audit
trail needs. Verified: a second run against an unchanged export loads 0 rows.

## Project lives outside iCloud-synced Desktop

Commands repeatedly stalled for minutes at near-zero CPU: the bulk dry run,
the officers fetch, dbt debug. A traceback showed Python blocked reading a
package file during import. ~/Desktop was synced by iCloud ("Desktop &
Documents"), so every read of the .venv's thousands of files could wait on
iCloud. Moving the project to ~/dev fixed it: dbt debug went from over
7 minutes to 4.5 seconds.

## Staging decisions from profiling (explore/01_raw_profile.ipynb)

- Sanctions targets: 7,509 persons, 9,893 organisations (Organization,
  Company, LegalEntity), 2,944 out of scope (Vessel, CryptoWallet, Airplane,
  Security). Out-of-scope targets stay in staging but are excluded from
  matching. Persons only match persons; organisations match companies and
  corporate officers.
- OFAC person birth dates: 81.7% full date, 9.1% multiple, 7.9% year only,
  1.3% missing. Companies House gives year and month only, so dates are
  compared at YYYY-MM, or at YYYY when the target has a year only. A year
  mismatch counts as evidence against a match. Multiple dates are scored on
  the best-agreeing one.
- Aliases: 5,494 of 30,547 (18%) contain no Latin letters, but every
  screenable target has at least one Latin name. Non-Latin script costs name
  variants, never whole targets.
- Officers: 26,186 person appointments, all in "SURNAME, Forenames" form
  (enforced by a test). 1,912 corporate officer appointments are matched on
  the organisation side, including 6 companies filed under a person role
  (see "Officer and company name repairs" below).
  3,103 secretaries have no date of birth and can only match on name.
- 21,613 distinct officer IDs across 28,098 appointments (20,772 of them
  person IDs), so screening is per officer ID. This is an upper bound on
  people: Companies House does not always merge one person's records. After
  the current-officers filter below, 9,856 person and 275 corporate officer
  IDs remain as subjects.
- 56% of appointments have ended. v1 alerts on current officers only; resigned
  officers stay in staging. Known gap: an officer who resigned after
  designation. Planned as a v2 rule.
- Company suffixes stripped: LIMITED, LTD, LTD., PLC, CIC, COMMUNITY INTEREST
  COMPANY. Private unlimited companies and exempt guarantee companies have no
  suffix by law. Words like COMPANY (as in "& COMPANY"), INVESTMENTS and
  HOLDINGS are part of the name and are not stripped. The abbreviation CO is
  stripped, so "SMITH & CO LTD" cores to SMITH and "SMITH & COMPANY LTD" to
  SMITH COMPANY. Accepted for v1; scoring has to tolerate the extra token.
- The slice contains no LLPs, which appear not to file SIC codes, so a
  SIC-based slice cannot include them. A coverage gap for fund management.
- Incorporation dates are 100% dd/mm/yyyy and are parsed with no fallback.

## Data quality findings (explore/02_data_quality_results.txt)

Clean: sanctions names, birth dates (8,337, all well-formed and plausible),
country codes (all ISO 2-letter), timestamp ordering; company slice integrity
(all Active, all 66300); officer joins (no orphans, no duplicate appointments).

Minor, handled by normalisation: 5 company names contain double spaces
(collapsed), 4 companies have no postcode (not used for matching). 2 officer
names contain a digit; to check whether they are corporate officers filed
as persons.

Handled:
- 4 aliases repeat the primary name and 6 repeat within a target. Names are
  deduplicated per target in staging.
- appointed_on is null for exactly the 824 pre-1992 appointments. Companies
  House does not record those dates, so the column is nullable by design.
- 2 officers resigned before their appointment date, and 1 officer ID has two
  birth dates. Source errors, kept and noted.
- Several sanctioned parties share a name (two separate persons named Alireza
  Derakhshan). Alerts reference target_id, never a name alone.
- No OC (LLP) company numbers in the slice, consistent with the LLP gap.
- Registered-office country mixes UNITED KINGDOM, constituent countries and
  547 blanks. Not used for matching.
- 38 officer IDs carry more than one name. Every name is matched, like aliases.
- 645 name+DOB combinations span 1,437 officer IDs, so Companies House holds
  duplicate records for some people. v1 keys on officer_id and accepts that a
  person may alert twice: merging on name+DOB is entity resolution in its own
  right, and a wrong merge is worse than a duplicate alert.

Officer name format is "SURNAME, Forenames, Title". The third field holds
courtesy titles and, in places, job titles ("Director", "Ceo"). Everything
after the second comma goes to name_title and is excluded from matching.
Bracketed text (nicknames, former names) goes to name_note. A leading title in
the forenames (LORD, SIR, DR, DAME, LADY, REV, PROF, MR, MRS, MS, MISS) is
stripped as a whole word only. On the real data that is 5 cases, all LORD,
with none left after stripping. (The data-quality check reported 1,005
"title in forenames" because it matched substrings, such as DR inside ANDREW.
analyses/leading_titles_in_forenames.sql has the whole-word count, and a
warning test flags any title left after stripping.)

Nationality is free text with 304 spellings (British/English/United Kingdom,
American/Usa/United States, combined "British,American"). Mapped to ISO codes
via a seed file. Unmapped and missing values are neutral in scoring.

## Name normalisation (int_name_norm)

One macro (normalise_name) is applied identically to subjects and targets:
uppercase, accents removed, dots and apostrophes dropped (LTD. -> LTD,
S.A. -> SA), other punctuation to spaces, whitespace collapsed.

Organisation names also get name_core: legal forms stripped from both ends
using the legal_forms seed, built from the forms actually present on both
sides (Russian OOO/JSC/AO before or after the name, transliterated forms
such as AKTSIONERNOE OBSHCHESTVO, GMBH & CO KG, SA DE CV, SIRKETI, DMCC).
Generic words (COMPANY, GROUP, BANK) are kept and left to frequency
weighting. If stripping would leave nothing, the full name is kept.

Of 47,641 in-scope sanctions names, 5,413 are non-Latin and drop out (no
target loses every name), and 2,201 merge into another spelling of the same
name, leaving 40,027. Subjects: 9,856 person officers, 275 corporate
officers, 5,406 companies (6,518 names including previous names).

Mixed-script names are dropped: 320 OFAC names are mostly Cyrillic with a
few stray Latin letters (a Belarusian i, a Latin C or O, or OOO before a
Cyrillic name), which normalised to junk such as C (79 targets), OOO (48)
and I (19). A name is kept only if at least half of its letters are Latin.
No target loses every name. int_name_norm then holds 56,382 names.

Known limitations: "& Co." is stripped as a legal form even where it is
part of a trading name. Very short cores (e.g. NKK, BS) give unreliable
trigram similarity, so scoring requires near-exact agreement for them.

## Candidate generation (matching/block.py)

No blocking in v1. Every subject name is compared with every target name of
the same kind with rapidfuzz: 9,866 x 25,127 person names and 6,796 x 24,291
organisation names, about 410M pairs, in roughly two to three minutes on a
laptop (330M before the UK list was added).
Blocking exists to make comparison affordable; here comparison is already
affordable, and comparing everything means candidate generation cannot miss
a pair. It becomes necessary if the subject side grows to the full register
(about 5M companies and many more officers): then block on rare words and a
phonetic key per word, and measure the recall lost against this exhaustive
version.

A pair is a candidate if token_sort_ratio >= 80 (same words in any order,
spelling variation allowed), or token_set_ratio >= 90 when both names have at
least two distinct words (one name contains the other). Without that guard
token_set_ratio scores single-word targets such as MARTIN or IM at 100
against any name containing them, and ANTHONY ANTHONY against any Anthony.

Result: 687 person and 3,669 organisation candidate name pairs (530 and
3,441 with OFAC alone). Candidates
are generous on purpose. Most organisation candidates share only generic
words (ASSET MANAGEMENT, INVESTMENTS), and only a handful of person
candidates agree on birth year, none closely. That is expected for a slice of
UK fund managers, and it means the evaluation set needs seeded true matches:
natural true positives will be too rare to measure recall.

## Scoring (matching/score.py)

Each subject-target pair gets one 0-100 score from its best pair of names,
with the reasons stored next to it, so every alert can be explained.

- Name: words matched one to one, spelling variants allowed (fuzz.ratio >=
  85), each word weighted by rarity (IDF over both sides). A shared ROMASHKA
  counts far more than a shared MANAGEMENT or MOHAMMED, so "[company]" against "ATLAS CURRENCY EXCHANGE" scores 78, not 100. Words of
  four letters or fewer must match exactly: without that rule IFC / IFDC,
  PSC / PBSC and TACO / TAFCO scored 86-89, and 21 organisation pairs
  reached 80 instead of 12.
- Date of birth (persons): +15 same year and month, +10 same year when the
  target gives a year only, +5 when 1-11 months apart, -40 when no target
  date is within a year, 0 when either side is missing or the dates are
  further apart but within a year (OFAC dates are sometimes approximate).
  The gap is counted in months: comparing years made 1989-12 and 1990-01
  "different years", worth nothing, while 1989-01 and 1989-12 earned +5.
- Nationality (persons): +5 overlap, -5 both known and no overlap. Kept small
  because OFAC countries mix nationality and residence.

Weights are hand-set. On the real data, 4,041 pairs are scored; 6 person and
14 organisation pairs reach 80 (4 and 12 with OFAC alone). None look like true matches: the top is
exact name collisions ([company], [officer], where one officer ID has a
birth date five months from the target's and the other has none) and
spelling variants ([company] / INPESCA). The alert threshold, and whether the
weights hold up, are for the evaluation set to decide.

## Evaluation (eval/evaluate.py, docs/evaluation.md)

Recall is measured on planted matches: 200 person and 200 organisation
sanctions targets (seeded sample, Latin-script primary names), each given one fake
subject with one change (typo, word order, middle name dropped or added,
transliteration, UK legal suffix, UK / GROUP). Half the person plants have a
conflicting birth year and are negatives. Real Companies House subjects are
treated as negatives. Plants go through the production candidate_pairs and
score_pair with the production word weights.

Alert threshold: 70. With both lists, recall at 70 is 93-96% across five
samples (persons with a matching birth date 96-99%, on name alone 87-98%,
organisations 91-94%), with 38 pairs on real subjects (8 person,
30 organisation), grouped into 30 alerts, and no birth-date-conflict plant
alerting on any sample. At 80 the real pairs fall to 20 (18 alerts) but
recall drops 1-3 points, and name-only person recall to 74-88%. A conflict
caps a perfect name at 60 (65 with a nationality match), so 70 keeps a
margin above that. The first OFAC-only run gave 97%; that figure came from
one sample, and the spread across samples (below, and in
docs/evaluation.md) is the better guide.

Weak spots, left untuned: organisation typos (72-92% at 70 across samples), because fuzz.ratio
counts a substituted letter as two edits, so words under seven letters can't
absorb one, and the misspelt word gets the top rarity weight; and a one-word
target with UK or GROUP added (TRIALKOM / TRIALKOM GROUP), which the
two-word guard keeps out of candidates entirely.

## Data quality checks (dbt tests + dbt-expectations)

The one-off profiling queries (explore/02_data_quality_results.txt, S1-S6,
C1-C4, O1-O7), and every inconsistency found since, are permanent tests that
run on every `dbt build`. They are written with the metaplane/dbt_expectations
package wherever it can express them, in models/*/schema.yml for models and
models/staging/sources.yml for the raw JSON:

- single-column rules: regex formats (company numbers, normalised names, no
  leftover commas or titles), value ranges (birth years, dates not in the
  future), not-null with a condition (nationality tokens mapped)
- row rules with expression_is_true, including rules on raw JSON (an
  appointment's link names its company) and on array columns via a
  subquery (every birth date is YYYY, YYYY-MM or YYYY-MM-DD)
- uniqueness of expressions, such as one name per target ignoring case
  (expect_compound_columns_to_be_unique on upper(name))
- consistency within groups (expect_column_distinct_count_to_be_less_than
  with group_by): one officer ID with several names or birth dates, one
  person under several officer IDs, two lists disagreeing on a target's kind
- coverage between models (expect_column_distinct_count_to_equal_other_table):
  every company has officers, every sanctions target keeps a name
- volume (expect_table_row_count_to_be_between), per sanctions list

83 data tests in all: 51 dbt-expectations, 30 built-in (unique, not_null,
accepted_values, relationships) and 2 SQL files in tests/, kept as SQL
because they need what dbt-expectations does not offer: a row-level join
between two models (officers appointed before incorporation) and the
sanctions load manifest (delisted targets). Plus 5 unit tests on the parsing
and merge rules.

Why dbt tests rather than Great Expectations or Soda: every transformation
already lives in dbt on Postgres, so the checks run in the same command,
the same CI step and against the same models. dbt build also orders tests
with the DAG: an error-severity failure in staging skips everything built
on top of it, so a bad load never reaches int_name_norm or matching. Great
Expectations and Soda would each add a second framework, configuration
format and runtime for checks that are SQL either way. What they offer
beyond dbt (data docs, profiling, anomaly detection over time) isn't needed
at this size. dbt-expectations provides the Great Expectations style checks
as dbt macros, so nothing is lost by staying in dbt.

The rule: severity error (53 tests) if a failure would make screening wrong
(a missing or truncated sanctions list, an unparseable birth date, a name
that no longer normalises the same way on both sides, a target with no
names left, a legal form left in a company's matching name). Severity warn
(30 tests) for known source quirks that staging or scoring already
tolerates. Every test description gives the count at the latest load, so a
change in a warning count is visible.

Volume guards: each sanctions list must have a floor of rows in its latest
export (us_ofac_sdn 15,000, it has 20,394; gb_fcdo_sanctions 4,500, it has
6,411), the guard against an empty upstream export like the OFSI one; a
list missing entirely counts as 0. stg_ch_company and current person
officers must not be empty. CI builds against an empty database, so these
are gated by the dbt var min_rows_check (true by default, false in CI); a
list's guard is also off when var sanctions_datasets leaves it out.

Warnings on the current data (row counts as dbt reports them):

| Test | Rows | Note |
|---|---:|---|
| ch_person_split_across_officer_ids | 645 | name+birth month groups over 1,437 officer IDs |
| warn_sanctions_delisted | 187 | OFAC targets no longer in the latest export; not screened |
| sanctions_listing_names_repeated | 83 | listings naming a target twice in different letter case (74 UK, 9 OFAC); deduplicated |
| ch_officer_name_non_ascii | 72 | accented names; unaccent handles them |
| ch_officer_id_several_names | 38 | every name is matched, like aliases |
| target_name_core_short | 35 | names of 2 characters or fewer |
| ch_company_name_repeated | 17 | 10 previous names equal to the current one, 7 repeated previous names |
| sanctions_shared_primary_names | 9 | in-scope targets sharing a primary name |
| ch_company_name_double_space | 5 | collapsed by normalisation |
| ch_company_postcode_present | 4 | not used for matching |
| ch_company_filed_as_person | 3 | current companies filed under a person role; screened as organisations |
| ch_company_name_trailing_the | 2 | names ending "(THE)"; legal form now stripped |
| ch_officer_name_repeated_comma | 2 | collapsed before splitting |
| ch_resigned_after_appointed | 2 | resigned before appointed; source error |
| ch_person_name_has_digit | 2 | possibly corporate officers filed as persons |
| ch_officer_id_several_birth_dates | 1 | one officer ID, two birth dates |

All error-severity tests pass. The previous-name check (C3) reported 0
names equal to the current name during profiling; the test finds 10, plus
7 repeated previous names, so the profiling query must have compared
something else. They are harmless, since names are deduplicated per entity
in int_name_norm.

## Officer and company name repairs

A second exploration pass, looking for inconsistencies the tests didn't
cover, found three that changed what gets screened:

- Companies filed under a person role. Companies House splits their names
  like a person's ("LIMITED, Propensions"), so they were screened against
  sanctioned persons only and could never match a sanctioned company. A
  person-role name whose surname field ends in LIMITED, LTD, LLP or PLC is
  now an organization named in the right order ("Propensions LIMITED"),
  flagged filed_as_person. 6 appointments, 3 of them current.
- A repeated comma ("SURNAME,, Forenames") pushed the
  forenames into the title field, which matching ignores, so a current
  director was screened on his surname alone. Repeated commas are collapsed
  before the name is split.
- "HOOVER TRUST FUND LIMITED(THE)" normalised to HOOVER TRUST FUND LIMITED
  THE, so LIMITED was never stripped. THE is now stripped from both ends in
  the legal_forms seed. Only these 2 names end in THE, on either side.

Effect: 3 officer IDs move from the person side to the organisation side,
1 organisation candidate is added ([company] / TCH CONSULTANCY, score
38), and alert counts at every threshold are unchanged. Recall at 70 is
still 97%. At 60, DOB-conflict plant alerts went from 21 to 19, because
word weights shift slightly when the subject names change.

Left as they are: sanctioned persons whose aliases are online handles
(@bassterlord, H4mid@Tm3l, jackrock#3337; 12 names contain @ or #) are
screened like any other name, and one company registered without its
Portuguese accents (GESTO DE PARTICIPAES) cannot be repaired on our side.

## Alerts (matching/alert.py)

match_score has one row per subject-target pair, but an analyst reviews a
subject. Reviewing the 33 pairs at 70 showed two kinds of repetition:

- One subject against several targets. [company] scored
  70+ against six sanctioned exchange houses ("Atlas Currency Exchange",
  "Sina Currency Exchange Company"...), because CURRENCY and EXCHANGE are
  rare among UK fund managers and weigh a lot. [company] hit two different
  entities both called Tamyna.
- One person under two officer IDs. [officer] is director and secretary of
  the same company; only the director record has a birth date, so the
  name+DOB duplicate check (645 groups) can't see it.

match_alert holds one row per subject at or above the threshold, listing
every target with its score, best first. Officers with the same matched
name who share a current company are folded into one alert. Officers who
only share a name, at different companies, stay separate (merging those is
entity resolution, and a wrong merge is worse than a duplicate alert).
Scores are untouched.

At 70: 33 pairs become 26 alerts (4 person, 22 organisation). At 80:
16 pairs, 14 alerts. The evaluation still counts pairs, since recall is
measured per subject-target pair.

The same review led to the month-gap birth-date rule above. It raised
[officer] (born [birth month], target 1968-01-05) from 91 to 96 and [officer] ([birth month] against 1975-01-11) from 78 to 83. Recall on the plants is
unchanged (true plants have exact months; conflict plants are years away).

## UK Sanctions List and delisted targets

The pipeline screens two lists: the UK Sanctions List (OpenSanctions
gb_fcdo_sanctions, 6,411 targets) and US OFAC SDN (us_ofac_sdn, 20,394 at
the 2026-10 reload). OpenSanctions gives a party on several lists the same
id, so the lists merge on target_id: 3,534 targets are on both, 2,877 only
on the UK list and 16,860 only on OFAC, 23,271 in all (9,165 persons and
10,695 organisations in scope). Ingest loads each list with
`--dataset`, or both by default, and refuses an empty export.

Staging is split in two. stg_sanctions_listing holds one row per list per
target. stg_sanctions_target merges them: the UK primary name is preferred
(this pipeline screens UK companies), every other name on either list
becomes an alias, and birth dates, countries and programmes are combined.
The lists never disagree on person versus organisation (138 shared targets
differ only between Company and Organization); a warn test watches for it.
The lists do disagree on 2,012 primary names and 485 sets of birth dates.
Combining birth dates favours recall: scoring uses the best-agreeing date,
so a -40 conflict needs every date from both lists to be over a year off.
var sanctions_datasets picks the lists to screen.

Reloading OFAC exposed a bug. Raw snapshots are append-only and staging kept
the latest version of every id ever seen, so 187 targets missing from the
new export, delisted or re-issued under a new id (55 share a name with a
current target), were still screened. Each load now records its full id
list in raw_sanctions_load, and staging screens only targets in each list's
latest export. warn_sanctions_delisted reports the rest.

The same reload showed the evaluation was too sensitive to the sample: with
matching unchanged, dropping those 187 targets reshuffled every plant and
moved recall from 97% to 93%. Plants are now chosen by a hash of seed and
target id, so a refresh only changes the plants of targets that changed,
and recall is reported over five seeds.

Effect, OFAC refresh alone, then with the UK list added:

| | OFAC, 2026-09 | OFAC, 2026-10 | UK + OFAC |
| --- | ---: | ---: | ---: |
| Real pairs at 70 | 33 | 33 | 38 |
| Alerts at 70 | 26 | 26 | 30 |
| Recall at 70, five seeds | 97% (one seed) | 93-97% | 93-96% |
| DOB-conflict plants alerting | 0 | 0 | 0 |

Five alerts come from targets only on the UK list:
- [company] (100), [company] (98) and [company]
  (77) against UAE free-zone companies under the UK Russia regime
  ([UAE company], [UAE company], [UAE company]).
- [officer] (97) against Malek Muhammad Ali (born 1956), and
  [officer] (89, born [birth month]) against Suleiman AL ABBAS, both under
  the UK Syria regime. The first officer is a secretary with no birth date
  and the second target has no birth date or country, so neither can be
  ruled out on this data.

[company] fell from 70.0 to just under, because the extra UK
names shift word weights. The threshold stays at 70.

