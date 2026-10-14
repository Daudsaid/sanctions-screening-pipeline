
## Sanctions source: OFAC for v1, UK Sanctions List next

The first choice was gb_hmt_sanctions (the OFSI Consolidated List). On
2026-09-19 OpenSanctions' bulk export for it returned a header-only CSV
(175 bytes) at the origin, confirmed via x-goog-stored-content-length on the
GCS-backed CDN response; a cache-busted request returned the same.

That was not an upstream bug. OFSI closed the Consolidated List on
28 January 2026, and the UK Sanctions List, published by the FCDO, is now the
only source of UK designations. The OFSI list is frozen, so pulling GOV.UK's
OFSI CSV directly is not an alternative either.

v1 uses us_ofac_sdn: same OpenSanctions schema, 20,346 targets. (An earlier
note said 20,349; the loaded raw table and staging both hold 20,346.)
Next step: add OpenSanctions' gb_fcdo_sanctions dataset (the UK Sanctions
List), since a pipeline screening UK companies should screen against UK
designations, and deduplicate targets designated on both lists.

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
- Officers: 26,192 person appointments, all in "SURNAME, Forenames" form
  (enforced by a test). 1,906 corporate officer appointments are matched on
  the organisation side.
  3,103 secretaries have no date of birth and can only match on name.
- 21,613 distinct officer IDs across 28,098 appointments (20,772 of them
  person IDs), so screening is per officer ID. This is an upper bound on
  people: Companies House does not always merge one person's records. After
  the current-officers filter below, 9,859 person and 272 corporate officer
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
name, leaving 40,027. Subjects: 9,859 person officers, 272 corporate
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
the same kind with rapidfuzz: 9,869 x 18,253 person names and 6,793 x 21,467
organisation names, about 330M pairs, in roughly two minutes on a laptop.
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

Result: 530 person and 3,440 organisation candidate name pairs. Candidates
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
  target gives a year only, +5 same year, -40 when no target date is within a
  year, 0 when either side is missing or the years are one apart (OFAC dates
  are sometimes approximate).
- Nationality (persons): +5 overlap, -5 both known and no overlap. Kept small
  because OFAC countries mix nationality and residence.

Weights are hand-set. On the real data, 3,708 pairs are scored; 3 person and
12 organisation pairs reach 80. None look like true matches: the top is
exact name collisions ([company], [officer], where one officer ID has a
birth date five months from the target's and the other has none) and
spelling variants ([company] / INPESCA). The alert threshold, and whether the
weights hold up, are for the evaluation set to decide.

## Evaluation (eval/evaluate.py, docs/evaluation.md)

Recall is measured on planted matches: 200 OFAC person and 200 organisation
targets (seeded sample, Latin-script primary names), each given one fake
subject with one change (typo, word order, middle name dropped or added,
transliteration, UK legal suffix, UK / GROUP). Half the person plants have a
conflicting birth year and are negatives. Real Companies House subjects are
treated as negatives. Plants go through the production candidate_pairs and
score_pair with the production word weights.

Alert threshold: 70. At 70, recall is 97% of 300 true plants (persons 100%,
96% on name alone, organisations 96%), with 33 alerts on real subjects
(5 person, 28 organisation) and no birth-date-conflict plant alerting. At 80
the real alerts fall to 15 but recall drops to 95%, and to 86% for persons
scored on name alone. A conflict caps a perfect name at 60 (65 with a
nationality match), so 70 keeps a margin above that.

Weak spots, left untuned: organisation typos (84% at 70), because fuzz.ratio
counts a substituted letter as two edits, so words under seven letters can't
absorb one, and the misspelt word gets the top rarity weight; and a one-word
target with UK or GROUP added (TRIALKOM / TRIALKOM GROUP), which the
two-word guard keeps out of candidates entirely.
