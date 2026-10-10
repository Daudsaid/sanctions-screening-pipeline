"""Query helper for exploration notebooks."""

import os

import polars as pl
import psycopg

pl.Config.set_tbl_rows(30)
pl.Config.set_fmt_str_lengths(80)

_conn = psycopg.connect(
    host=os.environ.get("POSTGRES_HOST", "localhost"),
    port=os.environ.get("POSTGRES_PORT", "5432"),
    dbname=os.environ.get("POSTGRES_DB", "sanctions_screening"),
    user=os.environ.get("POSTGRES_USER", "sift"),
    password=os.environ.get("POSTGRES_PASSWORD", "sift"),
    autocommit=True,
)


def q(sql: str) -> pl.DataFrame:
    """Run a query and return the result as a DataFrame."""
    return pl.read_database(sql, connection=_conn)
