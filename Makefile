.PHONY: install lint format typecheck test test-integration migrate api dagster web up down

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

up:
	docker compose up -d --build

down:
	docker compose down
