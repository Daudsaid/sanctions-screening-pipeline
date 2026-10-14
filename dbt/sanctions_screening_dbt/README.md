# sanctions_screening_dbt

The dbt project for the sanctions screening pipeline: staging models over the
raw JSON landing tables, `int_name_norm` (shared name normalisation for
subjects and sanctions targets), seeds for legal forms and nationality codes,
and the data quality tests.

Run it from the repository root with `make dbt-build`, which installs the
packages (`dbt deps`) and builds everything with `profiles.yml` from this
folder. See the [main README](../../README.md) and
[docs/decisions.md](../../docs/decisions.md) for the design.
