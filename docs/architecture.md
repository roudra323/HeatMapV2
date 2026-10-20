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

## Stages

| Stage | Module | Reads | Writes |
|---|---|---|---|
| Track | `ingestion` | `watchlist`, `sync_cursors` | `transfers`, `tokens`, `wallets` |
| Normalize | `normalize`, `entities` | `transfers`, `tokens` | `transfers.amount_usd`, `transfers.is_spam`, `entity_labels` |
| Graph | `graph` | `transfers` | `edges`, `watchlist` (neighbours), `wallet_communities` |
| Behaviour | `features` | `transfers`, `edges` | `wallet_features` |
| Models | `models` | `wallet_features` | `wallet_labels` |
| Serve | `exports`, `apps/api` | all | HTTP |

## Neighbour expansion rules
1. Start from seed wallets (`watchlist.origin = 'seed'`).
2. Rank counterparties by interaction count and USD flow inside
   `expansion.window_days`; keep the top `expansion.top_n_per_wallet` with at
   least `expansion.min_interactions`.
3. Never expand **hubs**: labelled exchanges, routers, bridges, token contracts,
   the null address, or any address with more than
   `expansion.hub_degree_threshold` counterparties. Hubs remain in the graph as
   labelled nodes.
4. Spam transfers are ignored.
5. Stop at `expansion.max_hops` and `expansion.max_total_neighbours`.
6. Each neighbour records `hop` and `via_address`, so provenance is traceable.

## Provider routing
`ProviderRouter` holds a `KeyPool` per provider. Each key has a token-bucket
rate limiter (`rps`), an optional `daily_quota`, and a cooldown. A request goes
to the highest-priority provider that has a usable key. On `RateLimitedError`
or `QuotaExceededError` that key is benched for `cooldown_s` (quota: until the
next UTC day) and the request moves on to the next key or provider. Transient
errors are retried with exponential backoff. If no key is usable,
`AllProvidersExhaustedError` is raised. Daily usage is persisted in
`provider_key_usage`.
