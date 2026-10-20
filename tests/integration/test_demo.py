from datetime import UTC, datetime

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from heatmap_core.config import Settings
from heatmap_core.db.models import Token, Transfer, WalletLabel
from heatmap_core.demo import demo_address, run_demo
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
