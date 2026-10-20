"""Turn feature snapshots into a numeric matrix for unsupervised models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from sklearn.preprocessing import StandardScaler

# Heavy-tailed counts and amounts are log-scaled before standardising.
LOG_FEATURES = {
    "transfer_count",
    "tx_count",
    "active_days",
    "lifespan_days",
    "days_since_last",
    "tx_per_active_day",
    "median_gap_hours",
    "volume_usd",
    "inflow_usd",
    "outflow_usd",
    "median_transfer_usd",
    "max_transfer_usd",
    "distinct_tokens",
    "nft_collections",
    "contract_interactions",
    "distinct_contracts",
    "degree",
    "in_degree",
    "out_degree",
    "tracked_neighbours",
    "funder_cluster_size",
    "co_timed_wallets",
    "wallets_sharing_counterparties",
}
# Identifiers and derived duplicates that should not drive similarity.
EXCLUDED = {"community_id", "netflow_usd", "funded_by", "most_similar_wallet"}


@dataclass
class FeatureMatrix:
    addresses: list[str]
    columns: list[str]
    raw: np.ndarray
    scaled: np.ndarray


def numeric_columns(rows: list[dict[str, Any]]) -> list[str]:
    columns: set[str] = set()
    for row in rows:
        for key, value in row.items():
            if isinstance(value, int | float) and not isinstance(value, bool):
                columns.add(key)
    return sorted(c for c in columns if c not in EXCLUDED and not c.startswith("neighbour_mean"))


def build_matrix(addresses: list[str], rows: list[dict[str, Any]]) -> FeatureMatrix:
    columns = numeric_columns(rows)
    raw = np.array([[_num(row.get(c)) for c in columns] for row in rows], dtype=float).reshape(
        len(rows), len(columns)
    )
    transformed = raw.copy()
    for idx, column in enumerate(columns):
        if column in LOG_FEATURES:
            transformed[:, idx] = np.sign(raw[:, idx]) * np.log1p(np.abs(raw[:, idx]))
    scaled = StandardScaler().fit_transform(transformed) if len(rows) else transformed
    return FeatureMatrix(addresses, columns, raw, np.nan_to_num(scaled))


def _num(value: Any) -> float:
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    return 0.0


def describe_group(matrix: FeatureMatrix, mask: np.ndarray, top: int = 3) -> list[str]:
    """Features where the group's mean z-score is most extreme, e.g. ``high share_cex``."""
    if not mask.any():
        return []
    means = matrix.scaled[mask].mean(axis=0)
    order = np.argsort(-np.abs(means))[:top]
    return [f"{'high' if means[i] > 0 else 'low'} {matrix.columns[i]}" for i in order]
