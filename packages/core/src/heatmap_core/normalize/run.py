"""Normalisation stage: amounts, spam flags, USD values and funding sources."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Engine, func, select, text, update
from sqlalchemy.orm import Session

from heatmap_core.config import Chain, Settings
from heatmap_core.db.models import Token, Transfer, WatchlistEntry
from heatmap_core.db.session import session_scope
from heatmap_core.ingestion.sync import scaled_amount
from heatmap_core.logging import get_logger
from heatmap_core.normalize.pricing import PriceBook, PriceSource
from heatmap_core.normalize.spam import (
    TokenInfo,
    TransferInfo,
    token_spam_reason,
    transfer_spam_reasons,
)
from heatmap_core.primitives import NATIVE_TOKEN, TokenCategory, TransferCategory

log = get_logger(__name__)


@dataclass
class NormalizeResult:
    transfers: int = 0
    spam: int = 0
    priced: int = 0
    spam_tokens: int = 0
    funded_wallets: int = 0


def _verified_symbols(session: Session, chain_id: int) -> dict[str, str]:
    rows = session.execute(
        select(Token.symbol, Token.address).where(
            Token.chain_id == chain_id, Token.is_verified.is_(True), Token.symbol.is_not(None)
        )
    )
    return {str(symbol).upper(): address for symbol, address in rows}


def _classify_tokens(
    session: Session, chain_id: int, addresses: set[str], settings: Settings
) -> tuple[dict[str, Token], int]:
    tokens = {
        t.address: t
        for t in session.scalars(
            select(Token).where(Token.chain_id == chain_id, Token.address.in_(addresses))
        )
    }
    verified_symbols = _verified_symbols(session, chain_id)
    flagged = 0
    for token in tokens.values():
        reason = (
            token_spam_reason(
                TokenInfo(token.address, token.symbol, token.name, token.is_verified),
                verified_symbols,
                settings.spam,
            )
            if settings.spam.enabled
            else None
        )
        if token.is_spam != (reason is not None) or token.spam_reason != reason:
            token.is_spam = reason is not None
            token.spam_reason = reason
            flagged += int(reason is not None)
    return tokens, flagged


def _real_counterparties(session: Session, chain_id: int, wallets: set[str]) -> dict[str, set[str]]:
    if not wallets:
        return {}
    rows = session.execute(
        select(Transfer.from_address, Transfer.to_address)
        .where(
            Transfer.chain_id == chain_id,
            Transfer.from_address.in_(wallets),
            Transfer.raw_amount > 0,
            Transfer.is_spam.is_(False),
        )
        .distinct()
    )
    result: dict[str, set[str]] = defaultdict(set)
    for src, dst in rows:
        result[src].add(dst)
    return result


def _recipient_counts(
    session: Session, chain_id: int, tx_hashes: set[str]
) -> dict[tuple[str, str], int]:
    rows = session.execute(
        select(
            Transfer.tx_hash,
            Transfer.token_address,
            func.count(func.distinct(Transfer.to_address)),
        )
        .where(Transfer.chain_id == chain_id, Transfer.tx_hash.in_(tx_hashes))
        .group_by(Transfer.tx_hash, Transfer.token_address)
    )
    return {(tx, token): int(n) for tx, token, n in rows}


def normalize_pending(
    engine: Engine,
    chain: Chain,
    settings: Settings,
    price_source: PriceSource | None = None,
    *,
    batch_size: int = 20_000,
) -> NormalizeResult:
    result = NormalizeResult()
    chain_id = chain.chain_id

    with session_scope(engine) as session:
        tracked = set(
            session.scalars(
                select(WatchlistEntry.address).where(WatchlistEntry.chain_id == chain_id)
            )
        )

    while True:
        with session_scope(engine) as session:
            batch = list(
                session.scalars(
                    select(Transfer)
                    .where(Transfer.chain_id == chain_id, Transfer.normalized_at.is_(None))
                    .order_by(Transfer.id)
                    .limit(batch_size)
                )
            )
            if not batch:
                break
            stats = _normalize_batch(session, chain, settings, price_source, batch, tracked)
            result.transfers += len(batch)
            result.spam += stats["spam"]
            result.priced += stats["priced"]
            result.spam_tokens += stats["spam_tokens"]

    with session_scope(engine) as session:
        result.funded_wallets = update_funding_sources(session, chain_id)

    log.info("normalize.done", chain=chain.name, **result.__dict__)
    return result


def _normalize_batch(
    session: Session,
    chain: Chain,
    settings: Settings,
    price_source: PriceSource | None,
    batch: list[Transfer],
    tracked: set[str],
) -> dict[str, int]:
    chain_id = chain.chain_id
    tokens, spam_tokens_flagged = _classify_tokens(
        session, chain_id, {t.token_address for t in batch}, settings
    )
    spam_tokens = {a for a, t in tokens.items() if t.is_spam}
    verified = {a for a, t in tokens.items() if t.is_verified}

    reasons: dict[int, str] = {}
    if settings.spam.enabled:
        wallets_in_batch = {t.from_address for t in batch} | {t.to_address for t in batch}
        reasons = transfer_spam_reasons(
            (
                TransferInfo(
                    t.id,
                    t.tx_hash,
                    t.category,
                    t.from_address,
                    t.to_address,
                    t.token_address,
                    t.raw_amount,
                )
                for t in batch
            ),
            tracked,
            spam_tokens,
            verified,
            _real_counterparties(session, chain_id, wallets_in_batch & tracked),
            settings.spam,
            _recipient_counts(session, chain_id, {t.tx_hash for t in batch}),
        )

    # Fill decimals-based amounts, then prime prices for every (token, day) needed.
    amounts: dict[int, Decimal | None] = {}
    days_by_token: dict[str, set[date]] = defaultdict(set)
    for t in batch:
        amount = t.amount
        if amount is None:
            token = tokens.get(t.token_address)
            decimals = (
                chain.config.native_decimals
                if t.token_address == NATIVE_TOKEN
                else (token.decimals if token else None)
            )
            if TransferCategory(t.category).is_nft:
                decimals = 0
            amount = scaled_amount(t.raw_amount, decimals)
        amounts[t.id] = amount
        if amount is not None and t.id not in reasons and not TransferCategory(t.category).is_nft:
            days_by_token[t.token_address].add(t.block_time.date())

    stable = {
        a for a, t in tokens.items() if t.is_verified and t.category == TokenCategory.STABLECOIN
    }
    book = PriceBook(
        session,
        chain_id,
        price_source if settings.pricing.enabled else None,
        stable,
    )
    for token_address, days in days_by_token.items():
        token = tokens.get(token_address)
        if token is not None and (token.price_id or token_address in stable):
            book.prime(token_address, token.price_id, days)

    now = datetime.now(UTC)
    updates: list[dict[str, Any]] = []
    priced = 0
    for t in batch:
        amount = amounts[t.id]
        price = book.price(t.token_address, t.block_time.date())
        usd = (amount * price).quantize(Decimal("0.00000001")) if amount and price else None
        priced += int(usd is not None)
        reason = reasons.get(t.id)
        updates.append(
            {
                "id": t.id,
                "amount": amount,
                "amount_usd": usd,
                "is_spam": reason is not None,
                "spam_reason": reason,
                "normalized_at": now,
            }
        )
    session.flush()  # persist token spam flags before detaching
    session.expunge_all()
    session.execute(update(Transfer), updates)
    return {"spam": len(reasons), "priced": priced, "spam_tokens": spam_tokens_flagged}


FUNDING_SQL = text(
    """
    UPDATE wallets AS w
    SET funded_by = f.from_address
    FROM (
        SELECT DISTINCT ON (t.to_address) t.to_address, t.from_address
        FROM transfers t
        JOIN watchlist wl ON wl.chain_id = t.chain_id AND wl.address = t.to_address
        WHERE t.chain_id = :chain_id
          AND t.category IN ('external', 'internal')
          AND t.raw_amount > 0
          AND NOT t.is_spam
        ORDER BY t.to_address, t.block_number, t.id
    ) AS f
    WHERE w.chain_id = :chain_id AND w.address = f.to_address AND w.funded_by IS NULL
    """
)


def update_funding_sources(session: Session, chain_id: int) -> int:
    """Record who first sent native currency to each tracked wallet."""
    return int(session.execute(FUNDING_SQL, {"chain_id": chain_id}).rowcount or 0)  # type: ignore[attr-defined]
