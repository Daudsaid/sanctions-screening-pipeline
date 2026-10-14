"""Fail if a GitHub Actions workflow file isn't valid YAML or lacks the basics.

GitHub rejects a workflow that doesn't parse before any step runs, so CI
can't report the error itself. Run by `make lint` before pushing.
"""

import sys
from pathlib import Path

import yaml

WORKFLOWS = Path(".github/workflows")


def problems(text: str) -> list[str]:
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError as e:
        return [str(e).replace("\n", " ")]
    if not isinstance(doc, dict):
        return ["not a mapping"]
    found = []
    # YAML 1.1 reads a bare `on:` key as the boolean True.
    if "on" not in doc and True not in doc:
        found.append("no 'on' trigger")
    jobs = doc.get("jobs")
    if not isinstance(jobs, dict) or not jobs:
        return [*found, "no jobs"]
    for name, job in jobs.items():
        for i, step in enumerate(job.get("steps") or [], 1):
            if not isinstance(step, dict) or not ({"run", "uses"} & step.keys()):
                found.append(f"job {name}, step {i}: needs 'run' or 'uses'")
    return found


def main() -> int:
    files = sorted([*WORKFLOWS.glob("*.yml"), *WORKFLOWS.glob("*.yaml")])
    failed = False
    for path in files:
        for p in problems(path.read_text()):
            print(f"{path}: {p}")
            failed = True
    if not failed:
        print(f"{len(files)} workflow file(s) OK")
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
