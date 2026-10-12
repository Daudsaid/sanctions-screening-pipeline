"""Tests for the extract/load helpers. No database or network needed."""

import csv
from pathlib import Path

from ingest.companies_house_bulk import read_slice
from ingest.loader import content_hash
from ingest.opensanctions import VOLATILE, read_rows

TARGET = {
    "id": "NK-abc",
    "schema": "Person",
    "name": "Alireza Derakhshan",
    "last_change": "2025-01-10T00:00:00",
    "last_seen": "2026-10-01T00:00:00",
}


# content_hash decides whether a re-run lands a new version. These pin the
# behaviour behind "a second run against an unchanged export loads 0 rows".


def test_hash_ignores_volatile_last_seen():
    restamped = {**TARGET, "last_seen": "2026-10-12T00:00:00"}
    assert content_hash(TARGET, VOLATILE) == content_hash(restamped, VOLATILE)


def test_hash_detects_last_seen_when_not_ignored():
    restamped = {**TARGET, "last_seen": "2026-10-12T00:00:00"}
    assert content_hash(TARGET) != content_hash(restamped)


def test_hash_detects_a_real_change():
    renamed = {**TARGET, "name": "Alireza Derakhshani"}
    assert content_hash(TARGET, VOLATILE) != content_hash(renamed, VOLATILE)


def test_hash_ignores_key_order():
    reordered = dict(reversed(list(TARGET.items())))
    assert content_hash(TARGET, VOLATILE) == content_hash(reordered, VOLATILE)


def test_opensanctions_volatile_fields():
    assert VOLATILE == frozenset({"last_seen"})


def test_read_rows_keys_on_id_and_keeps_multiline_values(tmp_path: Path):
    path = tmp_path / "targets.simple.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["id", "name", "addresses"])
        w.writeheader()
        w.writerow({"id": "T1", "name": "Acme", "addresses": "Line 1\nLine 2"})
        w.writerow({"id": "T2", "name": "Beta", "addresses": ""})
    rows = read_rows(path)
    assert [key for key, _ in rows] == ["T1", "T2"]
    assert rows[0][1]["addresses"] == "Line 1\nLine 2"


# read_slice: Active companies with a matching SIC code, header whitespace
# stripped, malformed rows skipped and reported.

HEADER = [
    "CompanyName",
    " CompanyNumber",
    "CompanyStatus",
    "SICCode.SicText_1",
    "SICCode.SicText_2",
    "SICCode.SicText_3",
    "SICCode.SicText_4",
]


def write_bulk(path: Path, rows: list[list[str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(HEADER)
        w.writerows(rows)


def test_read_slice_filters_status_and_sic(tmp_path: Path):
    path = tmp_path / "bulk.csv"
    write_bulk(
        path,
        [
            ["FUND LTD", "00000001", "Active", "66300 - Funds", "", "", ""],
            ["SHOP LTD", "00000002", "Active", "47110 - Retail", "", "", ""],
            ["OLD FUND LTD", "00000003", "Dissolved", "66300 - Funds", "", "", ""],
            ["MIXED LTD", "SC000004", "Active", "47110 - Retail", "", "", "66300 - Funds"],
        ],
    )
    rows, malformed = read_slice(path, {"66300"}, limit=None)
    assert [key for key, _ in rows] == ["00000001", "SC000004"]
    assert malformed == []


def test_read_slice_strips_header_whitespace_only(tmp_path: Path):
    path = tmp_path / "bulk.csv"
    write_bulk(path, [[" FUND LTD ", "00000001", "Active", "66300 - Funds", "", "", ""]])
    rows, _ = read_slice(path, {"66300"}, limit=None)
    payload = rows[0][1]
    assert "CompanyNumber" in payload
    assert payload["CompanyName"] == " FUND LTD "  # values are untouched


def test_read_slice_skips_and_reports_malformed_rows(tmp_path: Path):
    path = tmp_path / "bulk.csv"
    write_bulk(
        path,
        [
            ["FUND LTD", "00000001", "Active", "66300 - Funds", "", "", ""],
            ["BROKEN", "00000002", "Active"],
        ],
    )
    rows, malformed = read_slice(path, {"66300"}, limit=None)
    assert len(rows) == 1
    assert malformed == [3]


def test_read_slice_respects_limit(tmp_path: Path):
    path = tmp_path / "bulk.csv"
    write_bulk(
        path,
        [[f"FUND {i} LTD", f"0000000{i}", "Active", "66300 - Funds", "", "", ""] for i in range(5)],
    )
    rows, _ = read_slice(path, {"66300"}, limit=2)
    assert len(rows) == 2
