"""Deterministic synthetic dataset for trying the stack without provider keys.

It creates a handful of behaviour cohorts (a sybil farm, stablecoin/CEX users,
NFT traders, DEX traders, a whale) plus spam airdrops. It also records DEX
swaps: human traders of every size, and one bot of each kind the detector
knows (MEV, arbitrage, solver, batch executor, high frequency). Discovery
scores and promotes the traders, then every other stage runs.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import Engine
from sqlalchemy.dialects.postgresql import insert

from heatmap_core import pipeline
from heatmap_core.config import Chain, Settings
from heatmap_core.db.models import DexPool, DexTrade, Token
from heatmap_core.db.session import insert_batches, session_scope
from heatmap_core.dex.traders import promote_traders, refresh_traders
from heatmap_core.ingestion.watchlist import add_seed
from heatmap_core.primitives import NATIVE_TOKEN, TransferCategory
from heatmap_core.providers.base import RawTransfer, assign_uids

BINANCE = "0x28c6c06298d514db089934071355e5743bf21d60"
COINBASE = "0xa9d1e08c7793af67e9d92fe308d5697fb81d3e43"
UNISWAP = "0x3fc91a3afd70395cd496c647d5a6cc9d4b2b7fad"
ONEINCH = "0x111111125421ca6dc452d289314280a0f8842a65"
COW_SETTLEMENT = "0x9008d19f58aabd9ed0d60971565aa8510560ab41"
SEAPORT = "0x0000000000000068f116a894984e2db1123eb395"
AAVE = "0x87870bca3f3fd6335c3f4ce8392d69350b4fa4e2"
USDC = "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"
USDT = "0xdac17f958d2ee523a2206206994597c13d831ec7"
WETH = "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"
PEPE = "0x6982508145454ce325ddbe47a25d4ec3d2311933"
UNI = "0x1f9840a85d5af5bf1d1762f925bdaddc4201f984"
LINK = "0x514910771af9ca656af840dff83e8264ecf986ca"
SHIB = "0x95ad61b0a150d79219dcf64e1e6cc01f0b64c4ce"
LDO = "0x5a98fcbea516cf06857215779fd812ca3bef1b32"
FAKE_USDT = "0x" + "5" * 40
NFT_COLLECTION = "0x" + "a1" * 20
MEV_CONTRACT = "0x" + "9b" * 20

TOKENS = {
    USDC: ("USDC", 6, 1.0),
    USDT: ("USDT", 6, 1.0),
    WETH: ("WETH", 18, 3000.0),
    PEPE: ("PEPE", 18, 0.00001),
    UNI: ("UNI", 18, 9.0),
    LINK: ("LINK", 18, 18.0),
    SHIB: ("SHIB", 18, 0.00002),
    LDO: ("LDO", 18, 1.8),
    NATIVE_TOKEN: ("ETH", 18, 3000.0),
}
QUOTES = {WETH, USDC, USDT, NATIVE_TOKEN}
ALTS = [PEPE, UNI, LINK, SHIB, LDO]
PROTOCOLS = ["uniswap_v3", "uniswap_v3", "uniswap_v2", "uniswap_v4", "sushiswap"]


def demo_address(cohort: int, n: int) -> str:
    return f"0x{cohort:02x}{'d' * 30}{n:08x}"


class StaticSource:
    """A ``TransferSource`` backed by a fixed list of transfers."""

    def __init__(self, transfers: list[RawTransfer], head: int) -> None:
        self.transfers = transfers
        self.head = head

    def fetch_transfers(
        self, chain: Chain, address: str, from_block: int, to_block: int
    ) -> list[RawTransfer]:
        return assign_uids(
            [
                replace(t)
                for t in self.transfers
                if from_block <= t.block_number <= to_block
                and address in (t.from_address, t.to_address)
            ]
        )

    def latest_block(self, chain: Chain) -> int:
        return self.head

    def get_code(self, chain: Chain, address: str) -> str:
        contracts = {
            UNISWAP,
            ONEINCH,
            COW_SETTLEMENT,
            SEAPORT,
            AAVE,
            NFT_COLLECTION,
            FAKE_USDT,
            MEV_CONTRACT,
            *TOKENS,
        } - {NATIVE_TOKEN}
        return "0x6080" if address in contracts else "0x"

    def get_transaction_count(self, chain: Chain, address: str) -> int:
        return sum(t.from_address == address for t in self.transfers)


class StaticPrices:
    name = "demo"

    def price_key(self, chain: Chain, token: Token) -> str | None:
        return token.price_id

    def daily_prices(self, price_id: str, start: date, end: date) -> dict[date, Decimal]:
        price = {
            "ethereum": 3000.0,
            "weth": 3000.0,
            "pepe": 0.00001,
            "uniswap": 9.0,
            "chainlink": 18.0,
            "shiba-inu": 0.00002,
            "lido-dao": 1.8,
        }.get(price_id)
        if price is None:
            return {}
        days = (end - start).days + 1
        return {start + timedelta(days=i): Decimal(str(price)) for i in range(days)}


class _Builder:
    def __init__(self, now: datetime, seed: int) -> None:
        self.rng = random.Random(seed)
        # Midnight, so the hours given to ``at`` are UTC hours of the day.
        self.start = (now - timedelta(days=180)).replace(hour=0, minute=0, second=0, microsecond=0)
        self.transfers: list[RawTransfer] = []
        self.trades: list[dict[str, Any]] = []
        self.pools: dict[tuple[str, str], str] = {}
        self.block = 20_000_000

    def at(self, day: float, hour: float | None = None) -> datetime:
        hour = self.rng.uniform(0, 24) if hour is None else hour
        return self.start + timedelta(days=day, hours=hour)

    def add(
        self,
        when: datetime,
        src: str,
        dst: str,
        token: str = NATIVE_TOKEN,
        amount: float = 0.1,
        category: TransferCategory | None = None,
        token_id: str | None = None,
        symbol: str | None = None,
        tx: str | None = None,
        block: int | None = None,
    ) -> None:
        if block is None:
            self.block += 1
            block = self.block
        sym, decimals, _ = TOKENS.get(token, (symbol or "NFT", 0, 0.0))
        if category is None:
            category = (
                TransferCategory.EXTERNAL if token == NATIVE_TOKEN else TransferCategory.ERC20
            )
        raw = 1 if category.is_nft else int(Decimal(str(amount)) * 10**decimals)
        self.transfers.append(
            RawTransfer(
                chain_id=1,
                tx_hash=tx or f"0x{block:064x}",
                block_number=block,
                block_time=when,
                category=category,
                from_address=src,
                to_address=dst,
                token_address=token,
                raw_amount=raw,
                provider="demo",
                token_id=token_id,
                decimals=None if category.is_nft else decimals,
                symbol=symbol or sym,
            )
        )

    def pool(self, protocol: str, token: str) -> str:
        """A WETH/``token`` pool (``token`` is USDC for the WETH/USDC pair)."""
        key = (protocol, token)
        if key not in self.pools:
            n = len(self.pools)
            width = 56 if protocol == "uniswap_v4" else 32  # v4 pools are 32-byte PoolIds
            self.pools[key] = f"0x{'b' * width}{n:08x}"
        return self.pools[key]

    def swap(
        self,
        when: datetime,
        trader: str,
        sell: str,
        sell_amount: float,
        buy: str,
        buy_amount: float,
        *,
        protocol: str = "uniswap_v3",
        via: str = UNISWAP,
        legs: bool = False,
        tx: str | None = None,
        block: int | None = None,
        log_index: int = 0,
    ) -> None:
        """One swap signed by ``trader`` through ``via``; ``legs`` also records its transfers."""
        if block is None:
            self.block += 1
            block = self.block
        tx = tx or f"0x{block:064x}"
        alt = buy if sell in QUOTES else sell
        if alt in QUOTES:  # WETH/USDC
            alt = USDC
        priced_side = (sell, sell_amount) if sell in QUOTES else (buy, buy_amount)
        usd = priced_side[1] * TOKENS[priced_side[0]][2]

        def raw(token: str, amount: float) -> int:
            return int(Decimal(str(amount)) * 10 ** TOKENS[token][1])

        self.trades.append(
            {
                "chain_id": 1,
                "block_number": block,
                "block_time": when,
                "tx_hash": tx,
                "log_index": log_index,
                "pool_id": self.pool(protocol, alt),
                "protocol": protocol,
                "trader": trader,
                "tx_to": via,
                "token_in": sell,
                "token_out": buy,
                "amount_in_raw": raw(sell, sell_amount),
                "amount_out_raw": raw(buy, buy_amount),
                "amount_in": Decimal(str(sell_amount)),
                "amount_out": Decimal(str(buy_amount)),
                "amount_usd": Decimal(f"{usd:.2f}"),
            }
        )
        if legs:
            self.add(when, trader, via, sell, sell_amount, tx=tx, block=block)
            self.add(when, via, trader, buy, buy_amount, tx=tx, block=block)

    def alt_amount(self, usd: float, token: str) -> float:
        """How much of ``token`` ``usd`` buys, with a little price noise."""
        return round(usd / TOKENS[token][2] * self.rng.uniform(0.97, 1.03), 6)


@dataclass
class DemoData:
    transfers: list[RawTransfer]
    seeds: list[str]
    trades: list[dict[str, Any]]
    pools: dict[tuple[str, str], str]  # (protocol, token paired with WETH) -> pool id


def build_demo_data(now: datetime, seed: int = 7) -> DemoData:
    b = _Builder(now, seed)
    seeds: list[str] = []

    # Cohort 1: sybil farm funded by one private wallet, acting in lockstep.
    farmer = demo_address(0xF, 0)
    farm = [demo_address(1, i) for i in range(6)]
    b.add(b.at(0, 9), BINANCE, farmer, amount=5)
    for day in range(5, 150, 7):
        when = b.at(day, 14)
        for i, wallet in enumerate(farm):
            if day == 5:
                b.add(b.at(1, 10 + i * 0.01), farmer, wallet, amount=0.2)
            b.add(when + timedelta(seconds=20 * i), wallet, UNISWAP, amount=0.01)
            b.add(when + timedelta(seconds=20 * i + 5), wallet, AAVE, USDC, amount=10)
    seeds += farm

    # Cohort 2: stablecoin users who cash in and out through exchanges.
    for i in range(5):
        wallet = demo_address(2, i)
        seeds.append(wallet)
        for _ in range(b.rng.randint(25, 40)):
            offset = b.rng.uniform(0, 175)
            if b.rng.random() < 0.4:
                b.add(
                    b.at(offset, b.rng.uniform(8, 18)),
                    COINBASE,
                    wallet,
                    USDC,
                    b.rng.uniform(100, 5000),
                )
            else:
                friend = demo_address(0x12, b.rng.randint(0, 3))
                b.add(
                    b.at(offset, b.rng.uniform(8, 18)), wallet, friend, USDT, b.rng.uniform(20, 800)
                )

    # Cohort 3: NFT traders, active at night.
    for i in range(4):
        wallet = demo_address(3, i)
        seeds.append(wallet)
        b.add(b.at(1), BINANCE, wallet, amount=2)
        for k in range(b.rng.randint(15, 30)):
            when = b.at(b.rng.uniform(2, 178), b.rng.uniform(0, 5))
            b.add(when, wallet, SEAPORT, amount=b.rng.uniform(0.05, 0.5))
            b.add(
                when + timedelta(seconds=1),
                SEAPORT,
                wallet,
                NFT_COLLECTION,
                category=TransferCategory.ERC721,
                token_id=str(i * 100 + k),
                symbol="DEMOPUNK",
            )

    # Cohort 4: DEX traders swapping memecoins.
    for i in range(4):
        wallet = demo_address(4, i)
        seeds.append(wallet)
        b.add(b.at(0), COINBASE, wallet, amount=3)
        for k in range(b.rng.randint(40, 70)):
            when = b.at(b.rng.uniform(1, 179))
            b.swap(
                when,
                wallet,
                WETH,
                b.rng.uniform(0.1, 1),
                PEPE,
                b.rng.uniform(1e6, 1e8),
                protocol=PROTOCOLS[k % len(PROTOCOLS)],
                legs=True,
            )

    # A whale moving size between exchanges and a cold wallet.
    whale, cold = demo_address(5, 0), demo_address(0x15, 0)
    seeds.append(whale)
    for _ in range(20):
        b.add(b.at(b.rng.uniform(0, 175)), BINANCE, whale, USDC, b.rng.uniform(2e5, 2e6))
        b.add(b.at(b.rng.uniform(0, 175)), whale, cold, WETH, b.rng.uniform(50, 400))

    # Spam: homoglyph token airdrop and zero-value poisoning.
    spammer = demo_address(0xE, 0)
    for wallet in seeds:
        # "USD" + Cyrillic Te: a look-alike of USDT
        fake_symbol = "USD" + chr(0x0422)
        b.add(
            b.at(100, 3), spammer, wallet, FAKE_USDT, 1000, symbol=fake_symbol, tx="0x" + "e" * 64
        )
        b.add(b.at(120, 4), wallet, demo_address(0xE, 1), USDT, amount=0)

    add_dex_cohorts(b)
    return DemoData(
        transfers=sorted(b.transfers, key=lambda t: t.block_number),
        seeds=seeds,
        trades=b.trades,
        pools=b.pools,
    )


def add_dex_cohorts(b: _Builder) -> None:
    """Traders that discovery finds in swaps, rather than seeds, plus the bots it filters out.

    Days count from 180 days ago, so day 150 onwards falls in the 30-day window.
    """
    # Cohort 6: active traders with favourite tokens and trading hours.
    # Four of them are funded by, and pay out to, the same private desk.
    desk, desk_treasury = demo_address(0x16, 0), demo_address(0x16, 1)
    b.add(b.at(120, 10), BINANCE, desk, amount=60)
    for i in range(10):
        trader = demo_address(6, i)
        hour = b.rng.choice([7.0, 13.0, 18.0])
        funder = desk if i < 4 else b.rng.choice([BINANCE, COINBASE])
        b.add(b.at(130 + i, hour), funder, trader, amount=round(b.rng.uniform(3, 12), 3))
        favourites = b.rng.sample(ALTS, b.rng.randint(2, 4))
        for day in sorted(b.rng.sample(range(140, 179), b.rng.randint(6, 18))):
            for _ in range(b.rng.randint(1, 3)):
                when = b.at(day, hour + b.rng.uniform(0, 4))
                token = b.rng.choice(favourites)
                usd = b.rng.uniform(800, 9000)
                protocol = b.rng.choice(PROTOCOLS)
                via = ONEINCH if b.rng.random() < 0.25 else UNISWAP
                if b.rng.random() < 0.65:
                    sell, buy = WETH if b.rng.random() < 0.7 else USDC, token
                else:
                    sell, buy = token, WETH
                sold = b.alt_amount(usd, sell) if sell in ALTS else round(usd / TOKENS[sell][2], 6)
                got = b.alt_amount(usd, buy) if buy in ALTS else round(usd / TOKENS[buy][2], 6)
                b.swap(when, trader, sell, sold, buy, got, protocol=protocol, via=via, legs=True)
        if i < 4:
            b.add(b.at(b.rng.uniform(165, 178)), trader, desk_treasury, USDC, 5000)

    # Cohort 7: occasional small traders, too small or too new to promote.
    for i in range(8):
        trader = demo_address(7, i)
        for _ in range(b.rng.randint(1, 4)):
            token, usd = b.rng.choice(ALTS), b.rng.uniform(40, 900)
            b.swap(
                b.at(b.rng.uniform(152, 179)),
                trader,
                WETH,
                round(usd / TOKENS[WETH][2], 6),
                token,
                b.alt_amount(usd, token),
                protocol=b.rng.choice(PROTOCOLS),
            )

    # Cohort 8: a whale buying size through an aggregator, a few days a month.
    whale = demo_address(8, 0)
    b.add(b.at(140, 9), COINBASE, whale, USDC, 4_000_000)
    for day in (150, 156, 163, 171, 177):
        for token in (LINK, UNI):
            usd = round(b.rng.uniform(150_000, 600_000), 2)
            b.swap(
                b.at(day, b.rng.uniform(13, 16)),
                whale,
                USDC,
                usd,
                token,
                b.alt_amount(usd, token),
                via=ONEINCH,
                legs=True,
            )

    add_dex_bots(b)


def add_dex_bots(b: _Builder) -> None:
    """One bot of each kind ``dex.traders.bot_reason`` recognises."""

    def buy(when: datetime, bot: str, token: str, usd: float, **kw: Any) -> None:
        pay = kw.pop("pay", WETH)
        paid = round(usd / TOKENS[pay][2], 6)
        b.swap(when, bot, pay, paid, token, b.alt_amount(usd, token), **kw)

    def window_time() -> datetime:
        return b.at(b.rng.uniform(150, 179))

    # MEV: two signers trading through their own contract.
    for _ in range(160):
        bot = demo_address(9, b.rng.randint(0, 1))
        token = b.rng.choice([PEPE, SHIB])
        buy(window_time(), bot, token, b.rng.uniform(2_000, 40_000), via=MEV_CONTRACT)

    # Arbitrage: buy and sell the same token back in one transaction.
    for _ in range(60):
        b.block += 1
        when, token = window_time(), b.rng.choice(ALTS)
        eth = round(b.rng.uniform(2, 20), 6)
        amount = b.alt_amount(eth * TOKENS[WETH][2], token)
        arb = demo_address(9, 2)
        b.swap(when, arb, WETH, eth, token, amount, block=b.block, log_index=0)
        b.swap(
            when,
            arb,
            token,
            amount,
            WETH,
            round(eth * 1.004, 6),
            protocol="sushiswap",
            block=b.block,
            log_index=1,
        )

    # Solver: settles other people's orders through CoW Protocol.
    for _ in range(45):
        b.block += 1
        when = window_time()
        for k in range(b.rng.randint(2, 5)):
            token, usd = b.rng.choice(ALTS), b.rng.uniform(500, 20_000)
            buy(
                when,
                demo_address(9, 3),
                token,
                usd,
                pay=USDC,
                via=COW_SETTLEMENT,
                block=b.block,
                log_index=k,
            )

    # Batch executor: eight swaps packed into every transaction.
    for _ in range(30):
        b.block += 1
        when = window_time()
        for k in range(8):
            token, pay = ALTS[k % len(ALTS)], (WETH, USDC)[k % 2]
            buy(
                when,
                demo_address(9, 4),
                token,
                b.rng.uniform(300, 3_000),
                pay=pay,
                via=ONEINCH,
                block=b.block,
                log_index=k,
            )

    # High frequency: hundreds of small trades a day.
    for day in (176, 177, 178):
        for _ in range(170):
            buy(b.at(day), demo_address(9, 5), PEPE, b.rng.uniform(50, 400))


def run_demo(
    engine: Engine, chain: Chain, settings: Settings, *, now: datetime | None = None
) -> dict[str, object]:
    now = now or datetime.now(UTC)
    data = build_demo_data(now)
    transfers, seeds = data.transfers, data.seeds
    source = StaticSource(
        transfers, head=transfers[-1].block_number + chain.config.confirmations + 1
    )
    prices = StaticPrices()
    pipeline.seed_reference_data(engine, chain)
    with session_scope(engine) as session:
        for wallet in seeds:
            add_seed(session, chain.chain_id, wallet, note="demo")
    load_swaps(engine, chain, data)
    # Discovery without the scan: score the stored swaps, promote the best traders.
    traders = refresh_traders(engine, chain, settings, now=now)
    promoted = promote_traders(engine, chain, settings)

    for _ in range(2):  # second round syncs the neighbours found in the first
        pipeline.sync_tracked_wallets(engine, source, chain)
        pipeline.normalize(engine, chain, settings, prices)
        pipeline.refresh_graph(engine, chain, settings)

    pipeline.compute_behaviour(engine, chain, settings, now - timedelta(days=7))
    features = pipeline.compute_behaviour(engine, chain, settings, now)
    models = pipeline.label_wallets(engine, chain, settings)
    return {
        "seeds": len(seeds),
        "transfers": len(transfers),
        "dex_trades": len(data.trades),
        "traders": traders.traders,
        "bots": traders.bots,
        "promoted": len(promoted),
        "wallets_with_features": features.wallets_by_window,
        "tags": models.tags,
        "clusters": models.clusters,
    }


def load_swaps(engine: Engine, chain: Chain, data: DemoData) -> None:
    """Store the demo pools as verified, and the swaps as already valued trades."""
    pools = [
        {
            "chain_id": chain.chain_id,
            "pool_id": pool_id,
            "protocol": protocol,
            "token0": WETH,
            "token1": token,
            "fee": 3000,
            "verified": True,
        }
        for (protocol, token), pool_id in data.pools.items()
    ]
    trades = [{**t, "chain_id": chain.chain_id} for t in data.trades]
    with session_scope(engine) as session:
        session.execute(insert(DexPool).values(pools).on_conflict_do_nothing())
        for batch in insert_batches(trades):
            session.execute(insert(DexTrade).values(batch).on_conflict_do_nothing())
