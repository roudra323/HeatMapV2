"""Test doubles shared across test modules."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from heatmap_core.config import Chain, ChainConfig


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


def ethereum(providers: list[str] | None = None) -> Chain:
    return Chain(
        name="ethereum",
        config=ChainConfig(
            chain_id=1,
            providers=providers or [],
            alchemy_network="eth-mainnet",
        ),
    )
