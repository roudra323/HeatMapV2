from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from heatmap_api.deps import ChainDep, LimitDep, OffsetDep, SessionDep
from heatmap_api.schemas import Page, TopTokenOut, TraderOut
from heatmap_core.exports.dex import TraderSort, list_traders

router = APIRouter(prefix="/v1/traders", tags=["traders"])


@router.get("", response_model=Page[TraderOut])
def traders(
    session: SessionDep,
    chain: ChainDep,
    limit: LimitDep,
    offset: OffsetDep = 0,
    include_bots: bool = False,
    min_volume_usd: Annotated[float | None, Query(ge=0)] = None,
    protocol: Annotated[str | None, Query(examples=["uniswap_v3"])] = None,
    sort: TraderSort = "volume",
) -> Page[TraderOut]:
    """Wallets discovered from DEX trades, biggest first; bots are hidden unless asked for."""
    total, rows = list_traders(
        session,
        chain.chain_id,
        include_bots=include_bots,
        min_volume_usd=min_volume_usd,
        protocol=protocol,
        sort=sort,
        limit=limit,
        offset=offset,
    )
    items = []
    for row in rows:
        t = row.trader
        items.append(
            TraderOut(
                address=t.address,
                first_trade_at=t.first_trade_at,
                last_trade_at=t.last_trade_at,
                tx_count=t.tx_count,
                active_days=t.active_days,
                volume_usd=t.volume_usd,
                max_tx_usd=t.max_tx_usd,
                distinct_tokens=t.distinct_tokens,
                protocols=t.protocols,
                top_tokens=[TopTokenOut(**token) for token in t.top_tokens],
                router_share=t.router_share,
                private_share=t.private_share,
                settlement_share=t.settlement_share,
                swaps_per_tx=t.swaps_per_tx,
                arbitrage_share=t.arbitrage_share,
                is_bot=t.is_bot,
                bot_reason=t.bot_reason,
                tracked=row.tracked,
                computed_at=t.computed_at,
            )
        )
    return Page(total=total, limit=limit, offset=offset, items=items)
