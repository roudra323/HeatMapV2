from datetime import date
from decimal import Decimal

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from heatmap_core.config import Chain, Settings
from heatmap_core.db.models import EntityLabel, Token, TokenPrice, Transfer, Wallet
from heatmap_core.db.session import session_scope
from heatmap_core.entities.labels import (
    hub_addresses,
    import_labels,
    load_seed_labels,
    load_seed_tokens,
)
from heatmap_core.ingestion.sync import sync_wallet
from heatmap_core.ingestion.watchlist import add_seed
from heatmap_core.normalize.run import normalize_pending
from heatmap_core.primitives import NATIVE_TOKEN, TransferCategory
from heatmap_core.providers import TransientProviderError
from tests.support import FakeSource, addr, ethereum, raw

WALLET = addr(1)
FUNDER = addr(2)
USDC = "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"
FAKE_USDC = addr(0xBAD)


class FakePrices:
    name = "fake"

    def __init__(self) -> None:
        self.calls: list[str] = []

    def price_key(self, chain: Chain, token: Token) -> str | None:
        return token.price_id

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


TOKEN = addr(0xA11)


class FlakyPrices:
    """Prices ETH at 2000 and knows nothing about other tokens; can be made to fail."""

    name = "flaky"

    def __init__(self) -> None:
        self.fail = False
        self.calls: list[str] = []

    def price_key(self, chain: Chain, token: Token) -> str | None:
        return f"key:{token.address}"

    def daily_prices(self, key: str, start: date, end: date) -> dict[date, Decimal]:
        self.calls.append(key)
        if self.fail:
            raise TransientProviderError("HTTP 429")
        return {date(2026, 1, 1): Decimal("2000")} if key == f"key:{NATIVE_TOKEN}" else {}


def test_failed_prices_are_retried_and_misses_cached(engine: Engine, session: Session) -> None:
    setup(engine)
    source = FakeSource(
        [
            raw(1, FUNDER, WALLET),
            raw(2, WALLET, addr(3), category=TransferCategory.ERC20, token=TOKEN, symbol="ABC"),
        ],
        head=10,
    )
    sync_wallet(engine, source, ethereum(), WALLET)
    prices = FlakyPrices()
    prices.fail = True

    first = normalize_pending(engine, ethereum(), Settings(), prices)
    assert first.priced == 0
    assert all(t.amount_usd is None for t in session.scalars(select(Transfer)))

    prices.fail = False
    second = normalize_pending(engine, ethereum(), Settings(), prices)
    assert second.transfers == 0 and second.repriced == 1
    session.expire_all()
    by_block = {t.block_number: t for t in session.scalars(select(Transfer))}
    assert by_block[1].amount_usd == Decimal("2000.00000000")
    assert by_block[2].amount_usd is None
    miss = session.get(TokenPrice, (1, TOKEN, date(2026, 1, 1)))
    assert miss is not None and miss.price_usd is None and miss.source == "flaky"

    calls = len(prices.calls)
    assert normalize_pending(engine, ethereum(), Settings(), prices).repriced == 0
    assert len(prices.calls) == calls  # the recorded miss is not asked again


def test_token_turning_spam_requeues_its_earlier_transfers(
    engine: Engine, session: Session
) -> None:
    with session_scope(engine) as s:
        add_seed(s, 1, WALLET)
    fake = dict(category=TransferCategory.ERC20, token=FAKE_USDC, symbol="USDC", decimals=6)
    source = FakeSource([raw(1, addr(4), WALLET, **fake)], head=5)
    sync_wallet(engine, source, ethereum(), WALLET)
    normalize_pending(engine, ethereum(), Settings(), None)
    assert not session.scalars(select(Transfer)).one().is_spam

    # The real USDC becomes known, so the look-alike token is now spam.
    with session_scope(engine) as s:
        load_seed_tokens(s, ethereum())
    source.transfers.append(raw(6, addr(4), WALLET, **fake))
    source.head = 10
    sync_wallet(engine, source, ethereum(), WALLET)
    result = normalize_pending(engine, ethereum(), Settings(), None)

    assert result.requeued == 1 and result.transfers == 2
    session.expire_all()
    assert [t.spam_reason for t in session.scalars(select(Transfer))] == ["spam_token"] * 2


def test_airdrop_flagged_once_enough_recipients_are_synced(
    engine: Engine, session: Session
) -> None:
    wallets = [addr(0x100 + i) for i in range(3)]
    with session_scope(engine) as s:
        for w in wallets:
            add_seed(s, 1, w)
    drop = dict(category=TransferCategory.ERC20, token=TOKEN, symbol="AIR", tx="0x" + "d" * 64)
    source = FakeSource([raw(1, addr(9), w, **drop) for w in wallets], head=5)
    settings = Settings(spam={"airdrop_min_recipients": 3})

    sync_wallet(engine, source, ethereum(), wallets[0])
    normalize_pending(engine, ethereum(), settings, None)
    assert not session.scalars(select(Transfer)).one().is_spam

    for w in wallets[1:]:
        sync_wallet(engine, source, ethereum(), w)
    result = normalize_pending(engine, ethereum(), settings, None)

    assert result.requeued == 1
    session.expire_all()
    assert [t.spam_reason for t in session.scalars(select(Transfer))] == ["mass_airdrop"] * 3


def test_import_labels_respects_other_sources(engine: Engine, session: Session) -> None:
    setup(engine)
    binance = "0x28c6c06298d514db089934071355e5743bf21d60"  # in the seed file
    rows = [
        {"address": binance, "name": "Renamed", "category": "exchange"},
        {"Address": addr(0x51).upper().replace("0X", "0x"), "Label": "Some Bridge"},
        {"address": addr(0x52), "name": "Fund", "type": "fund"},
        {"address": "not-an-address"},
    ]
    with session_scope(engine) as s:
        result = import_labels(s, 1, rows, source="list-a")
    assert (result.imported, result.hubs, result.skipped) == (3, 2, 1)

    labels = {lbl.address: lbl for lbl in session.scalars(select(EntityLabel))}
    assert labels[binance].name != "Renamed" and labels[binance].source == "seed_file"
    assert labels[addr(0x51)].category == "bridge" and labels[addr(0x51)].is_hub
    assert labels[addr(0x52)].category == "other" and not labels[addr(0x52)].is_hub

    with session_scope(engine) as s:
        import_labels(s, 1, [{"address": addr(0x52), "name": "Fund II"}], source="list-a")
        import_labels(s, 1, [{"address": addr(0x51), "name": "Other"}], source="list-b")
    session.expire_all()
    assert session.get(EntityLabel, (1, addr(0x52))).name == "Fund II"
    assert session.get(EntityLabel, (1, addr(0x51))).name == "Some Bridge"
