# HeatMap

Track Ethereum wallets, model how they behave over time, and discover and
characterise the wallets around them.

- **Track**: a watchlist of wallets, synced incrementally from Alchemy and
  Etherscan with automatic failover across multiple keys per provider.
- **Behaviour**: per-wallet feature snapshots for 7d / 30d / 90d / all-time
  windows, explainable tags, behaviour clusters, anomaly scores and drift
  between snapshots.
- **Neighbours**: an interaction graph, neighbour discovery that never expands
  through exchanges, routers or token contracts, communities, ego networks,
  shared-funder and counterparty-overlap signals, behaviourally similar wallets.

Ethereum mainnet is configured; other EVM chains are a config entry away (see
[Adding a chain](#adding-a-chain)).

## Architecture

```
config/*.yaml + HEATMAP_* env
        │
ProviderRouter (alchemy keys, etherscan keys … rate limits, quotas, failover)
        │
sync ─▶ normalize ─▶ graph (edges, expansion, communities) ─▶ features ─▶ models
  └────────────── PostgreSQL (single source of truth) ──────────────────────┘
        │                                               │
   Dagster (schedules, sensor)                    FastAPI /v1 ─▶ Next.js web
```

Details: [docs/architecture.md](docs/architecture.md) ·
[docs/data-dictionary.md](docs/data-dictionary.md) ·
[docs/adr/0001-stack.md](docs/adr/0001-stack.md)

## Repository layout

```
apps/api        FastAPI service (/v1, OpenAPI at /docs)
apps/web        Next.js 16 frontend (typed client generated from the OpenAPI spec)
packages/core   domain library: config, db, providers, ingestion, normalize,
                entities, graph, features, models, exports, pipeline, cli, demo
pipelines       Dagster assets, jobs, schedules and the watchlist sensor
config          default.yaml (no secrets; keys are referenced by env var name)
infra/docker    Dockerfiles; docker-compose.yml runs the whole stack
tests           unit tests and PostgreSQL integration tests
```

## Quick start

Requirements: Python 3.12 with [uv](https://docs.astral.sh/uv/), Node 20+,
PostgreSQL 16 (or Docker).

```bash
cp .env.example .env                 # add provider keys (any number per provider)
uv sync                              # Python workspace
make migrate                         # create the schema (HEATMAP_DATABASE_URL)

# Try it without keys: load a synthetic dataset and run every stage
uv run heatmap demo

make api                             # http://localhost:8000/docs
make web                             # http://localhost:3000 (cd apps/web && npm ci first)
make dagster                         # http://localhost:3000 for Dagster if web is not running
```

Or everything in containers: `docker compose up --build` (API :8000,
Dagster :3001, web :3000).

### Track real wallets

```bash
uv run heatmap watch add 0xd8da6bf26964af9d7eed9e03e53415d37aa96045 --note vitalik
uv run heatmap run all               # reference → sync → normalize → graph → features → models
```

With Dagster running, adding a wallet (CLI, API `POST /v1/watchlist` or the web
form) triggers a sync through the sensor; the rest runs on the schedules.

## Configuration

`config/default.yaml` is loaded first, then any files in
`HEATMAP_CONFIG_FILES` (comma separated, later wins), then `HEATMAP_*`
environment variables (`__` for nesting, e.g. `HEATMAP_SCHEDULES__SYNC_CRON`).

| Section | What it controls |
|---|---|
| `providers` | Providers, priority, cooldowns and **keys**. Each key names the env var holding the secret, its `rps` and optional `daily_quota`. Add as many keys as you have. |
| `chains` | Enabled chains, which providers serve them, confirmations, reorg window, sync chunk size. |
| `schedules` | Cron strings for sync, expansion, features and models; timezone; on/off. |
| `expansion` | Hops, top-N per wallet, minimum interactions, look-back window, hub degree threshold, global neighbour budget. |
| `spam` | Spam rules (non-ASCII symbols, zero-value poisoning, airdrop threshold). |
| `features` | Windows, minimum transfers, co-timing bucket size. |
| `models` | Model window, drift window, cluster size, anomaly contamination, drift threshold. |
| `pricing` | CoinGecko base URL and API key env var. |

### Provider routing

Requests go to the highest-priority provider with a usable key, round-robin
across that provider's keys. A key is benched on HTTP 429 / rate-limit
messages (for `retry_after` or `cooldown_s`), benched until the next UTC day on
quota errors or when its local `daily_quota` is used up, and disabled on auth
errors. Transient errors are retried with backoff. When one provider runs out,
the next takes over; when all are out, the sync run stops cleanly and resumes
from the stored block cursor next time. Daily usage per key is stored in
`provider_key_usage`.

### Adding a chain

```yaml
chains:
  base:
    chain_id: 8453
    providers: [alchemy, etherscan]
    alchemy_network: base-mainnet
    explorer_url: https://basescan.org
```

Add `entities/data/labels_base.csv` and `tokens_base.csv` for hubs and verified
tokens. Dagster partitions, the API (`?chain=base`) and the CLI (`--chain base`)
pick the chain up automatically.

## Development

```bash
make lint typecheck test             # ruff, mypy --strict, unit tests
HEATMAP_TEST_DATABASE_URL=postgresql+psycopg://heatmap:heatmap@localhost:5432/heatmap_test \
  make test-integration              # PostgreSQL tests (CI runs both)
cd apps/web && npm run lint && npm run typecheck && npm run build
uv run python -m heatmap_api.openapi apps/web/openapi.json && (cd apps/web && npm run gen:api)
```

Schema changes: edit the models in `packages/core/src/heatmap_core/db/models`,
then `uv run alembic -c packages/core/alembic.ini revision --autogenerate -m "…"`.
A test fails if models and migrations drift apart.

## Known limits

- Funding source, degree and similarity features only see transfers involving
  tracked wallets; they get better as the watchlist grows.
- The mass-airdrop rule counts recipients stored in our database, so it fires
  only when several tracked wallets receive the same drop.
- Hub and token seed lists are small starting sets; extend the CSVs (or insert
  `entity_labels` rows with `source != 'seed_file'`, which the seed loader never
  overwrites).
- Hour-of-day features are in UTC.
