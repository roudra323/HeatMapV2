"""Directed, aggregated edges built from non-spam transfers."""

from __future__ import annotations

from sqlalchemy import Engine, text

from heatmap_core.db.session import session_scope

REBUILD_SQL = text(
    """
    INSERT INTO edges (
        chain_id, src, dst, tx_count, token_count, value_usd, first_seen_at, last_seen_at
    )
    SELECT
        chain_id,
        from_address,
        to_address,
        COUNT(*),
        COUNT(DISTINCT token_address),
        SUM(amount_usd),
        MIN(block_time),
        MAX(block_time)
    FROM transfers
    WHERE chain_id = :chain_id
      AND NOT is_spam
      AND normalized_at IS NOT NULL
      AND from_address <> to_address
    GROUP BY chain_id, from_address, to_address
    """
)


def rebuild_edges(engine: Engine, chain_id: int) -> int:
    """Recompute every edge for a chain in one transaction; returns the edge count."""
    with session_scope(engine) as session:
        session.execute(
            text("DELETE FROM edges WHERE chain_id = :chain_id"), {"chain_id": chain_id}
        )
        result = session.execute(REBUILD_SQL, {"chain_id": chain_id})
        return int(result.rowcount or 0)  # type: ignore[attr-defined]
