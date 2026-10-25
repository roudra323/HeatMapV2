# HeatMap

**Find the wallets behind DEX trades, map who they deal with, and turn them into audiences.**

HeatMap reads every Uniswap (v2, v3, v4) and SushiSwap swap on Ethereum,
attributes it to the wallet that signed it, filters out bots, and starts
tracking the real traders. From each tracked wallet it maps the neighbouring
wallets it transacts with, builds behaviour profiles over time, and groups
wallets into explainable tags and clusters that a marketer can target.

> **Status: paused (October 2026).** The pipeline runs end to end on Ethereum
> mainnet. ENS enrichment and audience export are next; see
> [Status and roadmap](#status-and-roadmap).

## How it works

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

Every stage reads its inputs from PostgreSQL and writes its results back, so
stages run independently, from the CLI or on Dagster schedules. Each stage
holds a per-chain database lock, so overlapping runs skip instead of doing the
work twice.

| Stage | What it does | CLI | Dagster |
|---|---|---|---|
| reference | Loads seed labels (exchanges, routers, bridges…), verified tokens and DEX factories | `heatmap run reference` | `reference_data` asset |
| discovery | Scans new blocks for swaps, values them in USD, scores traders over 30 days, filters bots, promotes the best to the watchlist | `heatmap run discovery` | `discovery_job`, every 10 min |
| sync | Vets automatically added wallets, then pulls new transfers for every active watchlist wallet | `heatmap run sync [--only-new]` | `sync_job`, hourly; a sensor syncs new wallets within a minute |
| normalize | Daily USD prices, spam flags, funding sources | `heatmap run normalize` | part of `sync_job` |
| graph | Rebuilds the interaction graph, adds neighbours, detects communities | `heatmap run graph` | `expansion_job`, every 6 h |
| features | Behaviour snapshot per wallet for 7d / 30d / 90d / all time | `heatmap run features` | `features_job`, daily |
| models | Tags, clusters (HDBSCAN), anomalies (Isolation Forest), drift between snapshots | `heatmap run models` | runs right after features |

### The rules that matter

- **Trader = transaction signer** (`tx.from`). The Swap event's own `sender`
  is usually a router.
- **Only verified pools count.** A known factory must confirm the pool
  (`entities/data/dex_factories_<chain>.csv`), or for v4 the pool key must
  hash to the emitted PoolId. Trades from other pools are stored but never
  scored.
- **Bots are filtered out** (`dex_traders.bot_reason`). A signer counts as a
  bot when it trades through settlement contracts (solvers), through private
  contracts or pools directly (MEV), or in circular arbitrage transactions. So
  does one that packs many swaps into a transaction (market makers) or trades
  more than `bot_tx_per_day` times a day.
- **Promotion ranks by activity, not size.** Candidates are ordered by active
  days, then tokens traded besides stablecoins (up to five), then volume.
  Volume alone fills the watchlist with treasuries and stablecoin
  rebalancers. Per-run and total caps (`discovery.promote`) keep sync costs
  bounded.
- **Automatic wallets are vetted before their first sync.** Promoted traders
  and neighbours are checked once with `eth_getCode` and
  `eth_getTransactionCount`. Contracts (pools, vaults, routers) are rejected.
  So are wallets that sent more than `tracking.max_sent_txs` transactions
  (exchanges, payout services, bots), because they can hold millions of
  transfers. A rejected wallet stays on the watchlist as inactive, with the
  reason in its note, and its slot goes to the next candidate. EIP-7702
  delegated accounts count as wallets. Wallets you add yourself are never
  vetted.
- **Neighbour expansion never crosses hubs.** Labelled entities, token
  contracts, DEX pools and addresses with more than
  `expansion.hub_degree_threshold` counterparties are hubs. They are never
  added as neighbours or expanded through, and known contracts are skipped
  too. Each tracked wallet contributes its top `expansion.top_n_per_wallet`
  counterparties, `max_hops` deep, up to `max_total_neighbours`. Every
  neighbour records `hop` and `via_address`.

More detail: [docs/architecture.md](docs/architecture.md) ·
[docs/data-dictionary.md](docs/data-dictionary.md) ·
[docs/adr/0001-stack.md](docs/adr/0001-stack.md)

## Quick start

Requirements: Python 3.12 with [uv](https://docs.astral.sh/uv/), Node 22
(20.9+ works), and PostgreSQL 16 (Docker Compose provides one).

```bash
git clone git@github.com:roudra323/HeatMapV2.git && cd HeatMapV2
cp .env.example .env                # add provider keys; .env is loaded from the working directory
make install                        # uv sync + npm ci for the web app
docker compose up -d postgres       # or point HEATMAP_DATABASE_URL at your own PostgreSQL
make migrate                        # create or upgrade the schema
```

**Without keys**, load a synthetic dataset and run every stage on it:

```bash
uv run heatmap demo
```

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

### Catching up after a break

Sync, normalize and the later stages resume where they stopped. Wallet sync
keeps a block cursor per wallet, and every stage is safe to re-run. Discovery
resumes from its own cursor, at most `discovery.max_blocks_per_run` blocks
(about 6 hours of chain) per run, so a long break takes many runs to catch up.
Trader statistics only look at the last 30 days anyway. To restart discovery
from the chain head, delete its cursor; the next run backfills
`discovery.backfill_blocks` from the head:

```sql
DELETE FROM dex_cursors WHERE chain_id = 1;
```

## Web app

| Page | What it shows |
|---|---|
| Overview `/` | The flow from DEX trades to audiences, the biggest traders right now, behaviour tags and what each segment moves and uses |
| Discover `/discover` | Traders found in DEX swaps: volume, activity, tokens, routes and bot verdicts; track any of them |
| Watchlist `/watchlist` | Tracked wallets by origin (seed, trader, neighbour) with sync status; add or untrack wallets |
| Wallet `/wallets/<address>` | Behaviour profile and what stands out, activity by weekday and hour, weekly timeline, neighbour graph, similar wallets, DEX trades and transfers |
| Clusters `/clusters` | A 2D behaviour map of all profiled wallets and what each cluster moves and uses |

The web app talks only to the API. Its typed client is generated from the
OpenAPI spec (see [Development](#development)).

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

## CLI

```bash
uv run heatmap watch add <address>… [--note TEXT] [--priority N]
uv run heatmap watch remove <address>…
uv run heatmap run <stage>|all [--only-new]      # stages listed above; --only-new is for sync
uv run heatmap labels import <file.csv|json> --source NAME [--category CATEGORY]
uv run heatmap demo
```

The chain is chosen before the command: `uv run heatmap --chain base run sync`
(default `ethereum`).

## Data sources and costs

| Source | Used for | Key |
|---|---|---|
| [Alchemy](https://www.alchemy.com/) | Swap logs and blocks (discovery), transfer history (`alchemy_getAssetTransfers`), contract reads through Multicall3, `eth_getCode`, transaction counts | Required for discovery (`ALCHEMY_KEY_*`) |
| [Etherscan](https://etherscan.io/apis) v2 | Fallback for transfer history, blocks, code and contract reads; cannot scan logs for discovery | Optional (`ETHERSCAN_KEY_*`) |
| [DefiLlama](https://defillama.com/docs/api) | Daily USD prices for any token by address | None |
| [CoinGecko](https://www.coingecko.com/en/api) | Alternative price source, only for tokens with a `price_id` | Optional (`COINGECKO_API_KEY`) |

- **Discovery** costs roughly 170k Alchemy compute units per day of chain:
  one `eth_getLogs` per 10 blocks (the free-tier limit,
  `discovery.logs_block_range`) plus one `eth_getBlockByNumber` per block to
  learn who signed each swap.
- **Vetting** costs two cheap calls per automatically added wallet, once.
- **Sync** cost grows with each wallet's history; the first sync of a wallet
  fetches it in full.

Multiple keys per provider are supported. Requests go to the highest-priority
provider with a usable key, round-robin across its keys. A key is benched on
rate limits, benched until the next UTC day on quota errors or when its
`daily_quota` is used up, and disabled on auth errors. Transient errors are
retried with backoff. When all keys are out, a run stops cleanly and resumes
from its cursors next time. Usage per key per day is stored in
`provider_key_usage`.

## Configuration

`config/default.yaml` is loaded first, then any files in `HEATMAP_CONFIG_FILES`
(comma separated, later wins), then `HEATMAP_*` environment variables (`__`
for nesting, e.g. `HEATMAP_SCHEDULES__SYNC_CRON`). Secrets never go in YAML:
each provider key names the environment variable that holds it.

| Section | What it controls |
|---|---|
| `providers` | Providers, priority, cooldowns and keys: each key's env var, `rps` and optional `daily_quota` |
| `chains` | Enabled chains, their providers, confirmations, reorg window, sync chunk size, `eth_getCode` budget for classifying counterparties, DEX contract addresses |
| `schedules` | Cron strings for discovery, sync, expansion and features; timezone; on/off |
| `discovery` | Trade scanning (backfill, blocks per run, log window), bot thresholds, promotion rules and caps |
| `tracking` | Vetting of automatically added wallets (`max_sent_txs`) |
| `expansion` | Hops, top-N per wallet, minimum interactions, look-back window, hub degree threshold, neighbour budget |
| `spam` | Spam rules: non-ASCII symbols, zero-value poisoning, airdrop threshold |
| `features` | Windows, minimum transfers, co-timing bucket size |
| `models` | Model window, drift window, cluster size, anomaly contamination, drift threshold |
| `pricing` | `defillama` (default; free, any token by address) or `coingecko` (only tokens with a `price_id`) |

### Entity labels

Neighbour expansion relies on knowing which addresses are exchanges, routers,
bridges and other hubs. The seed files in `packages/core/src/heatmap_core/entities/data/`
cover a few dozen. Import larger lists, either CSV with a header or a JSON
list of objects:

```bash
uv run heatmap labels import exchanges.csv --source eth-labels
uv run heatmap labels import routers.json --source my-list --category dex_router
```

Columns are matched loosely: `address`, `name`/`label`, `category`/`type`,
and optional `is_hub`. Free-text categories are mapped onto the built-in ones,
which decide whether the address is a hub. Re-importing a source updates its
rows. Seed-file labels and other sources are never overwritten.

### Adding a chain

```yaml
chains:
  base:
    chain_id: 8453
    providers: [alchemy, etherscan]
    alchemy_network: base-mainnet
    defillama_chain: base
    explorer_url: https://basescan.org
```

Add `labels_base.csv`, `tokens_base.csv` and `dex_factories_base.csv` next to
the Ethereum seed files. Dagster partitions, the API (`?chain=base`) and the
CLI (`heatmap --chain base …`) pick the chain up automatically.

## Repository layout

```
apps/api        FastAPI service (/v1, OpenAPI at /docs)
apps/web        Next.js 16 / React 19 / Tailwind 4 web app (typed API client)
packages/core   Domain library: config, db (SQLAlchemy + Alembic), providers,
                dex, ingestion, normalize, entities, graph, features, models,
                exports, pipeline, cli, demo
pipelines       Dagster assets, jobs, schedules and the new-wallet sensor
config          default.yaml (no secrets)
docs            Architecture, data dictionary, decision records
infra/docker    Dockerfiles; docker-compose.yml runs the whole stack
tests           Unit tests and PostgreSQL integration tests
```

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

For schema changes, edit the models in `packages/core/src/heatmap_core/db/models`,
then run `uv run alembic -c packages/core/alembic.ini revision --autogenerate -m "…"`.
`uv run alembic -c packages/core/alembic.ini check` confirms that models and
migrations match, and a test fails if they drift apart.

CI (`.github/workflows/ci.yml`) runs lint, type checks, unit and integration
tests, and the web build. It also checks that `openapi.json` and the
generated web types are up to date.

## Status and roadmap

### Working

- DEX trade discovery on Ethereum (Uniswap v2/v3/v4, SushiSwap) with USD
  valuation, bot filtering and promotion of active human traders
- Vetting of automatically added wallets; incremental transfer sync with
  multi-key, multi-provider failover
- DefiLlama pricing, spam detection, funding sources
- Interaction graph, neighbour expansion, communities, ego networks
- Behaviour features, tags, clusters, anomaly scores, drift
- HTTP API and web app (Overview, Discover, Watchlist, Wallet, Clusters)

### Next

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
