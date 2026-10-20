# One image for the API, migrations and Dagster (webserver + daemon).
FROM python:3.12-slim AS base
COPY --from=ghcr.io/astral-sh/uv:0.4 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PATH="/app/.venv/bin:$PATH"
WORKDIR /app

COPY pyproject.toml uv.lock .python-version ./
COPY packages/core/pyproject.toml packages/core/pyproject.toml
COPY apps/api/pyproject.toml apps/api/pyproject.toml
COPY pipelines/pyproject.toml pipelines/pyproject.toml
RUN uv sync --frozen --no-dev --no-install-workspace

COPY packages packages
COPY apps/api apps/api
COPY pipelines pipelines
COPY config config
RUN uv sync --frozen --no-dev

RUN useradd --create-home app && mkdir -p /opt/dagster/home && chown app /opt/dagster/home
USER app
