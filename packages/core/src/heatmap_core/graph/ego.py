"""Ego networks: a wallet's neighbours with their labels and edge weights."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from heatmap_core.db.models import (
    Edge,
    EntityLabel,
    Token,
    Wallet,
    WalletCommunity,
    WatchlistEntry,
)


@dataclass
class EgoNode:
    address: str
    depth: int
    label: str | None = None
    category: str | None = None
    is_hub: bool = False
    tracked: bool = False
    hop: int | None = None
    kind: str | None = None
    community_id: int | None = None


@dataclass
class EgoEdge:
    src: str
    dst: str
    tx_count: int
    value_usd: Decimal | None
    first_seen_at: datetime
    last_seen_at: datetime


@dataclass
class EgoNetwork:
    center: str
    nodes: list[EgoNode] = field(default_factory=list)
    edges: list[EgoEdge] = field(default_factory=list)


def _top_counterparties(
    session: Session, chain_id: int, address: str, min_tx: int, limit: int
) -> tuple[list[str], list[Edge]]:
    edges = list(
        session.scalars(
            select(Edge).where(
                Edge.chain_id == chain_id, or_(Edge.src == address, Edge.dst == address)
            )
        )
    )
    weight: dict[str, int] = defaultdict(int)
    for e in edges:
        weight[e.dst if e.src == address else e.src] += e.tx_count
    ranked = sorted((a for a, w in weight.items() if w >= min_tx), key=lambda a: (-weight[a], a))[
        :limit
    ]
    keep = set(ranked)
    return ranked, [e for e in edges if (e.dst if e.src == address else e.src) in keep]


def ego_network(
    session: Session,
    chain_id: int,
    address: str,
    *,
    depth: int = 1,
    min_tx: int = 1,
    limit: int = 50,
) -> EgoNetwork:
    """Neighbours of ``address`` up to ``depth`` hops (hubs are shown but not expanded)."""
    hubs = set(
        session.scalars(
            select(EntityLabel.address).where(
                EntityLabel.chain_id == chain_id, EntityLabel.is_hub.is_(True)
            )
        )
    )
    depth_of: dict[str, int] = {address: 0}
    edges: dict[tuple[str, str], Edge] = {}
    frontier = [address]
    for level in range(1, depth + 1):
        next_frontier: list[str] = []
        for node in frontier:
            if node in hubs and node != address:
                continue
            neighbours, node_edges = _top_counterparties(session, chain_id, node, min_tx, limit)
            for e in node_edges:
                edges[(e.src, e.dst)] = e
            for n in neighbours:
                if n not in depth_of:
                    depth_of[n] = level
                    next_frontier.append(n)
        frontier = next_frontier

    addresses = list(depth_of)
    labels = {
        r.address: r
        for r in session.scalars(
            select(EntityLabel).where(
                EntityLabel.chain_id == chain_id, EntityLabel.address.in_(addresses)
            )
        )
    }
    tokens = {
        r.address: r
        for r in session.scalars(
            select(Token).where(Token.chain_id == chain_id, Token.address.in_(addresses))
        )
    }
    watched = {
        r.address: r
        for r in session.scalars(
            select(WatchlistEntry).where(
                WatchlistEntry.chain_id == chain_id, WatchlistEntry.address.in_(addresses)
            )
        )
    }
    kinds: dict[str, str] = {
        a: k
        for a, k in session.execute(
            select(Wallet.address, Wallet.kind).where(
                Wallet.chain_id == chain_id, Wallet.address.in_(addresses)
            )
        )
    }
    communities: dict[str, int] = {
        a: c
        for a, c in session.execute(
            select(WalletCommunity.address, WalletCommunity.community_id).where(
                WalletCommunity.chain_id == chain_id, WalletCommunity.address.in_(addresses)
            )
        )
    }

    network = EgoNetwork(center=address)
    for a in addresses:
        label = labels.get(a)
        token = tokens.get(a)
        entry = watched.get(a)
        network.nodes.append(
            EgoNode(
                address=a,
                depth=depth_of[a],
                label=label.name if label else (token.symbol if token else None),
                category=label.category if label else ("token" if token else None),
                is_hub=bool(label and label.is_hub) or token is not None,
                tracked=entry is not None and entry.active,
                hop=entry.hop if entry else None,
                kind=kinds.get(a),
                community_id=communities.get(a),
            )
        )
    network.edges = [
        EgoEdge(e.src, e.dst, e.tx_count, e.value_usd, e.first_seen_at, e.last_seen_at)
        for e in edges.values()
        if e.src in depth_of and e.dst in depth_of
    ]
    return network
