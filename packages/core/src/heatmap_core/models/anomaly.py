"""Isolation-forest anomaly scores with the features that make each outlier unusual."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sklearn.ensemble import IsolationForest

from heatmap_core.models.matrix import FeatureMatrix

MIN_WALLETS = 20


@dataclass
class AnomalyScore:
    address: str
    score: float  # higher = more unusual, roughly in [0, 1]
    is_anomaly: bool
    drivers: list[str]


def score_anomalies(matrix: FeatureMatrix, contamination: float) -> list[AnomalyScore]:
    n = len(matrix.addresses)
    if n < MIN_WALLETS:
        return []
    model = IsolationForest(contamination=contamination, random_state=42)
    flags = model.fit_predict(matrix.scaled) == -1
    scores = -model.score_samples(matrix.scaled)
    results = []
    for i in range(n):
        top = np.argsort(-np.abs(matrix.scaled[i]))[:3]
        drivers = [
            f"{matrix.columns[j]} {'high' if matrix.scaled[i, j] > 0 else 'low'}" for j in top
        ]
        results.append(
            AnomalyScore(matrix.addresses[i], round(float(scores[i]), 4), bool(flags[i]), drivers)
        )
    return results
