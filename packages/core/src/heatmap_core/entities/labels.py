"""Known entities and verified tokens, seeded from versioned CSV files."""

from __future__ import annotations

import csv
from importlib import resources

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from heatmap_core.config import Chain
from heatmap_core.db.models import EntityLabel, Token
from heatmap_core.primitives import normalize_address


def _read_seed(filename: str) -> list[dict[str, str]]:
    path = resources.files("heatmap_core.entities") / "data" / filename
    if not path.is_file():
        return []
    with path.open() as handle:
        return list(csv.DictReader(handle))


def load_seed_labels(session: Session, chain: Chain) -> int:
    rows = [
        {
            "chain_id": chain.chain_id,
            "address": normalize_address(r["address"]),
            "name": r["name"],
            "category": r["category"],
            "is_hub": r["is_hub"].strip().lower() == "true",
            "source": "seed_file",
        }
        for r in _read_seed(f"labels_{chain.name}.csv")
    ]
    if not rows:
        return 0
    stmt = insert(EntityLabel).values(rows)
    session.execute(
        stmt.on_conflict_do_update(
            index_elements=["chain_id", "address"],
            set_={c: stmt.excluded[c] for c in ("name", "category", "is_hub", "source")},
            # Manual labels win over the seed file.
            where=EntityLabel.source == "seed_file",
        )
    )
    return len(rows)


def load_seed_tokens(session: Session, chain: Chain) -> int:
    rows = [
        {
            "chain_id": chain.chain_id,
            "address": normalize_address(r["address"]),
            "standard": r["standard"],
            "symbol": r["symbol"],
            "name": r["name"],
            "decimals": int(r["decimals"]),
            "category": r["category"],
            "price_id": r["price_id"] or None,
            "is_verified": True,
            "is_spam": False,
        }
        for r in _read_seed(f"tokens_{chain.name}.csv")
    ]
    if not rows:
        return 0
    stmt = insert(Token).values(rows)
    session.execute(
        stmt.on_conflict_do_update(
            index_elements=["chain_id", "address"],
            set_={
                c: stmt.excluded[c]
                for c in (
                    "standard",
                    "symbol",
                    "name",
                    "decimals",
                    "category",
                    "price_id",
                    "is_verified",
                    "is_spam",
                )
            },
        )
    )
    return len(rows)


def hub_addresses(session: Session, chain_id: int) -> set[str]:
    """Labelled hubs plus every known token contract."""
    hubs = set(
        session.scalars(
            select(EntityLabel.address).where(
                EntityLabel.chain_id == chain_id, EntityLabel.is_hub.is_(True)
            )
        )
    )
    hubs.update(session.scalars(select(Token.address).where(Token.chain_id == chain_id)))
    return hubs


def entity_labels(session: Session, chain_id: int) -> dict[str, EntityLabel]:
    return {
        label.address: label
        for label in session.scalars(select(EntityLabel).where(EntityLabel.chain_id == chain_id))
    }
