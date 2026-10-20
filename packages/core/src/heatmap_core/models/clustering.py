"""Behaviour clusters (HDBSCAN) with a 2-D projection for display."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sklearn.cluster import HDBSCAN
from sklearn.decomposition import PCA

from heatmap_core.models.matrix import FeatureMatrix, describe_group

NOISE = -1


@dataclass
class ClusterAssignment:
    address: str
    cluster: int
    probability: float
    x: float
    y: float


@dataclass
class ClusterResult:
    assignments: list[ClusterAssignment]
    profiles: dict[int, list[str]]


def cluster_wallets(matrix: FeatureMatrix, min_cluster_size: int) -> ClusterResult:
    n = len(matrix.addresses)
    if n == 0:
        return ClusterResult([], {})
    if n < 2 * min_cluster_size:
        labels = np.zeros(n, dtype=int)
        probabilities = np.ones(n)
    else:
        model = HDBSCAN(min_cluster_size=min_cluster_size, copy=True)
        labels = model.fit_predict(matrix.scaled)
        probabilities = model.probabilities_

    if n >= 2 and matrix.scaled.shape[1] >= 2:
        coords = PCA(n_components=2, random_state=42).fit_transform(matrix.scaled)
    else:
        coords = np.zeros((n, 2))

    profiles = {
        int(label): describe_group(matrix, labels == label)
        for label in sorted(set(labels.tolist()))
        if label != NOISE
    }
    assignments = [
        ClusterAssignment(
            address=matrix.addresses[i],
            cluster=int(labels[i]),
            probability=float(probabilities[i]),
            x=float(coords[i, 0]),
            y=float(coords[i, 1]),
        )
        for i in range(n)
    ]
    return ClusterResult(assignments, profiles)
