"""USD value of trades, taken from their stablecoin or ETH/WETH side.

Most swaps have such a side, which keeps price lookups to one series (ETH)
plus the $1 stablecoin peg instead of one per long-tail token.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy import Engine, select, text, update

from heatmap_core.config import Chain
from heatmap_core.db.models import DexTrade, Token
from heatmap_core.db.session import session_scope
from heatmap_core.normalize.pricing import PriceBook, PriceSource
from heatmap_core.normalize.run import usd_value, utc_day
from heatmap_core.primitives import NATIVE_TOKEN, TokenCategory

UNVALUED_SQL = text(
    """
    SELECT id, block_time, token_in, token_out, amount_in, amount_out
    FROM dex_trades
    WHERE chain_id = :chain_id
      AND amount_usd IS NULL
      AND id > :after
      AND (token_in = ANY(:quotes) OR token_out = ANY(:quotes))
    ORDER BY id
    LIMIT :limit
    """
)


def quote_tokens(engine: Engine, chain: Chain) -> tuple[dict[str, Token], set[str]]:
    """Verified stablecoins plus native/wrapped native; returns them and the stablecoin set."""
    eth_like = {
        NATIVE_TOKEN,
        *([chain.config.wrapped_native] if chain.config.wrapped_native else []),
    }
    with session_scope(engine) as session:
        tokens = {
            t.address: t
            for t in session.scalars(
                select(Token).where(
                    Token.chain_id == chain.chain_id,
                    Token.is_verified.is_(True),
                    (Token.category == TokenCategory.STABLECOIN) | Token.address.in_(eth_like),
                )
            )
        }
    stable = {a for a, t in tokens.items() if t.category == TokenCategory.STABLECOIN}
    return tokens, stable


def value_trades(
    engine: Engine, chain: Chain, prices: PriceSource | None, *, batch_size: int = 20_000
) -> int:
    """Fill ``amount_usd`` where possible; trades whose ETH price is missing are retried later."""
    tokens, stable = quote_tokens(engine, chain)
    if not tokens:
        return 0
    quotes = sorted(tokens)
    valued = 0
    after = 0
    while True:
        with session_scope(engine) as session:
            rows = session.execute(
                UNVALUED_SQL,
                {"chain_id": chain.chain_id, "after": after, "quotes": quotes, "limit": batch_size},
            ).all()
            if not rows:
                break
            after = rows[-1].id
            picks: dict[int, tuple[str, Decimal | None, date]] = {}
            days: dict[str, set[date]] = defaultdict(set)
            for r in rows:
                sides = [(r.token_in, r.amount_in), (r.token_out, r.amount_out)]
                side = next((s for s in sides if s[0] in stable), None) or next(
                    s for s in sides if s[0] in tokens
                )
                picks[r.id] = (side[0], side[1], utc_day(r.block_time))
                days[side[0]].add(utc_day(r.block_time))
            book = PriceBook(session, chain.chain_id, prices, stable)
            for address, token_days in days.items():
                key = prices.price_key(chain, tokens[address]) if prices else None
                book.prime(address, key, token_days)
            updates = [
                {"id": trade_id, "amount_usd": usd}
                for trade_id, (address, amount, day) in picks.items()
                if (usd := usd_value(amount, book.price(address, day))) is not None
            ]
            if updates:
                session.execute(update(DexTrade), updates)
            valued += len(updates)
    return valued
