from datetime import date
from decimal import Decimal

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from heatmap_core.config import Settings
from heatmap_core.db.models import Token, TokenPrice, Transfer, Wallet
from heatmap_core.db.session import session_scope
from heatmap_core.entities.labels import hub_addresses, load_seed_labels, load_seed_tokens
from heatmap_core.ingestion.sync import sync_wallet
from heatmap_core.ingestion.watchlist import add_seed
from heatmap_core.normalize.run import normalize_pending
from heatmap_core.primitives import NATIVE_TOKEN, TransferCategory
from tests.support import FakeSource, addr, ethereum, raw

WALLET = addr(1)
FUNDER = addr(2)
USDC = "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"
FAKE_USDC = addr(0xBAD)


class FakePrices:
    name = "fake"

    def __init__(self) -> None:
        self.calls: list[str] = []

    def daily_prices(self, price_id: str, start: date, end: date) -> dict[date, Decimal]:
        self.calls.append(price_id)
        return {date(2026, 1, 1): Decimal("2000")}


def setup(engine: Engine) -> None:
    with session_scope(engine) as s:
        load_seed_tokens(s, ethereum())
        load_seed_labels(s, ethereum())
        add_seed(s, 1, WALLET)


def test_normalize_prices_flags_spam_and_funding(engine: Engine, session: Session) -> None:
    setup(engine)
    source = FakeSource(
        [
            raw(1, FUNDER, WALLET, amount=2 * 10**18),  # 2 ETH funding
            raw(
                2,
                WALLET,
                addr(3),
                category=TransferCategory.ERC20,
                token=USDC,
                symbol="USDC",
                decimals=6,
                amount=5_000_000,
            ),
            raw(
                3,
                addr(4),
                WALLET,
                category=TransferCategory.ERC20,
                token=FAKE_USDC,
                symbol="USDC",
                decimals=6,
                amount=1,
            ),
        ],
        head=10,
    )
    sync_wallet(engine, source, ethereum(), WALLET)
    prices = FakePrices()

    result = normalize_pending(engine, ethereum(), Settings(), prices)

    assert result.transfers == 3 and result.spam == 1 and result.funded_wallets == 1
    by_block = {t.block_number: t for t in session.scalars(select(Transfer))}
    assert by_block[1].amount_usd == Decimal("4000.00000000")
    assert by_block[2].amount_usd == Decimal("5.00000000")  # stablecoin, no lookup
    assert by_block[3].is_spam and by_block[3].spam_reason == "spam_token"
    assert all(t.normalized_at is not None for t in by_block.values())
    fake = session.get(Token, (1, FAKE_USDC))
    assert fake is not None and fake.spam_reason == "impersonates:USDC"
    wallet = session.get(Wallet, (1, WALLET))
    assert wallet is not None and wallet.funded_by == FUNDER
    assert prices.calls == ["ethereum"]
    assert session.get(TokenPrice, (1, NATIVE_TOKEN, date(2026, 1, 1))) is not None

    # second run has nothing pending and uses cached prices
    assert normalize_pending(engine, ethereum(), Settings(), prices).transfers == 0


def test_hub_addresses_include_labels_and_tokens(engine: Engine, session: Session) -> None:
    setup(engine)
    hubs = hub_addresses(session, 1)
    assert "0x28c6c06298d514db089934071355e5743bf21d60" in hubs  # Binance 14
    assert USDC in hubs
    assert WALLET not in hubs
