"""DEX trade discovery end to end on a scripted chain."""

from datetime import UTC, date, datetime
from decimal import Decimal

from eth_abi.abi import encode
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from heatmap_core.config import Chain, Settings
from heatmap_core.db.models import DexPool, DexTrade, DexTrader, Token, WatchlistEntry
from heatmap_core.db.session import session_scope
from heatmap_core.ingestion.watchlist import add_seed, deactivate
from heatmap_core.pipeline import discover_traders, seed_reference_data
from heatmap_core.primitives import NATIVE_TOKEN, NULL_ADDRESS
from tests.support import addr
from tests.support_dex import (
    COW_SETTLEMENT,
    POSITION_MANAGER,
    UNI_V2_FACTORY,
    UNI_V3_FACTORY,
    UNIVERSAL_ROUTER,
    USDC,
    WETH,
    FakeDexChain,
    dex_chain,
    v4_pool_id,
    word,
)

HUMAN, BOT, SOLVER, OTHER = addr(0xA1), addr(0xB1), addr(0x50), addr(0xA2)
BOT_CONTRACT = addr(0xC0)
NEW = addr(0xAE)  # a token nobody has seen before
V2_POOL, V3_POOL, FAKE_POOL = addr(0x2001), addr(0x3001), addr(0x2BAD)
V4_KEY = (NULL_ADDRESS, USDC, 500, 10, NULL_ADDRESS)
V4_POOL = v4_pool_id(V4_KEY)
DAY1, DAY2 = datetime(2026, 1, 1, 12, tzinfo=UTC), datetime(2026, 1, 2, 12, tzinfo=UTC)


class EthPrices:
    name = "test"

    def price_key(self, chain: Chain, token: Token) -> str | None:
        return token.price_id

    def daily_prices(self, key: str, start: date, end: date) -> dict[date, Decimal]:
        return {date(2026, 1, 1): Decimal(2000), date(2026, 1, 2): Decimal(2000)}


def build_chain() -> FakeDexChain:
    fake = FakeDexChain(head=105)
    # pool registry answers
    for pool, t0, t1, factory in (
        (V2_POOL, USDC, WETH, UNI_V2_FACTORY),
        (V3_POOL, NEW, WETH, UNI_V3_FACTORY),
        (FAKE_POOL, USDC, WETH, addr(0xFAC)),
    ):
        fake.answer(pool, "token0()", b"", word(t0))
        fake.answer(pool, "token1()", b"", word(t1))
        fake.answer(pool, "factory()", b"", word(factory))
    fake.answer(V3_POOL, "fee()", b"", encode(["uint24"], [3000]))
    fake.answer(
        UNI_V2_FACTORY,
        "getPair(address,address)",
        encode(["address", "address"], [USDC, WETH]),
        word(V2_POOL),
    )
    fake.answer(
        UNI_V3_FACTORY,
        "getPool(address,address,uint24)",
        encode(["address", "address", "uint24"], [NEW, WETH, 3000]),
        word(V3_POOL),
    )
    fake.answer(
        POSITION_MANAGER,
        "poolKeys(bytes25)",
        encode(["bytes25"], [bytes.fromhex(V4_POOL[2:])[:25]]),
        encode(["address", "address", "uint24", "int24", "address"], list(V4_KEY)),
    )
    fake.answer(NEW, "decimals()", b"", encode(["uint8"], [9]))
    fake.answer(NEW, "symbol()", b"", encode(["string"], ["NEW"]))
    fake.answer(NEW, "name()", b"", encode(["string"], ["New Token"]))

    for number, when in ((101, DAY1), (102, DAY1), (103, DAY1), (104, DAY2), (105, DAY2)):
        fake.block(number, when)
    # human via the Universal Router: 2,000 USDC -> 1 WETH
    fake.tx(101, "0x01", HUMAN, UNIVERSAL_ROUTER)
    fake.v2_swap(101, "0x01", V2_POOL, (2_000 * 10**6, 0, 0, 10**18))
    # bot through its own contract: 5 NEW -> 0.5 WETH (pool view: NEW in, WETH out)
    fake.tx(101, "0x02", BOT, BOT_CONTRACT)
    fake.v3_swap(101, "0x02", V3_POOL, 5 * 10**9, -(10**18) // 2)
    # CoW solver settling someone's order: 1 ETH -> 2,000 USDC on v4 (swapper view)
    fake.tx(102, "0x03", SOLVER, COW_SETTLEMENT)
    fake.v4_swap(102, "0x03", V4_POOL, -(10**18), 2_000 * 10**6)
    # the human also hits a pool whose factory is unknown: stored, never counted
    fake.tx(102, "0x04", HUMAN, UNIVERSAL_ROUTER)
    fake.v2_swap(102, "0x04", FAKE_POOL, (10**6, 0, 0, 10**15))
    # a contract pretending to be the PoolManager
    fake.tx(103, "0x05", HUMAN, UNIVERSAL_ROUTER)
    fake.v4_swap(103, "0x05", V4_POOL, -(10**18), 2_000 * 10**6, emitter=addr(0xDEAD))
    # the human again on day two: 1 WETH -> 2,100 USDC
    fake.tx(104, "0x06", HUMAN, UNIVERSAL_ROUTER)
    fake.v2_swap(104, "0x06", V2_POOL, (0, 10**18, 2_100 * 10**6, 0))
    return fake


def settings(**promote: object) -> Settings:
    return Settings(
        discovery={
            "backfill_blocks": 5,
            "logs_block_range": 2,
            "window_days": 100_000,
            "promote": {"min_volume_usd": 1_000, "min_trades": 2, "min_active_days": 2, **promote},
        }
    )


def test_discovery_end_to_end(engine: Engine, session: Session) -> None:
    chain = dex_chain()
    seed_reference_data(engine, chain)
    fake = build_chain()

    result = discover_traders(engine, fake, chain, settings(), EthPrices())

    assert (result.from_block, result.to_block, result.error) == (101, 105, None)
    assert result.swaps == 5 and result.trades == 5  # the spoofed v4 event is dropped
    assert fake.calls["get_logs"] == 3  # windows of 2 blocks: 101-102, 103-104, 105

    trades = {t.tx_hash: t for t in session.scalars(select(DexTrade))}
    human = trades["0x01"]
    assert (human.trader, human.tx_to, human.protocol) == (HUMAN, UNIVERSAL_ROUTER, "uniswap_v2")
    assert (human.token_in, human.amount_in, human.token_out, human.amount_out) == (
        USDC,
        Decimal(2000),
        WETH,
        Decimal(1),
    )
    assert human.amount_usd == Decimal("2000.00000000")  # stablecoin side
    bot = trades["0x02"]
    assert (bot.token_in, bot.amount_in, bot.token_out) == (NEW, Decimal(5), WETH)
    assert bot.amount_usd == Decimal("1000.00000000")  # 0.5 WETH at $2,000
    solver = trades["0x03"]
    assert (solver.protocol, solver.token_in, solver.token_out) == (
        "uniswap_v4",
        NATIVE_TOKEN,
        USDC,
    )
    assert solver.amount_out == Decimal(2000)
    assert trades["0x06"].amount_usd == Decimal("2100.00000000")

    pools = {p.pool_id: p for p in session.scalars(select(DexPool))}
    assert pools[V2_POOL].verified and pools[V3_POOL].verified and pools[V4_POOL].verified
    assert not pools[FAKE_POOL].verified and pools[FAKE_POOL].protocol == "unknown_v2"
    new_token = session.get(Token, (1, NEW))
    assert new_token is not None and (new_token.symbol, new_token.decimals) == ("NEW", 9)

    traders = {t.address: t for t in session.scalars(select(DexTrader))}
    assert set(traders) == {HUMAN, BOT, SOLVER}
    h = traders[HUMAN]
    assert (h.tx_count, h.active_days, h.volume_usd, h.is_bot) == (2, 2, Decimal("4100"), False)
    assert h.router_share == 1.0 and h.protocols == ["uniswap_v2"]
    assert (traders[BOT].is_bot, traders[BOT].bot_reason) == (True, "private_contract")
    assert traders[SOLVER].bot_reason == "settlement_signer"
    assert result.bots == 2

    assert result.promoted == 1
    entry = session.get(WatchlistEntry, (1, HUMAN))
    assert entry is not None and entry.origin == "trader" and entry.hop == 0


def test_discovery_resumes_from_its_cursor(engine: Engine, session: Session) -> None:
    chain = dex_chain()
    seed_reference_data(engine, chain)
    fake = build_chain()
    discover_traders(engine, fake, chain, settings(), None)

    again = discover_traders(engine, fake, chain, settings(), None)
    assert again.from_block == 106 and again.swaps == 0  # nothing new, nothing re-read

    fake.head = 106
    fake.block(106, DAY2)
    fake.tx(106, "0x07", OTHER, UNIVERSAL_ROUTER)
    fake.v2_swap(106, "0x07", V2_POOL, (500 * 10**6, 0, 0, 10**17))
    later = discover_traders(engine, fake, chain, settings(), None)
    assert (later.from_block, later.to_block, later.trades) == (106, 106, 1)
    assert len(session.scalars(select(DexTrade)).all()) == 6


def test_promotion_caps_and_exclusions(engine: Engine, session: Session) -> None:
    chain = dex_chain()
    seed_reference_data(engine, chain)
    with session_scope(engine) as s:
        add_seed(s, 1, HUMAN)  # already watched: never promoted again

    result = discover_traders(engine, build_chain(), chain, settings(), EthPrices())
    assert result.promoted == 0
    assert session.get(WatchlistEntry, (1, HUMAN)).origin == "seed"  # type: ignore[union-attr]

    capped = discover_traders(
        engine, build_chain(), chain, settings(min_trades=1, min_active_days=1, max_total=0), None
    )
    assert capped.promoted == 0


def test_promotion_prefers_steady_varied_traders(engine: Engine, session: Session) -> None:
    chain = dex_chain()
    seed_reference_data(engine, chain)
    fake = build_chain()
    # OTHER trades the new token on both days, for less money than HUMAN's ETH trades
    fake.tx(103, "0x08", OTHER, UNIVERSAL_ROUTER)
    fake.v3_swap(103, "0x08", V3_POOL, 10 * 10**9, -(10**18) // 2)
    fake.tx(105, "0x09", OTHER, UNIVERSAL_ROUTER)
    fake.v3_swap(105, "0x09", V3_POOL, -(5 * 10**9), 10**18 // 4)
    cfg = settings(max_per_run=1, max_total=1)

    first = discover_traders(engine, fake, chain, cfg, EthPrices())

    traders = {t.address: t for t in session.scalars(select(DexTrader))}
    assert traders[HUMAN].traded_tokens == 1  # WETH; USDC is a stablecoin
    assert traders[OTHER].traded_tokens == 2  # NEW and WETH
    assert traders[OTHER].volume_usd < traders[HUMAN].volume_usd  # type: ignore[operator]
    assert first.promoted == 1
    assert session.get(WatchlistEntry, (1, OTHER)) is not None
    assert session.get(WatchlistEntry, (1, HUMAN)) is None

    with session_scope(engine) as s:
        deactivate(s, 1, OTHER)  # rejected or removed: frees its place, never comes back
    again = discover_traders(engine, fake, chain, cfg, EthPrices())
    assert again.promoted == 1
    assert session.get(WatchlistEntry, (1, HUMAN)) is not None
