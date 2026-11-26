# HeatMap

**Find the people behind DEX trades, map who they deal with, and group them by behaviour.**

[![CI](https://github.com/roudra323/HeatMapV2/actions/workflows/ci.yml/badge.svg)](https://github.com/roudra323/HeatMapV2/actions/workflows/ci.yml)
![Python 3.12](https://img.shields.io/badge/python-3.12-3776ab)
![PostgreSQL 16](https://img.shields.io/badge/postgresql-16-336791)
![Next.js 16](https://img.shields.io/badge/next.js-16-000000)
![mypy strict](https://img.shields.io/badge/mypy-strict-2a6db2)

**[Live demo](https://heat-map-v2.vercel.app)** · [Architecture](docs/architecture.md) · [Data dictionary](docs/data-dictionary.md) · [Operations](docs/operations.md)

HeatMap reads every Uniswap (v2, v3, v4) and SushiSwap swap on Ethereum and
attributes it to the wallet that signed it. It sets the bots aside and starts
tracking the real traders. Around each tracked wallet it maps the wallets it
deals with, builds behaviour profiles over time, and groups everyone into
explainable tags and clusters: candidate audience segments for Web3 marketing.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/discover-dark.png">
  <img alt="Discover page: traders found in DEX swaps, with bots labelled by the rule that caught them" src="docs/images/discover-light.png">
</picture>

> The live demo runs the real web app on a static, read-only snapshot of a
> synthetic dataset (see [Demo mode](#demo-mode)). The full pipeline runs on
> Ethereum mainnet with an Alchemy key.

## Contents

- [What it does](#what-it-does)
- [Design decisions](#design-decisions)
- [Architecture](#architecture)
- [Tech stack](#tech-stack)
- [Quick start](#quick-start)
- [Demo mode](#demo-mode)
- [Web app](#web-app) and [HTTP API](#http-api)
- [Development](#development)
- [Status and roadmap](#status-and-roadmap)

## What it does

1. **Discover.** Scans new blocks for swaps on verified pools, values them in
   USD, scores every signer over 30 days and filters out bots: MEV contracts,
   arbitrage, solvers, batch executors and high-frequency traders.
2. **Track.** Promotes the steadiest human traders to a watchlist (next to
   wallets you add yourself), vets them, and syncs their full transfer
   history.
3. **Expand.** Builds an interaction graph and adds each wallet's closest
   counterparties as neighbours, without crossing exchanges, routers or other
   hubs.
4. **Segment.** Computes behaviour features over 7, 30 and 90 days and all
   time, then tags, clusters (HDBSCAN), anomaly scores (Isolation Forest) and
   drift between snapshots.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/wallet-dark.png">
  <img alt="Wallet page: behaviour profile, what stands out, and the DEX trades the wallet signed" src="docs/images/wallet-light.png">
</picture>
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/activity-dark.png">
  <img alt="Activity heatmap by weekday and UTC hour, and weekly transfers in and out" src="docs/images/activity-light.png">
</picture>

## Design decisions

Most of the work is in getting attribution right on a noisy chain, where the
obvious reading of the data is often wrong.

- **The trader is the transaction signer** (`tx.from`). The Swap event's own
  `sender` is usually a router, so reading it would credit every trade to
  Uniswap.
- **Only verified pools count.** A known factory must confirm the pool, or,
  for v4, the pool key must hash to the emitted PoolId. Anyone can deploy a
  contract that emits Swap events; trades from unverified pools are stored but
  never scored.
- **Bots are caught by how they trade, not by lists.** A signer counts as a
  bot when it trades through settlement contracts (solvers), through private
  contracts or pools directly (MEV), in circular transactions (arbitrage),
  packs many swaps into one transaction (market makers), or trades more than
  `bot_tx_per_day` times a day. Each verdict keeps its reason.
- **Promotion ranks by activity, not size.** Candidates are ordered by active
  days, then tokens traded besides stablecoins, then volume. Ranking by volume
  alone filled the watchlist with treasuries and stablecoin rebalancers.
- **Wallets are vetted before their first sync.** Two cheap calls
  (`eth_getCode`, `eth_getTransactionCount`) reject contracts and wallets that
  sent too many transactions (exchanges, payout services) before they cost
  millions of transfer fetches. EIP-7702 delegated accounts count as wallets.
- **Expansion never crosses hubs.** Labelled entities, tokens, pools and
  addresses with too many counterparties are never added or expanded through,
  so one hop from a trader is not "everyone who used Binance".
- **Spam stays out of the features.** Look-alike tokens (non-ASCII symbols)
  and zero-value address poisoning are flagged, from either side of a
  transfer, so a poisoner cannot link unrelated wallets.
- **Every stage is resumable and safe to re-run.** Stages read from and write
  to PostgreSQL, keep cursors, and take a per-chain lock, so overlapping runs
  skip instead of doing the work twice.
- **Providers fail over per key.** Requests round-robin across keys and
  providers; a key is benched on rate limits, parked until the next UTC day on
  quota errors, and disabled on auth errors. When every key is out, a run
  stops cleanly and resumes from its cursors.

## Architecture

```
         Ethereum (Alchemy, Etherscan)                   DefiLlama prices
                    │                                             │
 discovery          │ swaps ▸ traders ▸ bots out ▸ promotion      │
                    ▼                                             │
                watchlist ◀─────── neighbours ──────────┐         │
                    │ (your seeds, promoted traders)    │         │
 sync               │ vet new wallets, pull transfers   │         │
 normalize          │ USD values, spam, funders ◀───────┼─────────┘
 graph              │ edges, neighbour expansion ───────┘
 features           │ behaviour per wallet and time window
 models             ▼ tags, clusters, anomalies, drift
              PostgreSQL ──▶ FastAPI /v1 ──▶ Next.js web app
```

| Stage | What it does | CLI | Dagster |
|---|---|---|---|
| reference | Loads seed labels (exchanges, routers, bridges…), verified tokens and DEX factories | `heatmap run reference` | `reference_data` asset |
| discovery | Scans new blocks for swaps, values them, scores traders over 30 days, filters bots, promotes the best | `heatmap run discovery` | `discovery_job`, every 10 min |
| sync | Vets automatically added wallets, then pulls new transfers for every active watchlist wallet | `heatmap run sync [--only-new]` | `sync_job`, hourly; a sensor syncs new wallets within a minute |
| normalize | Daily USD prices, spam flags, funding sources | `heatmap run normalize` | part of `sync_job` |
| graph | Rebuilds the interaction graph, adds neighbours, detects communities | `heatmap run graph` | `expansion_job`, every 6 h |
| features | Behaviour snapshot per wallet for 7d / 30d / 90d / all time | `heatmap run features` | `features_job`, daily |
| models | Tags, clusters, anomalies, drift | `heatmap run models` | runs right after features |

More: [architecture](docs/architecture.md), [data dictionary](docs/data-dictionary.md),
[stack decision record](docs/adr/0001-stack.md).

## Tech stack

| Area | Tools |
|---|---|
| Pipeline and domain | Python 3.12, uv workspace, SQLAlchemy 2.0, Alembic, psycopg 3, Pydantic, httpx, tenacity, structlog |
| Chain data | Alchemy and Etherscan (behind one provider router), eth-abi, Multicall3, DefiLlama prices |
| Analytics and ML | Polars, NumPy, NetworkX (graph, communities), scikit-learn (HDBSCAN, Isolation Forest) |
| Orchestration | Dagster: assets, schedules, a new-wallet sensor, per-chain partitions |
| API | FastAPI, OpenAPI spec checked into the repo |
| Web | Next.js 16, React 19, TypeScript, Tailwind CSS 4, d3-force; API client types generated from the OpenAPI spec |
| Quality | ruff, mypy `--strict`, pytest (unit and PostgreSQL integration tests), ESLint, GitHub Actions, pre-commit |
| Runtime | PostgreSQL 16, Docker Compose for the whole stack, Vercel for the web demo |

```
apps/api        FastAPI service (/v1, OpenAPI at /docs) and the demo snapshot exporter
apps/web        Next.js web app (typed API client, demo mode)
packages/core   Domain library: config, db, providers, dex, ingestion, normalize,
                entities, graph, features, models, exports, pipeline, cli, demo
pipelines       Dagster assets, jobs, schedules and sensors
config          default.yaml (no secrets)
docs            Architecture, data dictionary, operations, decision records
infra/docker    Dockerfiles; docker-compose.yml runs the whole stack
tests           Unit tests and PostgreSQL integration tests
```

## Quick start

Requirements: Python 3.12 with [uv](https://docs.astral.sh/uv/), Node 22
(20.9+ works), and PostgreSQL 16 (Docker Compose provides one).

```bash
git clone https://github.com/roudra323/HeatMapV2.git && cd HeatMapV2
cp .env.example .env                # add provider keys; .env is read from the working directory
make install                        # uv sync + npm ci for the web app
docker compose up -d postgres       # or point HEATMAP_DATABASE_URL at your own PostgreSQL
make migrate                        # create or upgrade the schema
```

**Without keys**, load the synthetic dataset and run every stage on it:

```bash
uv run heatmap demo
```

It covers a sybil farm, stablecoin and NFT users, a whale, spam airdrops and
address poisoning, plus DEX swaps from human traders of every size and one bot
of each kind the detector knows.

**With an Alchemy key**, discover real traders and build everything around
them:

```bash
uv run heatmap run reference          # seed labels, tokens and DEX factories
uv run heatmap run discovery          # first run: about a day of swaps
uv run heatmap run sync --only-new    # vet and sync the promoted traders
uv run heatmap run normalize
uv run heatmap run graph              # adds neighbours to the watchlist
uv run heatmap run sync --only-new    # vet and sync the neighbours
uv run heatmap run normalize
uv run heatmap run graph
uv run heatmap run features
uv run heatmap run models
```

`uv run heatmap run all` runs every stage once, in order. Then start the
services:

```bash
make api        # http://localhost:8000 (OpenAPI docs at /docs)
make web        # http://localhost:3000
make dagster    # http://localhost:3001: schedules and the new-wallet sensor
```

Or run the whole stack in containers with `docker compose up --build`: web
:3000, API :8000, Dagster :3001, PostgreSQL :5432.

Costs, configuration, label imports, adding a chain and catching up after a
break are in [docs/operations.md](docs/operations.md).

## Demo mode

The web app can run without the API or a database. With
`NEXT_PUBLIC_DEMO=1` it answers every request from a static snapshot in
`apps/web/public/demo`, and marks the site as a read-only demo. Tracking and
untracking are refused, and explorer links are hidden because the addresses
are synthetic.

```bash
make web-demo      # the web app on the snapshot, http://localhost:3000
make snapshot      # rebuild the snapshot
```

`make snapshot` resets a scratch database (`heatmap_demo`, override with
`DEMO_DATABASE_URL`), loads `heatmap demo` into it, and exports what the real
API returns (`heatmap_api.snapshot`). Lists are exported whole and filtered,
sorted and paged in the browser by the API's own rules
(`apps/web/src/lib/demo.ts`).

To deploy the demo on Vercel, set the project's **Root Directory** to
`apps/web`, **Node.js** to 22, and the environment variable
`NEXT_PUBLIC_DEMO=1`.

## Web app

| Page | What it shows |
|---|---|
| Overview `/` | The flow from DEX trades to audiences, the biggest traders right now, behaviour tags and what each segment moves and uses |
| Discover `/discover` | Traders found in DEX swaps: volume, activity, tokens, routes and bot verdicts; track any of them |
| Watchlist `/watchlist` | Tracked wallets by origin (seed, trader, neighbour) with sync status; add or untrack wallets |
| Wallet `/wallets/<address>` | Behaviour profile and what stands out, activity by weekday and hour, weekly timeline, neighbour graph, similar wallets, DEX trades and transfers |
| Clusters `/clusters` | A 2D behaviour map of all profiled wallets and what each cluster moves and uses |

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/clusters-dark.png">
  <img alt="Clusters page: a 2D behaviour map of profiled wallets, coloured by cluster" src="docs/images/clusters-light.png">
</picture>

The web app talks only to the API. Its typed client is generated from the
OpenAPI spec, and CI fails if the two drift apart.

## HTTP API

Every endpoint takes `?chain=` (default `ethereum`). List endpoints take
`limit` and `offset`. Interactive docs are at `http://localhost:8000/docs`.

| Endpoint | Returns |
|---|---|
| `GET /health`, `GET /v1/chains` | Liveness and the configured chains |
| `GET /v1/traders` | Traders discovered from DEX swaps; bots hidden unless `include_bots=true`; filter by `min_volume_usd` or `protocol`, sort by `volume`, `tx_count` or `last_trade` |
| `GET /v1/watchlist` | Watchlist entries, filterable by `origin` and `active` |
| `POST /v1/watchlist` | Track a wallet (as a seed) |
| `DELETE /v1/watchlist/{address}` | Stop tracking a wallet |
| `GET /v1/wallets/{address}` | Wallet profile: kind, entity label, tracking status, funder, community, tags, cluster and a feature summary |
| `GET /v1/wallets/{address}/features` | Feature snapshots over time |
| `GET /v1/wallets/{address}/transfers` | Transfers, newest first |
| `GET /v1/wallets/{address}/trades` | DEX trades signed by the wallet |
| `GET /v1/wallets/{address}/timeline` | Activity per `day`, `week` or `month` |
| `GET /v1/wallets/{address}/heatmap` | Transfer counts by weekday and UTC hour |
| `GET /v1/wallets/{address}/neighbors` | Ego network: neighbours, edges, hub labels |
| `GET /v1/wallets/{address}/similar` | Wallets with the most similar behaviour |
| `GET /v1/clusters`, `GET /v1/clusters/points` | Clusters with their profiles, and 2D points for the map |
| `GET /v1/tags` | Wallet count per tag |
| `GET /v1/heatmaps/segments` | Feature heatmap per cluster or tag (`by=cluster\|tag`) |

## Development

```bash
make lint typecheck test            # ruff, mypy --strict, unit tests

# Integration tests drop and recreate the schema: use a separate database.
HEATMAP_TEST_DATABASE_URL=postgresql+psycopg://heatmap:heatmap@localhost:5432/heatmap_test \
  make test-integration

cd apps/web && npm run lint && npm run typecheck && npm run build

# After changing the API: regenerate the spec and the web client
uv run python -m heatmap_api.openapi apps/web/openapi.json && (cd apps/web && npm run gen:api)
```

The suite has 92 unit tests and 50 integration tests against PostgreSQL,
including the full demo pipeline, which checks that every bot rule fires on
the synthetic swaps.

For schema changes, edit the models in `packages/core/src/heatmap_core/db/models`,
then run `uv run alembic -c packages/core/alembic.ini revision --autogenerate -m "…"`.
`uv run alembic -c packages/core/alembic.ini check` confirms that models and
migrations match, and a test fails if they drift apart.

CI (`.github/workflows/ci.yml`) runs lint, type checks, unit and integration
tests, and the web build. It also checks that `openapi.json` and the
generated web types are up to date.

## Status and roadmap

**Paused (October 2026).** The pipeline runs end to end on Ethereum mainnet.

### Working

- DEX trade discovery on Ethereum (Uniswap v2/v3/v4, SushiSwap) with USD
  valuation, bot filtering and promotion of active human traders
- Vetting of automatically added wallets; incremental transfer sync with
  multi-key, multi-provider failover
- DefiLlama pricing, spam detection, funding sources
- Interaction graph, neighbour expansion, communities, ego networks
- Behaviour features, tags, clusters, anomaly scores, drift
- HTTP API and web app (Overview, Discover, Watchlist, Wallet, Clusters),
  with a static demo mode

### Next

- **Validation**: a hand-labelled sample of mainnet wallets to measure the
  precision of the bot filter and the tags
- **ENS and identity enrichment**: names, avatars and text records for
  tracked wallets
- **Segments and audience export**: saved wallet groups, exported as CSV or
  through the API, for marketing tools
- **Coverage**: Curve, Balancer and other DEX venues; L2 chains such as Base
  and Arbitrum
- **API for the UI**: trader detail (`GET /v1/traders/{address}`), a
  discovery summary, cluster members, CSV export
- **Contract wallets**: Safes and smart accounts are rejected by vetting
  today; recognise them instead
- **Continuous operation**: run Dagster so discovery keeps pace with the chain

### Known limits

- The first sync of a wallet fetches its whole history. Vetting keeps out
  wallets that sent many transactions, but a wallet that mostly receives (for
  example a spam-airdrop magnet) can still be large.
- Funding source, degree and similarity features only see transfers that
  involve tracked wallets; they improve as the watchlist grows.
- The mass-airdrop spam rule counts recipients stored in the database, so it
  fires only when several tracked wallets receive the same drop.
- Hub and token seed lists are small starting sets. Extend the CSVs or import
  label lists; vetting catches many unlabelled exchange wallets by their
  transaction count.
- Prices are daily. A failed price lookup is retried on every normalize run;
  a day with no price is stored as NULL and not requested again.
- Hour-of-day features are in UTC.
