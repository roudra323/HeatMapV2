"""Test doubles shared across test modules."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

from heatmap_core.config import Chain, ChainConfig
from heatmap_core.primitives import NATIVE_TOKEN, TransferCategory
from heatmap_core.providers import RawTransfer, assign_uids


class FakeClock:
    def __init__(self, start: datetime | None = None) -> None:
        self.t = 0.0
        self.start = start or datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.t

    def utcnow(self) -> datetime:
        return self.start + timedelta(seconds=self.t)

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.t += seconds

    def advance(self, seconds: float) -> None:
        self.t += seconds


def ethereum(providers: list[str] | None = None, **overrides: object) -> Chain:
    return Chain(
        name="ethereum",
        config=ChainConfig.model_validate(
            {
                "chain_id": 1,
                "providers": providers or [],
                "alchemy_network": "eth-mainnet",
                "confirmations": 0,
                "reorg_window": 10,
                **overrides,
            }
        ),
    )


def addr(n: int) -> str:
    """Deterministic test address."""
    return f"0x{n:040x}"


class FakeSource:
    """In-memory stand-in for ``ProviderRouter`` used by ingestion tests."""

    def __init__(self, transfers: list[RawTransfer] | None = None, head: int = 1_000) -> None:
        self.transfers = transfers or []
        self.head = head
        self.calls: list[tuple[str, int, int]] = []
        self.contracts: set[str] = set()

    def fetch_transfers(
        self, chain: Chain, address: str, from_block: int, to_block: int
    ) -> list[RawTransfer]:
        self.calls.append((address, from_block, to_block))
        selected = [
            replace(t)
            for t in self.transfers
            if from_block <= t.block_number <= to_block
            and address in (t.from_address, t.to_address)
        ]
        return assign_uids(selected)

    def latest_block(self, chain: Chain) -> int:
        return self.head

    def get_code(self, chain: Chain, address: str) -> str:
        return "0x6080" if address in self.contracts else "0x"


def raw(
    block: int,
    src: str,
    dst: str,
    *,
    amount: int = 10**18,
    category: TransferCategory = TransferCategory.EXTERNAL,
    token: str = NATIVE_TOKEN,
    symbol: str | None = "ETH",
    decimals: int | None = 18,
    tx: str | None = None,
    token_id: str | None = None,
    name: str | None = None,
    time: datetime | None = None,
) -> RawTransfer:
    return RawTransfer(
        chain_id=1,
        tx_hash=tx or f"0x{block:064x}",
        block_number=block,
        block_time=time or datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=block),
        category=category,
        from_address=src,
        to_address=dst,
        token_address=token,
        raw_amount=amount,
        provider="fake",
        token_id=token_id,
        decimals=decimals,
        symbol=symbol,
        token_name=name,
    )
