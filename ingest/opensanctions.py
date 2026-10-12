"""Fetch a sanctions dataset from OpenSanctions and land it raw.

E: download the CSV, cache it to disk so a database wipe never costs a re-download.
L: hand rows to the shared loader. No filtering, renaming or typing here;
that all happens in dbt staging.
"""

import csv
from pathlib import Path

import httpx

from ingest.loader import content_hash, get_connection, load_raw

DATASET = "us_ofac_sdn"
URL = f"https://data.opensanctions.org/datasets/latest/{DATASET}/targets.simple.csv"
CACHE = Path("data/raw") / f"{DATASET}.targets.simple.csv"
VOLATILE = frozenset({"last_seen"})


def fetch() -> Path:
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    with httpx.stream("GET", URL, follow_redirects=True, timeout=120) as resp:
        resp.raise_for_status()
        with CACHE.open("wb") as f:
            for chunk in resp.iter_bytes():
                f.write(chunk)
    return CACHE


def read_rows(path: Path) -> list[tuple[str, dict]]:
    with path.open(newline="", encoding="utf-8") as f:
        return [(row["id"], row) for row in csv.DictReader(f)]


def run() -> None:
    path = fetch()
    rows = read_rows(path)
    print(f"downloaded {len(rows)} rows to {path}")

    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(
            "select source_version from raw_sanctions_snapshot where dataset = %s",
            (DATASET,),
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
        extra={"dataset": DATASET},
        hash_ignore=VOLATILE,
    )
    print(f"loaded {loaded} new rows ({len(rows) - loaded} already present)")


if __name__ == "__main__":
    run()
