"""Known entities and verified tokens, seeded from versioned CSV files."""

from __future__ import annotations

import csv
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from heatmap_core.config import Chain
from heatmap_core.db.models import DexPool, EntityLabel, Token
from heatmap_core.primitives import EntityCategory, InvalidAddressError, normalize_address

SEED_SOURCE = "seed_file"
ADDRESS_LENGTH = 42

# Entities that interact with everyone: never expanded, never evidence of a link.
HUB_CATEGORIES = {
    EntityCategory.CEX,
    EntityCategory.DEX_ROUTER,
    EntityCategory.BRIDGE,
    EntityCategory.TOKEN,
    EntityCategory.NFT_MARKETPLACE,
    EntityCategory.LENDING,
    EntityCategory.MIXER,
    EntityCategory.PROTOCOL,
    EntityCategory.SYSTEM,
    EntityCategory.SETTLEMENT,
}

# Free-text categories and names from external lists, checked in order.
_CATEGORY_KEYWORDS: tuple[tuple[EntityCategory, tuple[str, ...]], ...] = (
    (EntityCategory.MIXER, ("mixer", "tornado")),
    (EntityCategory.BRIDGE, ("bridge",)),
    (EntityCategory.CEX, ("exchange", "cex", "hot wallet", "cold wallet")),
    (EntityCategory.DEX_ROUTER, ("router", "dex", "aggregator", "swap")),
    (EntityCategory.NFT_MARKETPLACE, ("nft", "marketplace", "opensea", "blur")),
    (EntityCategory.LENDING, ("lending", "aave", "compound", "morpho")),
    (EntityCategory.TOKEN, ("token contract", "erc20", "erc-20", "stablecoin")),
)
_ADDRESS_KEYS = ("address", "addr", "wallet")
_NAME_KEYS = ("name", "label", "name_tag", "nametag", "entity")
_CATEGORY_KEYS = ("category", "type", "label_type", "tag")


def read_seed(filename: str) -> list[dict[str, str]]:
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
            "source": SEED_SOURCE,
        }
        for r in read_seed(f"labels_{chain.name}.csv")
    ]
    if not rows:
        return 0
    stmt = insert(EntityLabel).values(rows)
    session.execute(
        stmt.on_conflict_do_update(
            index_elements=["chain_id", "address"],
            set_={c: stmt.excluded[c] for c in ("name", "category", "is_hub", "source")},
            # Manual labels win over the seed file.
            where=EntityLabel.source == SEED_SOURCE,
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
        for r in read_seed(f"tokens_{chain.name}.csv")
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
    """Labelled hubs plus every known token contract and DEX pool."""
    hubs = set(
        session.scalars(
            select(EntityLabel.address).where(
                EntityLabel.chain_id == chain_id, EntityLabel.is_hub.is_(True)
            )
        )
    )
    hubs.update(session.scalars(select(Token.address).where(Token.chain_id == chain_id)))
    # v4 pools are ids inside the PoolManager (a labelled hub), not addresses.
    hubs.update(
        session.scalars(
            select(DexPool.pool_id).where(
                DexPool.chain_id == chain_id, func.length(DexPool.pool_id) == ADDRESS_LENGTH
            )
        )
    )
    return hubs


def entity_labels(session: Session, chain_id: int) -> dict[str, EntityLabel]:
    return {
        label.address: label
        for label in session.scalars(select(EntityLabel).where(EntityLabel.chain_id == chain_id))
    }


@dataclass
class LabelImportResult:
    imported: int = 0
    hubs: int = 0
    skipped: int = 0


def classify_category(*texts: str | None) -> EntityCategory:
    """Map free-text categories or names from external lists onto ``EntityCategory``."""
    for text in texts:
        value = (text or "").strip().lower()
        if value in {c.value for c in EntityCategory}:
            return EntityCategory(value)
        for category, keywords in _CATEGORY_KEYWORDS:
            if any(k in value for k in keywords):
                return category
    return EntityCategory.OTHER


def _first(row: Mapping[str, Any], keys: tuple[str, ...]) -> str | None:
    lowered = {str(k).strip().lower(): v for k, v in row.items()}
    for key in keys:
        value = lowered.get(key)
        if value not in (None, ""):
            return str(value).strip()
    return None


def read_label_file(path: Path) -> list[dict[str, Any]]:
    """Rows from a CSV file with a header, or a JSON list of objects."""
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text())
        if not isinstance(data, list):
            raise ValueError(f"{path} must contain a JSON list of objects")
        return [row for row in data if isinstance(row, dict)]
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def import_labels(
    session: Session,
    chain_id: int,
    rows: Iterable[Mapping[str, Any]],
    *,
    source: str,
    category: EntityCategory | None = None,
) -> LabelImportResult:
    """Upsert labels from an external list.

    Columns are matched loosely (``address``/``addr``, ``name``/``label``,
    ``category``/``type``); ``is_hub`` is optional and otherwise follows the
    category. A re-import of the same ``source`` updates its rows; labels from
    the seed file or other sources are left alone.
    """
    if not source or source == SEED_SOURCE or len(source) > 32:
        raise ValueError(f"source must be 1-32 characters and not {SEED_SOURCE!r}")
    result = LabelImportResult()
    labels: dict[str, dict[str, Any]] = {}
    for row in rows:
        try:
            address = normalize_address(_first(row, _ADDRESS_KEYS) or "")
        except InvalidAddressError:
            result.skipped += 1
            continue
        name = _first(row, _NAME_KEYS)
        kind = category or classify_category(_first(row, _CATEGORY_KEYS), name)
        hub_flag = _first(row, ("is_hub",))
        is_hub = hub_flag.lower() == "true" if hub_flag is not None else kind in HUB_CATEGORIES
        labels[address] = {
            "chain_id": chain_id,
            "address": address,
            "name": (name or kind.value)[:128],
            "category": kind.value,
            "is_hub": is_hub,
            "source": source,
        }
    values = list(labels.values())
    for start in range(0, len(values), 5000):
        stmt = insert(EntityLabel).values(values[start : start + 5000])
        session.execute(
            stmt.on_conflict_do_update(
                index_elements=["chain_id", "address"],
                set_={c: stmt.excluded[c] for c in ("name", "category", "is_hub")},
                where=EntityLabel.source == source,
            )
        )
    result.imported = len(values)
    result.hubs = sum(v["is_hub"] for v in values)
    return result
