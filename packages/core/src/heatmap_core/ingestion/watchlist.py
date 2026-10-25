"""Watchlist management."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from heatmap_core.db.models import SyncCursor, WatchlistEntry
from heatmap_core.primitives import WatchOrigin, normalize_address


def add_seed(
    session: Session, chain_id: int, address: str, *, priority: int = 100, note: str | None = None
) -> WatchlistEntry:
    """Track a wallet as a seed. Promotes an existing neighbour entry to a seed."""
    address = normalize_address(address)
    stmt = insert(WatchlistEntry).values(
        chain_id=chain_id,
        address=address,
        origin=WatchOrigin.SEED,
        hop=0,
        via_address=None,
        priority=priority,
        active=True,
        note=note,
    )
    session.execute(
        stmt.on_conflict_do_update(
            index_elements=["chain_id", "address"],
            set_={
                "origin": WatchOrigin.SEED,
                "hop": 0,
                "via_address": None,
                "priority": priority,
                "active": True,
                "note": note,
            },
        )
    )
    entry = session.get(WatchlistEntry, (chain_id, address), populate_existing=True)
    assert entry is not None
    return entry


def deactivate(session: Session, chain_id: int, address: str) -> bool:
    entry = session.get(WatchlistEntry, (chain_id, normalize_address(address)))
    if entry is None:
        return False
    entry.active = False
    return True


def active_addresses(session: Session, chain_id: int, limit: int | None = None) -> list[str]:
    query = (
        select(WatchlistEntry.address)
        .where(WatchlistEntry.chain_id == chain_id, WatchlistEntry.active.is_(True))
        .order_by(WatchlistEntry.priority, WatchlistEntry.hop, WatchlistEntry.address)
    )
    if limit is not None:
        query = query.limit(limit)
    return list(session.scalars(query))


def unsynced_addresses(session: Session, chain_id: int) -> list[str]:
    """Active wallets that have never been synced (no cursor yet)."""
    query = (
        select(WatchlistEntry.address)
        .outerjoin(
            SyncCursor,
            (SyncCursor.chain_id == WatchlistEntry.chain_id)
            & (SyncCursor.address == WatchlistEntry.address),
        )
        .where(
            WatchlistEntry.chain_id == chain_id,
            WatchlistEntry.active.is_(True),
            SyncCursor.address.is_(None),
        )
        .order_by(WatchlistEntry.priority, WatchlistEntry.hop, WatchlistEntry.address)
    )
    return list(session.scalars(query))
