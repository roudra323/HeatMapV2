# Operating HeatMap

Reference for running the pipeline against a real chain: the CLI, provider
costs, configuration, entity labels, adding chains and catching up after a
break. The [README](../README.md) covers what HeatMap does and how to start it.

## CLI

```bash
uv run heatmap watch add <address>… [--note TEXT] [--priority N]
uv run heatmap watch remove <address>…
uv run heatmap run <stage>|all [--only-new]      # stages: reference, discovery, sync, normalize, graph, features, models
uv run heatmap labels import <file.csv|json> --source NAME [--category CATEGORY]
uv run heatmap demo                              # load the synthetic dataset and run every stage
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
| `api` | CORS origins, default and maximum page size |

## Entity labels

Neighbour expansion relies on knowing which addresses are exchanges, routers,
bridges and other hubs. The seed files in
`packages/core/src/heatmap_core/entities/data/` cover a few dozen. Import
larger lists, either CSV with a header or a JSON list of objects:

```bash
uv run heatmap labels import exchanges.csv --source eth-labels
uv run heatmap labels import routers.json --source my-list --category dex_router
```

Columns are matched loosely: `address`, `name`/`label`, `category`/`type`,
and optional `is_hub`. Free-text categories are mapped onto the built-in ones,
which decide whether the address is a hub. Re-importing a source updates its
rows. Seed-file labels and other sources are never overwritten.

## Adding a chain

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

## Catching up after a break

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
