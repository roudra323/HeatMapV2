from datetime import UTC, datetime

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from heatmap_core.config import Settings
from heatmap_core.db.models import DexTrader, Token, Transfer, WalletLabel, WatchlistEntry
from heatmap_core.demo import demo_address, run_demo
from heatmap_core.primitives import WatchOrigin
from tests.support import ethereum

NOW = datetime(2026, 6, 1, tzinfo=UTC)


def tags_of(session: Session, address: str) -> set[str]:
    return set(
        session.scalars(
            select(WalletLabel.label).where(
                WalletLabel.address == address, WalletLabel.kind == "tag"
            )
        )
    )


def test_demo_dataset_produces_expected_behaviours(engine: Engine, session: Session) -> None:
    summary = run_demo(engine, ethereum(), Settings(), now=NOW)

    assert summary["seeds"] == 20
    farm_wallet = demo_address(1, 0)
    assert "sybil_suspect" in tags_of(session, farm_wallet)
    # wallets outside the farm share only spam/poisoning events, which must not link them
    flagged = session.scalars(
        select(WalletLabel.address).where(WalletLabel.label == "sybil_suspect")
    ).all()
    assert set(flagged) == {demo_address(1, i) for i in range(6)}
    zero_value = session.scalar(
        select(func.count()).select_from(Transfer).where(Transfer.spam_reason == "zero_value")
    )
    assert zero_value == 20
    assert "nft_trader" in tags_of(session, demo_address(3, 0))
    assert "stablecoin_heavy" in tags_of(session, demo_address(2, 0))
    assert "whale" in tags_of(session, demo_address(5, 0))

    fake = session.scalars(select(Token).where(Token.symbol.like("USD%"), Token.is_spam)).one()
    assert fake.spam_reason == "non_ascii_symbol"
    poisoning = session.scalar(
        select(func.count()).select_from(Transfer).where(Transfer.spam_reason == "spam_token")
    )
    assert poisoning == 20


def test_demo_swaps_exercise_discovery(engine: Engine, session: Session) -> None:
    summary = run_demo(engine, ethereum(), Settings(), now=NOW)

    bots = session.execute(select(DexTrader.address, DexTrader.bot_reason).where(DexTrader.is_bot))
    reasons = {address: reason for address, reason in bots}
    assert reasons == {
        demo_address(9, 0): "private_contract",
        demo_address(9, 1): "private_contract",
        demo_address(9, 2): "arbitrage",
        demo_address(9, 3): "settlement_signer",
        demo_address(9, 4): "batch_executor",
        demo_address(9, 5): "high_frequency",
    }
    promoted = set(
        session.scalars(
            select(WatchlistEntry.address).where(WatchlistEntry.origin == WatchOrigin.TRADER)
        )
    )
    # active traders and the whale; occasional small traders stay below the bar
    assert promoted == {demo_address(6, i) for i in range(10)} | {demo_address(8, 0)}
    assert summary["promoted"] == len(promoted)
    # promoted traders are synced, so their swaps show up as transfers too
    synced = session.scalar(
        select(func.count())
        .select_from(Transfer)
        .where(Transfer.from_address == demo_address(6, 0))
    )
    assert synced
