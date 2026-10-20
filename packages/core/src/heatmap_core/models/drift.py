"""Behaviour drift: how far a wallet moved between two consecutive snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from heatmap_core.models.matrix import build_matrix


@dataclass
class Drift:
    address: str
    distance: float
    changed: bool
    top_changes: list[str]


def detect_drift(
    previous: dict[str, dict[str, Any]],
    current: dict[str, dict[str, Any]],
    threshold: float,
) -> list[Drift]:
    """Compare wallets present in both snapshots in a shared standardised space.

    The distance is the RMS of per-feature z-score changes, so ``threshold=3``
    means "moved three standard deviations on a typical feature".
    """
    common = sorted(previous.keys() & current.keys())
    if len(common) < 2:
        return []
    rows = [previous[a] for a in common] + [current[a] for a in common]
    matrix = build_matrix(common + common, rows)
    n = len(common)
    before, after = matrix.scaled[:n], matrix.scaled[n:]
    delta = after - before
    distances = np.sqrt((delta**2).mean(axis=1))
    results = []
    for i, address in enumerate(common):
        order = np.argsort(-np.abs(delta[i]))[:3]
        changes = [
            f"{matrix.columns[j]} {'up' if delta[i, j] > 0 else 'down'}"
            for j in order
            if delta[i, j] != 0
        ]
        results.append(
            Drift(address, round(float(distances[i]), 4), bool(distances[i] >= threshold), changes)
        )
    return results
