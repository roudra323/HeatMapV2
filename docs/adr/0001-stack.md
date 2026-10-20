# ADR 0001 — Platform stack and layout

- Status: accepted
- Date: 2026-10-20

## Context
HeatMap v1 was a prototype: hand-made CSVs without amounts or contract
addresses, two disconnected analysis scripts, and an API reading files that no
step produced. v3 restarts on a clean tree with the goal of **tracking wallets,
modelling their behaviour over time and characterising their neighbouring
wallets**.

## Decision
- **Monorepo, uv workspace**: `packages/core` (domain library), `apps/api`
  (FastAPI), `pipelines` (Dagster), `apps/web` (Next.js).
- **PostgreSQL** is the single source of truth; schema via **SQLAlchemy 2.0 +
  Alembic**. Analytics jobs read with Polars and write results back.
- **Dagster** orchestrates assets; cadences come from `schedules.*` cron strings
  in config.
- **Providers** sit behind one `TransferProvider` protocol. A `ProviderRouter`
  spreads requests over multiple providers and multiple keys per provider,
  benching a key on rate-limit/quota errors and failing over to the next one.
- **Ethereum first, multi-chain ready**: `chain_id` is part of every key; chains
  are declared in config and resolved through `ChainRegistry`.
- Tooling: ruff, mypy (strict), pytest, pre-commit, GitHub Actions, Docker
  Compose.

## Consequences
- Adding a chain is a config change plus provider support for that network.
- Adding a provider is one adapter class implementing the protocol.
- Running locally needs PostgreSQL (Docker Compose provides one).
