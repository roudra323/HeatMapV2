"""Deterministic synthetic dataset for trying the stack without provider keys.

It creates a handful of behaviour cohorts (a sybil farm, stablecoin/CEX users,
NFT traders, DEX traders, a whale) plus spam airdrops, then runs every stage.
"""

from __future__ import annotations

import random
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import Engine

from heatmap_core import pipeline
from heatmap_core.config import Chain, Settings
from heatmap_core.db.session import session_scope
from heatmap_core.ingestion.watchlist import add_seed
from heatmap_core.primitives import NATIVE_TOKEN, TransferCategory
from heatmap_core.providers.base import RawTransfer, assign_uids

BINANCE = "0x28c6c06298d514db089934071355e5743bf21d60"
COINBASE = "0xa9d1e08c7793af67e9d92fe308d5697fb81d3e43"
UNISWAP = "0x3fc91a3afd70395cd496c647d5a6cc9d4b2b7fad"
SEAPORT = "0x0000000000000068f116a894984e2db1123eb395"
AAVE = "0x87870bca3f3fd6335c3f4ce8392d69350b4fa4e2"
USDC = "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"
USDT = "0xdac17f958d2ee523a2206206994597c13d831ec7"
WETH = "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"
PEPE = "0x6982508145454ce325ddbe47a25d4ec3d2311933"
FAKE_USDT = "0x" + "5" * 40
NFT_COLLECTION = "0x" + "a1" * 20

TOKENS = {
    USDC: ("USDC", 6, 1.0),
    USDT: ("USDT", 6, 1.0),
    WETH: ("WETH", 18, 3000.0),
    PEPE: ("PEPE", 18, 0.00001),
    NATIVE_TOKEN: ("ETH", 18, 3000.0),
}


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
        contracts = {UNISWAP, SEAPORT, AAVE, USDC, USDT, WETH, PEPE, NFT_COLLECTION, FAKE_USDT}
        return "0x6080" if address in contracts else "0x"


class StaticPrices:
    name = "demo"

    def daily_prices(self, price_id: str, start: date, end: date) -> dict[date, Decimal]:
        price = {"ethereum": 3000.0, "weth": 3000.0, "pepe": 0.00001}.get(price_id)
        if price is None:
            return {}
        days = (end - start).days + 1
        return {start + timedelta(days=i): Decimal(str(price)) for i in range(days)}


class _Builder:
    def __init__(self, now: datetime, seed: int) -> None:
        self.rng = random.Random(seed)
        self.start = now - timedelta(days=180)
        self.transfers: list[RawTransfer] = []
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
    ) -> None:
        self.block += 1
        sym, decimals, _ = TOKENS.get(token, (symbol or "NFT", 0, 0.0))
        if category is None:
            category = (
                TransferCategory.EXTERNAL if token == NATIVE_TOKEN else TransferCategory.ERC20
            )
        raw = 1 if category.is_nft else int(Decimal(str(amount)) * 10**decimals)
        self.transfers.append(
            RawTransfer(
                chain_id=1,
                tx_hash=tx or f"0x{self.block:064x}",
                block_number=self.block,
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


def build_demo_transfers(now: datetime, seed: int = 7) -> tuple[list[RawTransfer], list[str]]:
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
        for _ in range(b.rng.randint(40, 70)):
            when = b.at(b.rng.uniform(1, 179))
            b.add(when, wallet, UNISWAP, WETH, b.rng.uniform(0.1, 1))
            b.add(when + timedelta(seconds=2), UNISWAP, wallet, PEPE, b.rng.uniform(1e6, 1e8))

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

    return sorted(b.transfers, key=lambda t: t.block_number), seeds


def run_demo(
    engine: Engine, chain: Chain, settings: Settings, *, now: datetime | None = None
) -> dict[str, object]:
    now = now or datetime.now(UTC)
    transfers, seeds = build_demo_transfers(now)
    source = StaticSource(
        transfers, head=transfers[-1].block_number + chain.config.confirmations + 1
    )
    prices = StaticPrices()
    pipeline.seed_reference_data(engine, chain)
    with session_scope(engine) as session:
        for wallet in seeds:
            add_seed(session, chain.chain_id, wallet, note="demo")

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
        "wallets_with_features": features.wallets_by_window,
        "tags": models.tags,
        "clusters": models.clusters,
    }
