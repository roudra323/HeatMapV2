"""Read models for discovered traders and their trades."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.orm import Session, aliased

from heatmap_core.db.models import DexTrade, DexTrader, Token, WatchlistEntry

TraderSort = Literal["volume", "tx_count", "last_trade"]


@dataclass
class TraderRow:
    trader: DexTrader
    tracked: bool


@dataclass
class TradeRow:
    tx_hash: str
    block_number: int
    block_time: datetime
    log_index: int
    protocol: str
    pool_id: str
    tx_to: str | None
    token_in: str
    token_in_symbol: str | None
    amount_in: Decimal | None
    token_out: str
    token_out_symbol: str | None
    amount_out: Decimal | None
    amount_usd: Decimal | None


def list_traders(
    session: Session,
    chain_id: int,
    *,
    include_bots: bool = False,
    min_volume_usd: float | None = None,
    protocol: str | None = None,
    sort: TraderSort = "volume",
    limit: int,
    offset: int,
) -> tuple[int, list[TraderRow]]:
    conditions: list[Any] = [DexTrader.chain_id == chain_id]
    if not include_bots:
        conditions.append(DexTrader.is_bot.is_(False))
    if min_volume_usd is not None:
        conditions.append(DexTrader.volume_usd >= min_volume_usd)
    if protocol is not None:
        conditions.append(DexTrader.protocols.contains([protocol]))
    orders: dict[str, ColumnElement[Any]] = {
        "volume": DexTrader.volume_usd.desc().nulls_last(),
        "tx_count": DexTrader.tx_count.desc(),
        "last_trade": DexTrader.last_trade_at.desc(),
    }
    order = orders[sort]
    total = session.scalar(select(func.count()).select_from(DexTrader).where(*conditions)) or 0
    watched = (
        select(WatchlistEntry.address)
        .where(WatchlistEntry.chain_id == chain_id, WatchlistEntry.active.is_(True))
        .scalar_subquery()
    )
    rows = session.execute(
        select(DexTrader, DexTrader.address.in_(watched))
        .where(*conditions)
        .order_by(order, DexTrader.address)
        .limit(limit)
        .offset(offset)
    ).all()
    return int(total), [TraderRow(trader, bool(tracked)) for trader, tracked in rows]


def wallet_trades(
    session: Session, chain_id: int, address: str, *, limit: int, offset: int
) -> tuple[int, list[TradeRow]]:
    conditions = [DexTrade.chain_id == chain_id, DexTrade.trader == address]
    total = session.scalar(select(func.count()).select_from(DexTrade).where(*conditions)) or 0
    token_in, token_out = aliased(Token), aliased(Token)
    rows = session.execute(
        select(DexTrade, token_in.symbol, token_out.symbol)
        .outerjoin(
            token_in,
            (token_in.chain_id == DexTrade.chain_id) & (token_in.address == DexTrade.token_in),
        )
        .outerjoin(
            token_out,
            (token_out.chain_id == DexTrade.chain_id) & (token_out.address == DexTrade.token_out),
        )
        .where(*conditions)
        .order_by(DexTrade.block_number.desc(), DexTrade.log_index.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return int(total), [
        TradeRow(
            tx_hash=t.tx_hash,
            block_number=t.block_number,
            block_time=t.block_time,
            log_index=t.log_index,
            protocol=t.protocol,
            pool_id=t.pool_id,
            tx_to=t.tx_to,
            token_in=t.token_in,
            token_in_symbol=symbol_in,
            amount_in=t.amount_in,
            token_out=t.token_out,
            token_out_symbol=symbol_out,
            amount_out=t.amount_out,
            amount_usd=t.amount_usd,
        )
        for t, symbol_in, symbol_out in rows
    ]
