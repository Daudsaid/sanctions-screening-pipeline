"""Shared load step (the L in ELT).

Lands raw payloads into raw_* tables as JSONB. No filtering, no typing.
Every ingest script fetches its data, then calls load_raw.
"""

import hashlib
import json
import os

import psycopg


def get_connection() -> psycopg.Connection:
    return psycopg.connect(
        host=os.environ.get("POSTGRES_HOST", "localhost"),
        port=os.environ.get("POSTGRES_PORT", "5432"),
        dbname=os.environ.get("POSTGRES_DB", "sanctions_screening"),
        user=os.environ.get("POSTGRES_USER", "sift"),
        password=os.environ.get("POSTGRES_PASSWORD", "sift"),
    )


def content_hash(payload: dict) -> str:
    """Stable hash of a raw record, stored as source_version for audit."""
    blob = json.dumps(payload, sort_keys=True).encode()
    return hashlib.sha256(blob).hexdigest()


def load_raw(
    conn: psycopg.Connection,
    table: str,
    key_column: str,
    rows: list[tuple[str, dict]],
    extra: dict[str, str] | None = None,
) -> int:
    """COPY (key, payload) pairs into a raw_* table.

    extra holds constant columns for the whole batch, e.g. {"dataset": "us_ofac_sdn"}.
    """
    extra = extra or {}
    columns = [key_column, *extra.keys(), "raw", "source_version"]
    with conn.cursor() as cur:
        with cur.copy(f"COPY {table} ({', '.join(columns)}) FROM STDIN") as copy:
            for key, payload in rows:
                copy.write_row([key, *extra.values(), json.dumps(payload), content_hash(payload)])
    conn.commit()
    return len(rows)
