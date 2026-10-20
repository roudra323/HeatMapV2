from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import polars as pl
import pytest

from heatmap_core.features.context import SIDES_SCHEMA, WALLETS_SCHEMA, FeatureContext
from heatmap_core.features.registry import compute_all
from tests.support import addr

W1, W2, W3 = addr(1), addr(2), addr(3)
SHARED, OTHER, CEX = addr(0xA), addr(0xB), addr(0xC)
T0 = datetime(2026, 1, 5, 10, 0, tzinfo=UTC)  # a Monday
SNAPSHOT = datetime(2026, 1, 15, tzinfo=UTC)


def side(wallet: str, cp: str, minutes: int, **kw: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "wallet": wallet,
        "direction": "out",
        "counterparty": cp,
        "tx_hash": f"{wallet}-{minutes}",
        "block_time": T0 + timedelta(minutes=minutes),
        "category": "erc20",
        "token_address": addr(0x100),
        "token_category": "stablecoin",
        "amount_usd": 100.0,
        "is_zero": False,
        "cp_entity": None,
        "cp_is_hub": False,
        "cp_is_contract": False,
        "cp_tracked": False,
    }
    row.update(kw)
    return row


@pytest.fixture
def features() -> dict[str, dict[str, Any]]:
    sides = [
        # W1: 3 transfers to SHARED an hour apart, 1 inbound from CEX the next day
        side(W1, SHARED, 0),
        side(W1, SHARED, 60),
        side(W1, SHARED, 120),
        side(
            W1,
            CEX,
            24 * 60,
            direction="in",
            cp_entity="cex",
            cp_is_hub=True,
            amount_usd=1000.0,
            token_category="native",
            category="external",
            token_address=addr(0xEEE),
        ),
        # W2 hits SHARED in the same minute as W1 and also pays W1
        side(W2, SHARED, 0, tx_hash="w2-a"),
        side(W2, W1, 5, cp_tracked=True, amount_usd=None),
        # W3 only uses OTHER
        side(W3, OTHER, 0),
    ]
    wallets = [
        {"wallet": W1, "funded_by": CEX, "community_id": 0},
        {"wallet": W2, "funded_by": CEX, "community_id": 0},
        {"wallet": W3, "funded_by": None, "community_id": 1},
    ]
    ctx = FeatureContext(
        sides=pl.DataFrame(sides, schema=SIDES_SCHEMA),
        wallets=pl.DataFrame(wallets, schema=WALLETS_SCHEMA),
        snapshot_at=SNAPSHOT,
        window="all",
    )
    frame = compute_all(ctx)
    return {row["wallet"]: row for row in frame.iter_rows(named=True)}


def test_activity(features: dict[str, dict[str, Any]]) -> None:
    w1 = features[W1]
    assert w1["transfer_count"] == 4 and w1["tx_count"] == 4
    assert w1["active_days"] == 2
    assert w1["out_share"] == 0.75
    assert w1["lifespan_days"] == pytest.approx(1.0)
    assert w1["days_since_last"] == pytest.approx(8 + 14 / 24)  # last tx Jan 6 10:00
    assert w1["median_gap_hours"] == pytest.approx(1.0)


def test_value_and_mix(features: dict[str, dict[str, Any]]) -> None:
    w1 = features[W1]
    assert w1["volume_usd"] == 1300.0
    assert (w1["inflow_usd"], w1["outflow_usd"], w1["netflow_usd"]) == (1000.0, 300.0, 700.0)
    assert w1["share_stablecoin"] == 0.75 and w1["share_native"] == 0.25
    assert w1["distinct_tokens"] == 2
    assert features[W2]["priced_share"] == 0.5


def test_timing(features: dict[str, dict[str, Any]]) -> None:
    w1 = features[W1]
    assert len(w1["hour_hist"]) == 24 and sum(w1["hour_hist"]) == pytest.approx(1)
    assert w1["hour_hist"][10] == pytest.approx(0.5)
    assert w1["weekday_hist"][0] == 0.75 and w1["weekday_hist"][1] == 0.25
    assert w1["weekend_share"] == 0


def test_protocol_and_neighbourhood(features: dict[str, dict[str, Any]]) -> None:
    w1, w2, w3 = features[W1], features[W2], features[W3]
    assert w1["share_cex"] == 0.25
    assert w1["hub_share"] == 0.25
    assert (w1["degree"], w1["in_degree"], w1["out_degree"]) == (2, 1, 1)
    assert w1["top_counterparty_share"] == 0.75
    # W1 and W2 share a funder and the SHARED counterparty
    assert w1["funder_cluster_size"] == 2 and w3["funder_cluster_size"] == 0
    assert w2["most_similar_wallet"] == W1
    assert w2["max_counterparty_jaccard"] == pytest.approx(0.5)  # {SHARED} / {SHARED, W1}
    assert w1["co_timed_wallets"] == 1 and w3["co_timed_wallets"] == 0
    assert w2["tracked_neighbours"] == 1
    assert w2["neighbour_mean_transfer_count"] == 4
    assert w1["community_id"] == 0


def test_window_filter() -> None:
    ctx = FeatureContext(
        sides=pl.DataFrame(
            [side(W1, SHARED, 0), side(W1, SHARED, 60 * 24 * 9)], schema=SIDES_SCHEMA
        ),
        wallets=pl.DataFrame([], schema=WALLETS_SCHEMA),
        snapshot_at=SNAPSHOT,
        window="all",
    )
    assert ctx.for_window("7d").sides.height == 1
    assert ctx.for_window("all").sides.height == 2
