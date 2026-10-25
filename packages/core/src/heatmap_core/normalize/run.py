"""Normalisation stage: amounts, spam flags, USD values and funding sources.

Spam flags that depend on other transfers are kept current: when a token's spam
status flips, or a transaction reaches the mass-airdrop recipient count because
more wallets were synced, the affected transfers are queued for normalisation
again. Transfers whose USD value is missing are re-priced on every run until
the price source answers.
"""

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
    requeued: int = 0
    repriced: int = 0
    funded_wallets: int = 0
    skipped: bool = False


def utc_day(when: datetime) -> date:
    return when.astimezone(UTC).date()


def usd_value(amount: Decimal | None, price: Decimal | None) -> Decimal | None:
    return (amount * price).quantize(Decimal("0.00000001")) if amount and price else None


def _verified_symbols(session: Session, chain_id: int) -> dict[str, str]:
    rows = session.execute(
        select(Token.symbol, Token.address).where(
            Token.chain_id == chain_id, Token.is_verified.is_(True), Token.symbol.is_not(None)
        )
    )
    return {str(symbol).upper(): address for symbol, address in rows}


def _classify_tokens(
    session: Session, chain_id: int, addresses: set[str], settings: Settings
) -> tuple[dict[str, Token], int, set[str]]:
    """Refresh token spam flags; returns tokens, newly flagged count and tokens that flipped."""
    tokens = {
        t.address: t
        for t in session.scalars(
            select(Token).where(Token.chain_id == chain_id, Token.address.in_(addresses))
        )
    }
    verified_symbols = _verified_symbols(session, chain_id)
    flagged = 0
    flipped: set[str] = set()
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
        if token.is_spam != (reason is not None):
            flipped.add(token.address)
        if token.is_spam != (reason is not None) or token.spam_reason != reason:
            token.is_spam = reason is not None
            token.spam_reason = reason
            flagged += int(reason is not None)
    return tokens, flagged, flipped


def _real_counterparties(
    session: Session, chain_id: int, wallets: set[str]
) -> dict[str, dict[str, datetime]]:
    """For each wallet, the addresses it sent value to and when it first did."""
    if not wallets:
        return {}
    rows = session.execute(
        select(Transfer.from_address, Transfer.to_address, func.min(Transfer.block_time))
        .where(
            Transfer.chain_id == chain_id,
            Transfer.from_address.in_(wallets),
            Transfer.raw_amount > 0,
            Transfer.is_spam.is_(False),
        )
        .group_by(Transfer.from_address, Transfer.to_address)
    )
    result: dict[str, dict[str, datetime]] = defaultdict(dict)
    for src, dst, first in rows:
        result[src][dst] = first
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
    source = price_source if settings.pricing.enabled else None

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
            stats = _normalize_batch(session, chain, settings, source, batch, tracked)
            result.transfers += len(batch)
            result.spam += stats["spam"]
            result.priced += stats["priced"]
            result.spam_tokens += stats["spam_tokens"]
            result.requeued += stats["requeued"]

    result.repriced = reprice_missing(engine, chain, source, batch_size=batch_size)
    with session_scope(engine) as session:
        result.funded_wallets = update_funding_sources(session, chain_id)

    log.info("normalize.done", chain=chain.name, **result.__dict__)
    return result


def _normalize_batch(
    session: Session,
    chain: Chain,
    settings: Settings,
    source: PriceSource | None,
    batch: list[Transfer],
    tracked: set[str],
) -> dict[str, int]:
    chain_id = chain.chain_id
    tokens, spam_tokens_flagged, flipped = _classify_tokens(
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
            days_by_token[t.token_address].add(utc_day(t.block_time))

    book = _price_book(session, chain, source, tokens)
    for token_address, days in days_by_token.items():
        _prime(book, chain, source, tokens.get(token_address), days)

    now = datetime.now(UTC)
    updates: list[dict[str, Any]] = []
    priced = 0
    for t in batch:
        amount = amounts[t.id]
        usd = usd_value(amount, book.price(t.token_address, utc_day(t.block_time)))
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
    batch_ids = [t.id for t in batch]
    tx_hashes = sorted({t.tx_hash for t in batch})
    session.flush()  # persist token spam flags before detaching
    session.expunge_all()
    session.execute(update(Transfer), updates)

    requeued = 0
    if flipped:
        requeued += _rowcount(
            session.execute(
                REQUEUE_TOKENS_SQL,
                {"chain_id": chain_id, "tokens": sorted(flipped), "batch_ids": batch_ids},
            )
        )
    if settings.spam.enabled:
        requeued += _rowcount(
            session.execute(
                REQUEUE_AIRDROPS_SQL,
                {
                    "chain_id": chain_id,
                    "tx_hashes": tx_hashes,
                    "min_recipients": settings.spam.airdrop_min_recipients,
                    "batch_ids": batch_ids,
                },
            )
        )
    return {
        "spam": len(reasons),
        "priced": priced,
        "spam_tokens": spam_tokens_flagged,
        "requeued": requeued,
    }


def _rowcount(result: Any) -> int:
    return int(result.rowcount or 0)


def _price_book(
    session: Session, chain: Chain, source: PriceSource | None, tokens: dict[str, Token]
) -> PriceBook:
    stable = {
        a for a, t in tokens.items() if t.is_verified and t.category == TokenCategory.STABLECOIN
    }
    return PriceBook(session, chain.chain_id, source, stable)


def _prime(
    book: PriceBook,
    chain: Chain,
    source: PriceSource | None,
    token: Token | None,
    days: set[date],
) -> None:
    if token is None:
        return
    if source is not None:
        book.prime(token.address, source.price_key(chain, token), days)
    elif token.price_id or (token.is_verified and token.category == TokenCategory.STABLECOIN):
        book.prime(token.address, None, days)  # stablecoin peg and stored prices only


# Other transfers of a token whose spam status changed get normalised again.
REQUEUE_TOKENS_SQL = text(
    """
    UPDATE transfers SET normalized_at = NULL
    WHERE chain_id = :chain_id
      AND token_address = ANY(:tokens)
      AND normalized_at IS NOT NULL
      AND id <> ALL(:batch_ids)
    """
)

# Transactions that now reach the mass-airdrop recipient count: earlier recipients
# were normalised before the others were synced, so they are checked again.
REQUEUE_AIRDROPS_SQL = text(
    """
    UPDATE transfers AS t SET normalized_at = NULL
    FROM (
        SELECT tx_hash, token_address
        FROM transfers
        WHERE chain_id = :chain_id AND tx_hash = ANY(:tx_hashes)
        GROUP BY tx_hash, token_address
        HAVING COUNT(DISTINCT to_address) >= :min_recipients
    ) AS drops
    WHERE t.chain_id = :chain_id
      AND t.tx_hash = drops.tx_hash
      AND t.token_address = drops.token_address
      AND t.normalized_at IS NOT NULL
      AND NOT t.is_spam
      AND t.id <> ALL(:batch_ids)
      AND NOT EXISTS (
          SELECT 1 FROM tokens tok
          WHERE tok.chain_id = t.chain_id AND tok.address = t.token_address AND tok.is_verified
      )
    """
)

UNPRICED_SQL = text(
    """
    SELECT t.id, t.token_address, t.block_time, t.amount
    FROM transfers t
    WHERE t.chain_id = :chain_id
      AND t.id > :after
      AND t.amount_usd IS NULL
      AND t.normalized_at IS NOT NULL
      AND NOT t.is_spam
      AND t.amount <> 0
      AND t.category IN ('external', 'internal', 'erc20')
      AND NOT EXISTS (
          SELECT 1 FROM token_prices p
          WHERE p.chain_id = t.chain_id
            AND p.token_address = t.token_address
            AND p.day = (t.block_time AT TIME ZONE 'UTC')::date
            AND p.price_usd IS NULL
            AND p.source = :source
      )
    ORDER BY t.id
    LIMIT :limit
    """
)


def reprice_missing(
    engine: Engine, chain: Chain, source: PriceSource | None, *, batch_size: int = 20_000
) -> int:
    """Price normalised transfers that have no USD value yet, e.g. after a failed fetch.

    Days the source has answered "no price" for are skipped, so each run only
    asks again for what failed or was never asked.
    """
    if source is None:
        return 0
    repriced = 0
    after = 0
    while True:
        with session_scope(engine) as session:
            rows = session.execute(
                UNPRICED_SQL,
                {
                    "chain_id": chain.chain_id,
                    "after": after,
                    "source": source.name,
                    "limit": batch_size,
                },
            ).all()
            if not rows:
                break
            after = rows[-1].id
            tokens = {
                t.address: t
                for t in session.scalars(
                    select(Token).where(
                        Token.chain_id == chain.chain_id,
                        Token.address.in_({r.token_address for r in rows}),
                    )
                )
            }
            days_by_token: dict[str, set[date]] = defaultdict(set)
            for r in rows:
                days_by_token[r.token_address].add(utc_day(r.block_time))
            book = _price_book(session, chain, source, tokens)
            for token_address, days in days_by_token.items():
                _prime(book, chain, source, tokens.get(token_address), days)
            updates = [
                {"id": r.id, "amount_usd": usd}
                for r in rows
                if (usd := usd_value(r.amount, book.price(r.token_address, utc_day(r.block_time))))
                is not None
            ]
            if updates:
                session.execute(update(Transfer), updates)
            repriced += len(updates)
    return repriced


# Recomputed every run: a funding transfer may later be flagged as spam, removed
# by a reorg, or preceded by older history that was synced afterwards.
FUNDING_SQL = text(
    """
    UPDATE wallets AS w
    SET funded_by = f.from_address
    FROM (
        SELECT wl.address, first_in.from_address
        FROM watchlist wl
        LEFT JOIN LATERAL (
            SELECT t.from_address
            FROM transfers t
            WHERE t.chain_id = wl.chain_id
              AND t.to_address = wl.address
              AND t.category IN ('external', 'internal')
              AND t.raw_amount > 0
              AND t.normalized_at IS NOT NULL
              AND NOT t.is_spam
            ORDER BY t.block_time, t.block_number, t.id
            LIMIT 1
        ) AS first_in ON true
        WHERE wl.chain_id = :chain_id
    ) AS f
    WHERE w.chain_id = :chain_id
      AND w.address = f.address
      AND w.funded_by IS DISTINCT FROM f.from_address
    """
)


def update_funding_sources(session: Session, chain_id: int) -> int:
    """Set who first sent native currency to each tracked wallet; returns wallets changed."""
    return int(session.execute(FUNDING_SQL, {"chain_id": chain_id}).rowcount or 0)  # type: ignore[attr-defined]
