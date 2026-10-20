"""Input shared by every feature group."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import polars as pl

# Columns of ``FeatureContext.sides``: one row per (tracked wallet, transfer side).
SIDES_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    "wallet": pl.String,
    "direction": pl.String,  # "in" | "out"
    "counterparty": pl.String,
    "tx_hash": pl.String,
    "block_time": pl.Datetime(time_zone="UTC"),
    "category": pl.String,
    "token_address": pl.String,
    "token_category": pl.String,
    "amount_usd": pl.Float64,
    "is_zero": pl.Boolean,
    "cp_entity": pl.String,  # entity category of the counterparty, if labelled
    "cp_is_hub": pl.Boolean,
    "cp_is_contract": pl.Boolean,
    "cp_tracked": pl.Boolean,
}

WALLETS_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    "wallet": pl.String,
    "funded_by": pl.String,
    "funder_is_hub": pl.Boolean,  # exchanges fund everyone; not evidence of common control
    "community_id": pl.Int64,
}


def window_start(window: str, snapshot_at: datetime) -> datetime | None:
    if window == "all":
        return None
    return snapshot_at - timedelta(days=int(window[:-1]))


@dataclass
class FeatureContext:
    sides: pl.DataFrame
    wallets: pl.DataFrame
    snapshot_at: datetime
    window: str
    co_timing_seconds: int = 120

    def for_window(self, window: str) -> FeatureContext:
        start = window_start(window, self.snapshot_at)
        sides = self.sides if start is None else self.sides.filter(pl.col("block_time") >= start)
        return FeatureContext(sides, self.wallets, self.snapshot_at, window, self.co_timing_seconds)
