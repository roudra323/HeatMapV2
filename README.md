# HeatMap

Track Ethereum wallets, model their behaviour over time, and discover and
characterise their neighbouring wallets.

Status: under active development (v3 rewrite). See
[docs/architecture.md](docs/architecture.md) and [docs/adr](docs/adr).

## Layout
```
apps/api        FastAPI service (/v1)
apps/web        Next.js frontend
packages/core   domain library: config, db, providers, ingestion, graph, features, models
pipelines       Dagster assets, jobs and schedules
config          YAML configuration (secrets come from env vars)
tests           unit and integration tests
```

## Quick start
```bash
cp .env.example .env      # add provider keys
uv sync
make test
```
