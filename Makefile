.PHONY: install lint format typecheck test test-integration migrate api dagster web web-demo snapshot up down

# Scratch database for the web demo snapshot; `make snapshot` wipes it.
DEMO_DATABASE_URL ?= postgresql+psycopg://heatmap:heatmap@localhost:5432/heatmap_demo

install:
	uv sync
	cd apps/web && npm ci

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff check --fix .
	uv run ruff format .

typecheck:
	uv run mypy packages/core/src apps/api/src pipelines/src

test:
	uv run pytest -m "not integration and not live"

test-integration:
	uv run pytest -m integration

migrate:
	uv run alembic -c packages/core/alembic.ini upgrade head

api:
	uv run uvicorn heatmap_api.main:app --reload --port 8000

dagster:
	uv run dagster dev -m heatmap_pipelines.definitions -p 3001

web:
	cd apps/web && npm run dev

# The web app on the static demo snapshot: no API or database needed.
web-demo:
	cd apps/web && NEXT_PUBLIC_DEMO=1 npm run dev

# Rebuild apps/web/public/demo: reset the scratch database, load the demo, export the API.
snapshot:
	HEATMAP_DATABASE_URL=$(DEMO_DATABASE_URL) uv run alembic -c packages/core/alembic.ini downgrade base
	HEATMAP_DATABASE_URL=$(DEMO_DATABASE_URL) uv run alembic -c packages/core/alembic.ini upgrade head
	HEATMAP_DATABASE_URL=$(DEMO_DATABASE_URL) uv run heatmap demo > /dev/null
	HEATMAP_DATABASE_URL=$(DEMO_DATABASE_URL) uv run python -m heatmap_api.snapshot apps/web/public/demo

up:
	docker compose up -d --build

down:
	docker compose down
