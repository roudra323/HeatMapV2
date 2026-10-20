"""Clock abstraction and a token-bucket rate limiter."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Protocol


class Clock(Protocol):
    def monotonic(self) -> float: ...
    def utcnow(self) -> datetime: ...
    def sleep(self, seconds: float) -> None: ...


class SystemClock:
    def monotonic(self) -> float:
        return time.monotonic()

    def utcnow(self) -> datetime:
        return datetime.now(UTC)

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


class TokenBucket:
    """Allows ``rate`` requests per second with bursts up to ``capacity``."""

    def __init__(self, rate: float, clock: Clock, capacity: float | None = None) -> None:
        if rate <= 0:
            raise ValueError("rate must be positive")
        self.rate = rate
        self.capacity = capacity if capacity is not None else max(1.0, rate)
        self._clock = clock
        self._tokens = self.capacity
        self._updated = clock.monotonic()

    def _refill(self) -> None:
        now = self._clock.monotonic()
        self._tokens = min(self.capacity, self._tokens + (now - self._updated) * self.rate)
        self._updated = now

    def wait_time(self) -> float:
        """Seconds until one token is available (0 if available now)."""
        self._refill()
        if self._tokens >= 1:
            return 0.0
        return (1 - self._tokens) / self.rate

    def try_acquire(self) -> bool:
        self._refill()
        if self._tokens >= 1:
            self._tokens -= 1
            return True
        return False

    def drain(self) -> None:
        """Empty the bucket, e.g. after the server reported a rate limit."""
        self._refill()
        self._tokens = 0
