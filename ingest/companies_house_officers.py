"""Fetch officers for the sliced companies from the Companies House API.

E: one call per company (paged past 100 officers), cached to
data/raw/officers/<company_number>.json so an interrupted run resumes and a
database wipe never costs another crawl.
L: each officer item lands as its own unmodified row in raw_ch_officer.

Resigned officers are included. Filtering on resigned_on happens in staging.
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import httpx

from ingest.loader import content_hash, get_connection, load_raw

BASE = "https://api.company-information.service.gov.uk"
CACHE = Path("data/raw/officers")
PAGE = 100
PAUSE = 0.55  # about 109 requests/min, under the 600 per 5 min limit


def get(client: httpx.Client, url: str, params: dict) -> httpx.Response:
    for _ in range(6):
        time.sleep(PAUSE)
        r = client.get(url, params=params)
        if r.status_code == 429:
            wait = int(r.headers.get("Retry-After", 30))
            print(f"429 received, sleeping {wait}s")
            time.sleep(wait)
            continue
        return r
    r.raise_for_status()
    return r


def fetch_company(client: httpx.Client, number: str) -> dict:
    items, start = [], 0
    while True:
        r = get(
            client,
            f"{BASE}/company/{number}/officers",
            {"items_per_page": PAGE, "start_index": start},
        )
        if r.status_code == 404:
            return {"company_number": number, "total_results": 0, "items": [], "http_status": 404}
        r.raise_for_status()
        data = r.json()
        items.extend(data.get("items", []))
        total = data.get("total_results", len(items))
        start += PAGE
        if start >= total:
            break
    return {"company_number": number, "total_results": total, "items": items}


def run() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=None, help="fetch at most N uncached companies")
    args = p.parse_args()

    key = os.environ.get("COMPANIES_HOUSE_API_KEY")
    if not key:
        sys.exit("COMPANIES_HOUSE_API_KEY not set (run with: uv run --env-file .env ...)")

    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("select company_number from raw_ch_company order by company_number")
        numbers = [r[0] for r in cur.fetchall()]

    CACHE.mkdir(parents=True, exist_ok=True)
    todo = [n for n in numbers if not (CACHE / f"{n}.json").exists()]
    cached = len(numbers) - len(todo)
    if args.limit:
        todo = todo[: args.limit]
    print(f"{len(numbers)} companies, {cached} cached, fetching {len(todo)} this run")

    started = time.time()
    with httpx.Client(auth=(key, ""), timeout=30) as client:
        for i, number in enumerate(todo, 1):
            result = fetch_company(client, number)
            (CACHE / f"{number}.json").write_text(json.dumps(result))
            if i % 100 == 0:
                mins = (time.time() - started) / 60
                print(f"fetched {i}/{len(todo)} in {mins:.1f} min")

    print(f"fetch phase: {time.time() - started:.1f}s for {len(todo)} companies")
    rows = []
    for path in sorted(CACHE.glob("*.json")):
        data = json.loads(path.read_text())
        rows.extend((data["company_number"], item) for item in data["items"])

    with conn.cursor() as cur:
        cur.execute("select source_version from raw_ch_officer")
        seen = {r[0] for r in cur.fetchall()}
    new_rows = [(k, v) for k, v in rows if content_hash(v) not in seen]
    loaded = load_raw(conn, "raw_ch_officer", "company_number", new_rows)
    print(f"loaded {loaded} new officer rows ({len(rows) - loaded} already present)")


if __name__ == "__main__":
    run()
