"""Community detection on the non-hub interaction graph."""

from __future__ import annotations

from datetime import UTC, datetime

import networkx as nx
from sqlalchemy import Engine, delete, select
from sqlalchemy.dialects.postgresql import insert

from heatmap_core.db.models import Edge, WalletCommunity
from heatmap_core.db.session import session_scope
from heatmap_core.entities.labels import hub_addresses

ALGORITHM = "louvain"


def build_graph(engine: Engine, chain_id: int, *, exclude_hubs: bool = True) -> nx.Graph:
    """Undirected graph weighted by transfer count.

    Hubs are left out so they do not merge everything into one community.
    """
    graph = nx.Graph()
    with session_scope(engine) as session:
        hubs = hub_addresses(session, chain_id) if exclude_hubs else set()
        for src, dst, count in session.execute(
            select(Edge.src, Edge.dst, Edge.tx_count).where(Edge.chain_id == chain_id)
        ):
            if src in hubs or dst in hubs:
                continue
            weight = graph[src][dst]["weight"] + count if graph.has_edge(src, dst) else count
            graph.add_edge(src, dst, weight=weight)
    return graph


def detect_communities(engine: Engine, chain_id: int, *, seed: int = 42) -> int:
    """Run Louvain and store one community id per address; returns the community count."""
    graph = build_graph(engine, chain_id)
    communities = (
        nx.community.louvain_communities(graph, weight="weight", seed=seed) if graph else []
    )
    # Largest community gets id 0 so ids are stable-ish across runs.
    communities = sorted(communities, key=lambda c: (-len(c), min(c)))
    now = datetime.now(UTC)
    rows = [
        {
            "chain_id": chain_id,
            "address": address,
            "community_id": idx,
            "algorithm": ALGORITHM,
            "computed_at": now,
        }
        for idx, members in enumerate(communities)
        for address in members
    ]
    with session_scope(engine) as session:
        session.execute(delete(WalletCommunity).where(WalletCommunity.chain_id == chain_id))
        for start in range(0, len(rows), 5000):
            session.execute(insert(WalletCommunity).values(rows[start : start + 5000]))
    return len(communities)
