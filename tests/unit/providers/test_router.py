from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

import pytest

from heatmap_core.config import Chain, ProviderKeyConfig
from heatmap_core.primitives import NATIVE_TOKEN, TransferCategory
from heatmap_core.providers import (
    AllProvidersExhaustedError,
    AuthError,
    InMemoryUsageStore,
    KeyPool,
    ProviderRouter,
    QuotaExceededError,
    RateLimitedError,
    RawTransfer,
    TransferPage,
    TransferRequest,
    TransientProviderError,
)
from tests.support import FakeClock, ethereum

Behaviour = Callable[[str, TransferRequest], TransferPage]


def transfer(provider: str, n: int) -> RawTransfer:
    return RawTransfer(
        chain_id=1,
        tx_hash=f"0x{n:064x}",
        block_number=n,
        block_time=datetime(2026, 1, 1, tzinfo=UTC),
        category=TransferCategory.EXTERNAL,
        from_address="0x" + "a" * 40,
        to_address="0x" + "b" * 40,
        token_address=NATIVE_TOKEN,
        raw_amount=n,
        provider=provider,
    )


class FakeProvider:
    def __init__(self, name: str, behaviour: Behaviour) -> None:
        self.name = name
        self.behaviour = behaviour
        self.calls: list[tuple[str, dict[str, object] | None]] = []

    def supports(self, chain: Chain) -> bool:
        return True

    def fetch_transfers_page(self, key: str, request: TransferRequest) -> TransferPage:
        self.calls.append((key, request.cursor))
        return self.behaviour(key, request)

    def latest_block(self, key: str, chain: Chain) -> int:
        return 100

    def get_code(self, key: str, chain: Chain, address: str) -> str:
        return "0x"


def make_router(
    monkeypatch: pytest.MonkeyPatch,
    providers: dict[str, tuple[FakeProvider, list[tuple[str, float, int | None]]]],
    clock: FakeClock,
) -> ProviderRouter:
    store = InMemoryUsageStore()
    pools = {}
    priorities = {}
    for priority, (name, (_, keys)) in enumerate(providers.items()):
        configs = []
        for key_id, rps, quota in keys:
            env = f"TEST_{key_id.upper().replace('-', '_')}"
            monkeypatch.setenv(env, key_id)
            configs.append(ProviderKeyConfig(id=key_id, env=env, rps=rps, daily_quota=quota))
        pools[name] = KeyPool(name, configs, clock, store, cooldown_s=60)
        priorities[name] = priority
    return ProviderRouter(
        {name: p for name, (p, _) in providers.items()},
        pools,
        priorities,
        clock=clock,
        store=store,
    )


def single_page(key: str, request: TransferRequest) -> TransferPage:
    return TransferPage([transfer(key, 1)])


def test_rate_limited_key_fails_over_to_next_key(monkeypatch: pytest.MonkeyPatch) -> None:
    def behaviour(key: str, request: TransferRequest) -> TransferPage:
        if key == "a-1":
            raise RateLimitedError("429")
        return single_page(key, request)

    clock = FakeClock()
    provider = FakeProvider("a", behaviour)
    router = make_router(
        monkeypatch, {"a": (provider, [("a-1", 5, None), ("a-2", 5, None)])}, clock
    )

    result = router.fetch_transfers(ethereum(), "0x" + "a" * 40, 0, 10)

    assert [t.provider for t in result] == ["a-2"]
    assert router.pools["a"].keys[0].cooldown_until == 60


def test_fails_over_to_lower_priority_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    def limited(key: str, request: TransferRequest) -> TransferPage:
        raise QuotaExceededError("monthly capacity")

    clock = FakeClock()
    primary = FakeProvider("primary", limited)
    backup = FakeProvider("backup", single_page)
    router = make_router(
        monkeypatch,
        {
            "primary": (primary, [("p-1", 5, None)]),
            "backup": (backup, [("b-1", 5, None)]),
        },
        clock,
    )

    result = router.fetch_transfers(ethereum(), "0x" + "a" * 40, 0, 10)

    assert [t.provider for t in result] == ["b-1"]
    # quota errors bench the key until the next UTC day (12:00 -> 24:00)
    assert router.pools["primary"].keys[0].cooldown_until == 12 * 3600


def test_all_keys_exhausted_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    def limited(key: str, request: TransferRequest) -> TransferPage:
        raise QuotaExceededError("daily limit")

    clock = FakeClock()
    router = make_router(
        monkeypatch, {"a": (FakeProvider("a", limited), [("a-1", 5, None)])}, clock
    )
    with pytest.raises(AllProvidersExhaustedError):
        router.fetch_transfers(ethereum(), "0x" + "a" * 40, 0, 10)


def test_cooldown_expiry_restores_key(monkeypatch: pytest.MonkeyPatch) -> None:
    state = {"limited": True}

    def behaviour(key: str, request: TransferRequest) -> TransferPage:
        if state["limited"]:
            state["limited"] = False
            raise RateLimitedError("429", retry_after=5)
        return single_page(key, request)

    clock = FakeClock()
    router = make_router(
        monkeypatch, {"a": (FakeProvider("a", behaviour), [("a-1", 5, None)])}, clock
    )
    result = router.fetch_transfers(ethereum(), "0x" + "a" * 40, 0, 10)
    assert len(result) == 1
    assert clock.sleeps == [5]


def test_daily_quota_is_enforced_locally(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = FakeClock()
    a = FakeProvider("a", single_page)
    b = FakeProvider("b", single_page)
    router = make_router(
        monkeypatch,
        {"a": (a, [("a-1", 100, 2)]), "b": (b, [("b-1", 100, None)])},
        clock,
    )
    for _ in range(3):
        router.latest_block(ethereum())
    assert router.pools["a"].keys[0].used_today == 2
    assert router.pools["b"].keys[0].used_today == 1


def test_auth_error_disables_key(monkeypatch: pytest.MonkeyPatch) -> None:
    def behaviour(key: str, request: TransferRequest) -> TransferPage:
        if key == "a-1":
            raise AuthError("invalid api key")
        return single_page(key, request)

    clock = FakeClock()
    router = make_router(
        monkeypatch,
        {"a": (FakeProvider("a", behaviour), [("a-1", 5, None), ("a-2", 5, None)])},
        clock,
    )
    router.fetch_transfers(ethereum(), "0x" + "a" * 40, 0, 10)
    assert router.pools["a"].keys[0].disabled_reason == "invalid api key"


def test_transient_errors_retry_with_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    failures = {"left": 2}

    def behaviour(key: str, request: TransferRequest) -> TransferPage:
        if failures["left"]:
            failures["left"] -= 1
            raise TransientProviderError("502")
        return single_page(key, request)

    clock = FakeClock()
    router = make_router(
        monkeypatch, {"a": (FakeProvider("a", behaviour), [("a-1", 100, None)])}, clock
    )
    assert len(router.fetch_transfers(ethereum(), "0x" + "a" * 40, 0, 10)) == 1
    assert clock.sleeps == [2.0, 4.0]


def test_pagination_stays_on_provider_and_passes_cursor(monkeypatch: pytest.MonkeyPatch) -> None:
    def behaviour(key: str, request: TransferRequest) -> TransferPage:
        page = (request.cursor or {}).get("page", 0)
        assert isinstance(page, int)
        nxt = {"page": page + 1} if page < 2 else None
        return TransferPage([transfer(key, page)], next_cursor=nxt)

    clock = FakeClock()
    provider = FakeProvider("a", behaviour)
    router = make_router(monkeypatch, {"a": (provider, [("a-1", 100, None)])}, clock)
    result = router.fetch_transfers(ethereum(), "0x" + "a" * 40, 0, 10)
    assert len(result) == 3
    assert [c for _, c in provider.calls] == [None, {"page": 1}, {"page": 2}]


def test_switching_provider_mid_pagination_restarts_range(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def primary_behaviour(key: str, request: TransferRequest) -> TransferPage:
        if request.cursor is None:
            return TransferPage([transfer("primary", 1)], next_cursor={"page": 1})
        raise QuotaExceededError("monthly capacity")

    def backup_behaviour(key: str, request: TransferRequest) -> TransferPage:
        assert request.cursor is None  # never receives the other provider's cursor
        return TransferPage([transfer("backup", 1), transfer("backup", 2)])

    clock = FakeClock()
    router = make_router(
        monkeypatch,
        {
            "primary": (FakeProvider("primary", primary_behaviour), [("p-1", 100, None)]),
            "backup": (FakeProvider("backup", backup_behaviour), [("b-1", 100, None)]),
        },
        clock,
    )
    result = router.fetch_transfers(ethereum(), "0x" + "a" * 40, 0, 10)
    assert {t.provider for t in result} == {"backup"}
    assert len(result) == 2
    assert len({t.uid for t in result}) == 2


def test_waits_when_all_keys_are_throttled_locally(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = FakeClock()
    router = make_router(
        monkeypatch, {"a": (FakeProvider("a", single_page), [("a-1", 1, None)])}, clock
    )
    router.latest_block(ethereum())
    router.latest_block(ethereum())
    assert clock.sleeps == [1.0]
