"""Run every model on a feature snapshot and store the labels."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import Engine, delete, select
from sqlalchemy.dialects.postgresql import insert

from heatmap_core.config import Chain, Settings
from heatmap_core.db.models import WalletFeatureSnapshot, WalletLabel
from heatmap_core.db.session import session_scope
from heatmap_core.logging import get_logger
from heatmap_core.models.anomaly import score_anomalies
from heatmap_core.models.clustering import NOISE, cluster_wallets
from heatmap_core.models.drift import detect_drift
from heatmap_core.models.matrix import build_matrix
from heatmap_core.models.tags import tag_wallet
from heatmap_core.primitives import LabelKind

log = get_logger(__name__)


@dataclass
class ModelRunResult:
    snapshot_at: datetime | None
    tags: int = 0
    clusters: int = 0
    anomalies: int = 0
    drifted: int = 0
    skipped: bool = False


def load_snapshot(
    engine: Engine, chain_id: int, window: str, snapshot_at: datetime
) -> dict[str, dict[str, Any]]:
    with session_scope(engine) as session:
        rows = session.execute(
            select(WalletFeatureSnapshot.address, WalletFeatureSnapshot.features).where(
                WalletFeatureSnapshot.chain_id == chain_id,
                WalletFeatureSnapshot.window == window,
                WalletFeatureSnapshot.snapshot_at == snapshot_at,
            )
        )
        return {address: features for address, features in rows}


def _snapshots(engine: Engine, chain_id: int, window: str) -> list[datetime]:
    with session_scope(engine) as session:
        return list(
            session.scalars(
                select(WalletFeatureSnapshot.snapshot_at)
                .where(
                    WalletFeatureSnapshot.chain_id == chain_id,
                    WalletFeatureSnapshot.window == window,
                )
                .distinct()
                .order_by(WalletFeatureSnapshot.snapshot_at.desc())
            )
        )


def run_models(
    engine: Engine, chain: Chain, settings: Settings, *, snapshot_at: datetime | None = None
) -> ModelRunResult:
    cfg = settings.models
    chain_id = chain.chain_id
    if snapshot_at is None:
        available = _snapshots(engine, chain_id, cfg.window)
        snapshot_at = available[0] if available else None
    result = ModelRunResult(snapshot_at=snapshot_at)
    if snapshot_at is None:
        return result

    current = load_snapshot(engine, chain_id, cfg.window, snapshot_at)
    addresses = sorted(current)
    labels: list[dict[str, Any]] = []

    def add(
        address: str,
        kind: LabelKind,
        label: str,
        score: float | None,
        reason: str | None,
        window: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        labels.append(
            {
                "chain_id": chain_id,
                "address": address,
                "kind": kind.value,
                "label": label,
                "score": score,
                "reason": reason,
                "window": window,
                "snapshot_at": snapshot_at,
                "model_version": cfg.version,
                "details": details,
            }
        )

    for address in addresses:
        for name, score, reason in tag_wallet(current[address]):
            add(address, LabelKind.TAG, name, score, reason, cfg.window)
            result.tags += 1

    matrix = build_matrix(addresses, [current[a] for a in addresses])
    clusters = cluster_wallets(matrix, cfg.min_cluster_size)
    result.clusters = len(clusters.profiles)
    for c in clusters.assignments:
        name = "noise" if c.cluster == NOISE else f"cluster_{c.cluster}"
        profile = clusters.profiles.get(c.cluster, [])
        add(
            c.address,
            LabelKind.CLUSTER,
            name,
            round(c.probability, 4),
            ", ".join(profile) or None,
            cfg.window,
            {"x": round(c.x, 5), "y": round(c.y, 5), "cluster_id": c.cluster},
        )

    for a in score_anomalies(matrix, cfg.anomaly_contamination):
        add(
            a.address,
            LabelKind.ANOMALY,
            "outlier" if a.is_anomaly else "inlier",
            a.score,
            ", ".join(a.drivers),
            cfg.window,
        )
        result.anomalies += int(a.is_anomaly)

    drift_snapshots = [
        s for s in _snapshots(engine, chain_id, cfg.drift_window) if s <= snapshot_at
    ]
    if len(drift_snapshots) >= 2:
        latest, previous = drift_snapshots[0], drift_snapshots[1]
        drifts = detect_drift(
            load_snapshot(engine, chain_id, cfg.drift_window, previous),
            load_snapshot(engine, chain_id, cfg.drift_window, latest),
            cfg.drift_threshold,
        )
        for d in drifts:
            add(
                d.address,
                LabelKind.DRIFT,
                "behaviour_changed" if d.changed else "stable",
                d.distance,
                ", ".join(d.top_changes) or None,
                cfg.drift_window,
                {"previous_snapshot": previous.isoformat()},
            )
            result.drifted += int(d.changed)

    with session_scope(engine) as session:
        session.execute(
            delete(WalletLabel).where(
                WalletLabel.chain_id == chain_id,
                WalletLabel.snapshot_at == snapshot_at,
                WalletLabel.model_version == cfg.version,
            )
        )
        for start in range(0, len(labels), 2000):
            session.execute(insert(WalletLabel).values(labels[start : start + 2000]))

    log.info("models.done", chain=chain.name, **{k: str(v) for k, v in result.__dict__.items()})
    return result
