"""Slice the Companies House bulk file and land the slice raw.

E: read the cached CSV, keep Active companies matching the SIC codes.
L: hand rows to the shared loader.

Reads data/raw/ch_fin_candidates.csv when present (a grep-filtered subset of
the full bulk file, SIC 64/65/66 only) so slice tuning takes seconds instead
of minutes. Falls back to the full file.

Header names are stripped of whitespace because the source has leading spaces
(' CompanyNumber'). That is the only change made to the raw data; values are
untouched. Rows with the wrong column count are skipped and reported.
"""

import argparse
import csv
import sys
from pathlib import Path

from ingest.loader import content_hash, get_connection, load_raw

SUBSET = Path("data/raw/ch_fin_candidates.csv")


def find_csv() -> Path:
    if SUBSET.exists():
        return SUBSET
    files = sorted(Path("data/raw").glob("BasicCompanyDataAsOneFile-*.csv"))
    if not files:
        sys.exit("no bulk CSV in data/raw/")
    return files[-1]


def read_slice(path: Path, codes: set[str], limit: int | None):
    rows, malformed = [], []
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = [h.strip() for h in next(reader)]
        width = len(header)
        idx = {h: i for i, h in enumerate(header)}
        sic_cols = [idx[f"SICCode.SicText_{n}"] for n in (1, 2, 3, 4)]
        status, number = idx["CompanyStatus"], idx["CompanyNumber"]
        for row in reader:
            if len(row) != width:
                malformed.append(reader.line_num)
                continue
            if row[status] != "Active":
                continue
            if not any(row[i][:5] in codes for i in sic_cols):
                continue
            rows.append((row[number], dict(zip(header, row))))
            if limit and len(rows) >= limit:
                break
    return rows, malformed


def run() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--sic", required=True, help="comma-separated 5-digit SIC codes")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    codes = {c.strip() for c in args.sic.split(",")}
    path = find_csv()
    rows, malformed = read_slice(path, codes, args.limit)
    print(f"{path.name}: {len(rows)} active companies match {sorted(codes)}")
    print(f"malformed rows skipped: {len(malformed)} at lines {malformed[:5]}")
    if args.dry_run:
        return

    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("select source_version from raw_ch_company")
        seen = {r[0] for r in cur.fetchall()}
    new_rows = [(k, v) for k, v in rows if content_hash(v) not in seen]
    loaded = load_raw(conn, "raw_ch_company", "company_number", new_rows)
    print(f"loaded {loaded} new rows ({len(rows) - loaded} already present)")


if __name__ == "__main__":
    run()
