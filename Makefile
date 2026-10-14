RUN := uv run --env-file $(CURDIR)/.env
DBT_DIR := dbt/sanctions_screening_dbt

.PHONY: up schema lint test dbt-build dbt-unit candidates score eval check

up:
	docker compose up -d --wait

# The container also runs schema/ on first start; this reapplies it (idempotent).
schema:
	docker compose exec -T postgres sh -c 'psql -v ON_ERROR_STOP=1 -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"' < schema/001_raw.sql

lint:
	uv run ruff check .
	uv run ruff format --check .

test:
	uv run pytest -q

dbt-build:
	cd $(DBT_DIR) && $(RUN) dbt build --profiles-dir .

dbt-unit:
	cd $(DBT_DIR) && $(RUN) dbt test --profiles-dir . --select test_type:unit

candidates:
	$(RUN) python -m matching.block

score:
	$(RUN) python -m matching.score

eval:
	$(RUN) python -m eval.evaluate

check: lint test dbt-unit
