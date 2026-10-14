"""Tests for the workflow file check."""

from scripts.check_workflows import problems

GOOD = """
on:
  push:
jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: "uv run dbt build --vars '{min_rows_check: false}'"
"""


def test_valid_workflow_passes():
    assert problems(GOOD) == []


def test_unquoted_colon_in_run_is_caught():
    # The bug that broke CI: ": " inside a plain scalar.
    bad = GOOD.replace(
        "run: \"uv run dbt build --vars '{min_rows_check: false}'\"",
        "run: uv run dbt build --vars '{min_rows_check: false}'",
    )
    assert problems(bad)


def test_step_without_run_or_uses_is_caught():
    bad = GOOD + "      - name: nothing\n"
    assert problems(bad) == ["job check, step 3: needs 'run' or 'uses'"]


def test_missing_jobs_is_caught():
    assert "no jobs" in problems("on: push\n")
