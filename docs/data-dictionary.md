# Data dictionary

All addresses are stored lowercase. Every table is keyed by `chain_id`.
`NATIVE_TOKEN` (`0xeeee…eeee`) stands for the chain's native asset.

## Tracking

| Table | Key | Purpose |
|---|---|---|
| `watchlist` | chain, address | Wallets synced on every run. `origin` = `seed` or `neighbour`; `hop`, `via_address` record how a neighbour was found; `active` toggles tracking. |
| `sync_cursors` | chain, address | Last fully ingested block, last sync time and last error. |
| `wallets` | chain, address | Every address seen: `kind` (eoa/contract/unknown), first/last seen, `funded_by` (sender of the first inbound native transfer, tracked wallets only). |
| `entity_labels` | chain, address | Known entities. `is_hub` addresses are never expanded. `source = 'seed_file'` rows are refreshed from CSV; other sources are left alone. |
| `provider_key_usage` | provider, key, day | Requests, rate-limit hits and errors per key per UTC day. |

## Transfers

| Table | Key | Purpose |
|---|---|---|
| `transfers` | id; unique (chain, uid) | One value movement. `uid` is a hash of on-chain facts (tx, category, parties, token, token id, amount) plus an ordinal, so different providers produce the same id. `amount` is decimal-adjusted, `amount_usd` priced at the daily close, `is_spam`/`spam_reason` from the spam rules, `normalized_at` set by the normalise stage. |
| `tokens` | chain, address | `standard`, symbol, name, decimals, `category` (native, stablecoin, wrapped, liquid_staking, defi, meme, nft, other), `is_verified`, `is_spam`, `price_id`. |
| `token_prices` | chain, token, day | Cached daily USD prices. |

Spam reasons: `spam_token`, `zero_value`, `lookalike_address`, `mass_airdrop`;
token-level `non_ascii_symbol`, `promo_text`, `impersonates:<SYMBOL>`.

## Graph

| Table | Key | Purpose |
|---|---|---|
| `edges` | chain, src, dst | Directed aggregate of non-spam transfers: count, distinct tokens, USD value, first/last seen. Rebuilt by the graph stage. |
| `wallet_communities` | chain, address | Louvain community on the hub-free undirected graph (largest community = 0). |

## Behaviour

`wallet_features` — key (chain, address, window, snapshot_at); `features` is JSONB,
`feature_version` names the registry version (currently `f1`).

| Group | Features |
|---|---|
| activity | `transfer_count`, `tx_count`, `active_days`, `lifespan_days`, `days_since_last`, `tx_per_active_day`, `out_share`, `median_gap_hours`, `gap_regularity` (share of gaps within 10% of the median), `burstiness` (−1 periodic … 1 bursty) |
| value | `volume_usd`, `inflow_usd`, `outflow_usd`, `netflow_usd`, `median_transfer_usd`, `max_transfer_usd`, `priced_share` |
| asset mix | `share_<token category>`, `distinct_tokens`, `token_entropy`, `nft_collections` |
| timing (UTC) | `hour_hist[24]`, `weekday_hist[7]` (Mon first), `night_share` (00–06), `weekend_share`, `hour_entropy` |
| services | `share_cex`, `share_dex_router`, `share_bridge`, `share_nft_marketplace`, `share_lending`, `share_mixer`, `contract_interactions`, `distinct_contracts` |
| neighbourhood | `degree`, `in_degree`, `out_degree`, `hub_share`, `tracked_neighbours`, `counterparty_entropy`, `top_counterparty_share`, `funded_by`, `funder_cluster_size` (tracked wallets with the same non-hub funder), `community_id`, `max_counterparty_jaccard`, `most_similar_wallet`, `wallets_sharing_counterparties`, `co_timed_wallets` (tracked wallets hitting the same non-hub counterparty in the same time bucket), `neighbour_mean_*` |

## Model outputs

`wallet_labels` — one row per (wallet, kind, label) per snapshot and `model_version`.

| kind | labels | score | details |
|---|---|---|---|
| `tag` | stablecoin_heavy, nft_trader, meme_trader, liquid_staker, dex_trader, cex_user, bridge_user, lending_user, whale, bot_like, dormant, new_wallet, distributor, collector, sybil_suspect, mixer_exposure | strength 0–1; `reason` explains it | — |
| `cluster` | `cluster_<n>` or `noise` | HDBSCAN membership probability; `reason` = cluster profile | `x`, `y` (PCA), `cluster_id` |
| `anomaly` | `outlier` / `inlier` | isolation-forest score (higher = stranger); `reason` = top drivers | — |
| `drift` | `behaviour_changed` / `stable` | RMS z-score change vs previous snapshot; `reason` = top changes | `previous_snapshot` |
