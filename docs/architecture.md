# Architecture

```
            ┌──────────── config/default.yaml + HEATMAP_* env ────────────┐
            ▼                                                             ▼
  Alchemy keys ─┐                                                  apps/web (Next.js)
  Etherscan keys┼─▶ ProviderRouter ─▶ ingestion ─▶ transfers ─┐          ▲
  (more…)      ─┘   (rate limit,       (cursors,    tokens     │          │
                     quota, failover)   reorg)                 ▼          │
                                         normalize: pricing, spam, labels │
                                                   │                      │
                                         graph: edges ─▶ neighbour expansion ─▶ watchlist
                                                   │
                                         features (per wallet × window × snapshot)
                                                   │
                                         models: tags, clusters, anomaly, drift
                                                   │
                                         exports: heatmaps, read models ─▶ apps/api (FastAPI /v1)
```

All stages are Dagster assets in `pipelines/`; each stage's logic lives in
`packages/core` so it can be tested without Dagster.

Scheduling: `discovery_job` scans DEX trades on `discovery_cron` and promotes
traders to the watchlist; `sync_job` (sync + normalize) runs on `sync_cron`, and the watchlist
sensor runs it for never-synced wallets only; `expansion_job` runs the graph
stage; `features_job` computes features and then models, so labels always use
the snapshot just written. Every stage holds a PostgreSQL advisory lock per
chain (features and models share one), and a run that finds it taken is
skipped rather than repeated.

## Stages

| Stage | Module | Reads | Writes |
|---|---|---|---|
| Discover | `dex` | chain logs and blocks, `dex_pools`, `entity_labels` | `dex_trades`, `dex_pools`, `tokens`, `dex_traders`, `watchlist` (traders) |
| Track | `ingestion` | `watchlist`, `sync_cursors` | `transfers`, `tokens`, `wallets`, `watchlist` (vetting) |
| Normalize | `normalize`, `entities` | `transfers`, `tokens` | `transfers.amount_usd`, `transfers.is_spam`, `entity_labels` |
| Graph | `graph` | `transfers` | `edges`, `watchlist` (neighbours), `wallet_communities` |
| Behaviour | `features` | `transfers`, `edges` | `wallet_features` |
| Models | `models` | `wallet_features` | `wallet_labels` |
| Serve | `exports`, `apps/api` | all | HTTP |

## Neighbour expansion rules
1. Start from active watchlist wallets below `expansion.max_hops` (seeds and
   promoted traders are hop 0).
2. Rank counterparties by interaction count and USD flow inside
   `expansion.window_days`; keep the top `expansion.top_n_per_wallet` with at
   least `expansion.min_interactions`.
3. Never expand **hubs**: labelled exchanges, routers, bridges, token contracts,
   DEX pools, the null address, or any address with more than
   `expansion.hub_degree_threshold` counterparties. Hubs remain in the graph as
   labelled nodes, but are left out of communities.
4. Skip counterparties known to be contracts, and ignore spam transfers.
5. Stop at `expansion.max_hops` and `expansion.max_total_neighbours` (active
   neighbours).
6. Each neighbour records `hop` and `via_address`, so provenance is traceable.

## Vetting automatic wallets
Promoted traders and neighbours are added without a person looking at them.
Before its first sync, the sync stage checks each one once with `eth_getCode`
and `eth_getTransactionCount` (`ingestion/vetting.py`):

- a **contract** (pool, vault, router…) is not a person;
- a wallet that **sent more than `tracking.max_sent_txs` transactions** is an
  exchange, payout service or bot, and can hold millions of transfers.

Such a wallet is deactivated with the reason appended to its watchlist note,
and keeps its place on the watchlist so it is never added again; the next
expansion or promotion run fills its slot with the next candidate. The kind
and count are stored in `wallets.kind` and `wallets.sent_txs`. EIP-7702
delegated accounts (code `0xef0100` + delegate) are EOAs. Wallets added by
hand are never vetted, and a wallet still unvetted (provider outage) is not
synced until a later run vets it.

## Provider routing
`ProviderRouter` holds a `KeyPool` per provider. Each key has a token-bucket
rate limiter (`rps`), an optional `daily_quota`, and a cooldown. A request goes
to the highest-priority provider that has a usable key. On `RateLimitedError`
or `QuotaExceededError` that key is benched for `cooldown_s` (quota: until the
next UTC day) and the request moves on to the next key or provider. Transient
errors are retried with exponential backoff. If no key is usable,
`AllProvidersExhaustedError` is raised. Daily usage is persisted in
`provider_key_usage`.
