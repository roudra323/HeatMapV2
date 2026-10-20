"""Per-key state: rate limiter, daily quota, cooldown and health."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Protocol

from heatmap_core.config import ProviderKeyConfig
from heatmap_core.providers.ratelimit import Clock, TokenBucket


class UsageStore(Protocol):
    """Persists per-key daily counters so quotas survive restarts."""

    def requests_today(self, provider: str, key_id: str, day: date) -> int: ...

    def record(
        self,
        provider: str,
        key_id: str,
        day: date,
        *,
        requests: int = 0,
        rate_limited: int = 0,
        errors: int = 0,
    ) -> None: ...

    def flush(self) -> None: ...


class InMemoryUsageStore:
    def __init__(self) -> None:
        self.counts: dict[tuple[str, str, date], list[int]] = {}

    def requests_today(self, provider: str, key_id: str, day: date) -> int:
        return self.counts.get((provider, key_id, day), [0, 0, 0])[0]

    def record(
        self,
        provider: str,
        key_id: str,
        day: date,
        *,
        requests: int = 0,
        rate_limited: int = 0,
        errors: int = 0,
    ) -> None:
        row = self.counts.setdefault((provider, key_id, day), [0, 0, 0])
        row[0] += requests
        row[1] += rate_limited
        row[2] += errors

    def flush(self) -> None:
        return None


@dataclass
class KeyState:
    provider: str
    config: ProviderKeyConfig
    secret: str
    bucket: TokenBucket
    cooldown_until: float = 0.0
    disabled_reason: str | None = None
    day: date | None = None
    used_today: int = 0
    consecutive_errors: int = field(default=0)

    @property
    def key_id(self) -> str:
        return self.config.id

    def roll_day(self, today: date, store: UsageStore) -> None:
        if self.day != today:
            self.day = today
            self.used_today = store.requests_today(self.provider, self.key_id, today)

    def quota_left(self) -> bool:
        quota = self.config.daily_quota
        return quota is None or self.used_today < quota

    def usable(self, monotonic_now: float) -> bool:
        return (
            self.disabled_reason is None
            and monotonic_now >= self.cooldown_until
            and self.quota_left()
        )


class KeyPool:
    """The keys of one provider, served round-robin."""

    def __init__(
        self,
        provider: str,
        keys: list[ProviderKeyConfig],
        clock: Clock,
        store: UsageStore,
        cooldown_s: float,
    ) -> None:
        self.provider = provider
        self.cooldown_s = cooldown_s
        self._clock = clock
        self._store = store
        self._next = 0
        self.keys: list[KeyState] = []
        for cfg in keys:
            secret = cfg.secret()
            if secret:
                self.keys.append(
                    KeyState(
                        provider=provider,
                        config=cfg,
                        secret=secret,
                        bucket=TokenBucket(cfg.rps, clock),
                    )
                )

    def _refresh(self) -> None:
        today = self._clock.utcnow().date()
        for key in self.keys:
            key.roll_day(today, self._store)

    def acquire(self) -> KeyState | None:
        """Return a key that can send a request right now, consuming one token."""
        self._refresh()
        now = self._clock.monotonic()
        count = len(self.keys)
        for offset in range(count):
            key = self.keys[(self._next + offset) % count]
            if key.usable(now) and key.bucket.try_acquire():
                self._next = (self._next + offset + 1) % count
                key.used_today += 1
                self._store.record(self.provider, key.key_id, self._today(), requests=1)
                return key
        return None

    def next_ready_in(self) -> float | None:
        """Seconds until some key can be used, or None if every key is out for the day."""
        self._refresh()
        now = self._clock.monotonic()
        waits: list[float] = []
        for key in self.keys:
            if key.disabled_reason is not None or not key.quota_left():
                continue
            cooldown_wait = max(0.0, key.cooldown_until - now)
            waits.append(max(cooldown_wait, key.bucket.wait_time()))
        return min(waits) if waits else None

    def _today(self) -> date:
        return self._clock.utcnow().date()

    def bench(self, key: KeyState, seconds: float | None = None) -> None:
        key.cooldown_until = self._clock.monotonic() + (
            seconds if seconds is not None else self.cooldown_s
        )
        key.bucket.drain()
        self._store.record(self.provider, key.key_id, self._today(), rate_limited=1)

    def bench_until_tomorrow(self, key: KeyState) -> None:
        now = self._clock.utcnow()
        tomorrow = datetime.combine(now.date() + timedelta(days=1), datetime.min.time(), now.tzinfo)
        key.cooldown_until = self._clock.monotonic() + (tomorrow - now).total_seconds()
        self._store.record(self.provider, key.key_id, self._today(), rate_limited=1)

    def disable(self, key: KeyState, reason: str) -> None:
        key.disabled_reason = reason
        self._store.record(self.provider, key.key_id, self._today(), errors=1)

    def record_error(self, key: KeyState) -> None:
        key.consecutive_errors += 1
        self._store.record(self.provider, key.key_id, self._today(), errors=1)

    def record_success(self, key: KeyState) -> None:
        key.consecutive_errors = 0
