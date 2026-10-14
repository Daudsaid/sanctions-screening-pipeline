"""Fetch sanctions datasets from OpenSanctions and land them raw.

E: download the CSV, cache it to disk so a database wipe never costs a re-download.
L: hand rows to the shared loader. No filtering, renaming or typing here;
that all happens in dbt staging, which also merges targets listed by more
than one dataset (OpenSanctions gives them the same id).

Datasets: the US OFAC SDN list and the UK Sanctions List (FCDO), which
replaced OFSI's Consolidated List in January 2026. Run one with --dataset.
"""

import argparse
import csv
import sys
from pathlib import Path

import httpx

from ingest.loader import content_hash, get_connection, load_raw

DATASETS = ("us_ofac_sdn", "gb_fcdo_sanctions")
URL = "https://data.opensanctions.org/datasets/latest/{dataset}/targets.simple.csv"
VOLATILE = frozenset({"last_seen"})


def cache_path(dataset: str) -> Path:
    return Path("data/raw") / f"{dataset}.targets.simple.csv"


def fetch(dataset: str) -> Path:
    path = cache_path(dataset)
    path.parent.mkdir(parents=True, exist_ok=True)
    url = URL.format(dataset=dataset)
    with httpx.stream("GET", url, follow_redirects=True, timeout=120) as resp:
        resp.raise_for_status()
        with path.open("wb") as f:
            for chunk in resp.iter_bytes():
                f.write(chunk)
    return path


def read_rows(path: Path) -> list[tuple[str, dict]]:
    with path.open(newline="", encoding="utf-8") as f:
        return [(row["id"], row) for row in csv.DictReader(f)]


def load(conn, dataset: str) -> None:
    path = fetch(dataset)
    rows = read_rows(path)
    print(f"{dataset}: downloaded {len(rows)} rows to {path}")
    if not rows:
        # A header-only export (as OFSI's was in 2026-09) must not pass as
        # "nothing changed".
        sys.exit(f"{dataset}: export is empty, nothing loaded")

    with conn.cursor() as cur:
        cur.execute(
            "select source_version from raw_sanctions_snapshot where dataset = %s",
            (dataset,),
        )
        seen = {r[0] for r in cur.fetchall()}

    new_rows = [
        (key, payload) for key, payload in rows if content_hash(payload, VOLATILE) not in seen
    ]
    loaded = load_raw(
        conn,
        "raw_sanctions_snapshot",
        "target_id",
        new_rows,
        extra={"dataset": dataset},
        hash_ignore=VOLATILE,
    )
    print(f"{dataset}: loaded {loaded} new rows ({len(rows) - loaded} already present)")

    # Record the export's full id list: staging screens only these.
    conn.execute(
        "insert into raw_sanctions_load (dataset, row_count, target_ids) values (%s, %s, %s)",
        (dataset, len(rows), [key for key, _ in rows]),
    )
    conn.commit()


def run() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--dataset", choices=DATASETS, help="load one dataset (default: all)")
    args = p.parse_args()
    conn = get_connection()
    for dataset in [args.dataset] if args.dataset else DATASETS:
        load(conn, dataset)


if __name__ == "__main__":
    run()
