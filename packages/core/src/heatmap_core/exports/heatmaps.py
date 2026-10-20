"""Heatmap matrices: wallet activity by hour/weekday and segment behaviour profiles."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from heatmap_core.db.models import WalletFeatureSnapshot, WalletLabel
from heatmap_core.features.protocol import TRACKED_ENTITIES
from heatmap_core.primitives import LabelKind, TokenCategory

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
HOURS = [f"{h:02d}" for h in range(24)]


@dataclass
class Heatmap:
    rows: list[str]
    columns: list[str]
    values: list[list[float]]
    meta: dict[str, Any]


ACTIVITY_SQL = text(
    """
    SELECT (EXTRACT(ISODOW FROM block_time AT TIME ZONE 'UTC')::int - 1) AS weekday,
           EXTRACT(HOUR FROM block_time AT TIME ZONE 'UTC')::int AS hour,
           COUNT(*) AS n
    FROM transfers
    WHERE chain_id = :chain_id AND NOT is_spam AND block_time >= :since
      AND (from_address = :address OR to_address = :address)
    GROUP BY 1, 2
    """
)


def wallet_activity_heatmap(
    session: Session, chain_id: int, address: str, *, days: int = 365
) -> Heatmap:
    """Transfer counts by weekday (rows) and UTC hour (columns)."""
    values = [[0.0] * 24 for _ in range(7)]
    since = datetime.now(UTC) - timedelta(days=days)
    total = 0
    for weekday, hour, n in session.execute(
        ACTIVITY_SQL, {"chain_id": chain_id, "address": address, "since": since}
    ):
        values[weekday][hour] = float(n)
        total += int(n)
    return Heatmap(WEEKDAYS, HOURS, values, {"days": days, "total": total, "timezone": "UTC"})


SEGMENT_COLUMNS = [f"share_{c.value}" for c in TokenCategory] + [
    f"share_{e.value}" for e in TRACKED_ENTITIES
]


def segment_heatmap(
    session: Session, chain_id: int, *, by: str = "cluster", window: str = "all"
) -> Heatmap:
    """Mean asset/service shares per segment (cluster or tag) for the latest model run."""
    if by not in {"cluster", "tag"}:
        raise ValueError("by must be 'cluster' or 'tag'")
    snapshot_at = session.scalar(
        select(func.max(WalletLabel.snapshot_at)).where(WalletLabel.chain_id == chain_id)
    )
    if snapshot_at is None:
        return Heatmap([], SEGMENT_COLUMNS, [], {"by": by, "window": window})
    kind = LabelKind.CLUSTER if by == "cluster" else LabelKind.TAG
    rows = session.execute(
        select(WalletLabel.label, WalletFeatureSnapshot.features)
        .join(
            WalletFeatureSnapshot,
            (WalletFeatureSnapshot.chain_id == WalletLabel.chain_id)
            & (WalletFeatureSnapshot.address == WalletLabel.address)
            & (WalletFeatureSnapshot.snapshot_at == WalletLabel.snapshot_at),
        )
        .where(
            WalletLabel.chain_id == chain_id,
            WalletLabel.snapshot_at == snapshot_at,
            WalletLabel.kind == kind,
            WalletFeatureSnapshot.window == window,
        )
    )
    sums: dict[str, list[float]] = {}
    counts: dict[str, int] = {}
    for label, features in rows:
        acc = sums.setdefault(label, [0.0] * len(SEGMENT_COLUMNS))
        for i, column in enumerate(SEGMENT_COLUMNS):
            value = features.get(column)
            acc[i] += float(value) if isinstance(value, int | float) else 0.0
        counts[label] = counts.get(label, 0) + 1
    segments = sorted(sums, key=lambda s: (-counts[s], s))
    return Heatmap(
        rows=segments,
        columns=SEGMENT_COLUMNS,
        values=[[round(v / counts[s], 4) for v in sums[s]] for s in segments],
        meta={
            "by": by,
            "window": window,
            "snapshot_at": snapshot_at.isoformat(),
            "sizes": {s: counts[s] for s in segments},
        },
    )
