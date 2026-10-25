"""Routes requests across providers and keys, failing over on limits and errors."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from functools import partial
from typing import Any, TypeVar

import httpx

from heatmap_core.config import Chain, Settings
from heatmap_core.logging import get_logger
from heatmap_core.providers.alchemy import AlchemyProvider
from heatmap_core.providers.base import (
    RawTransfer,
    TransferPage,
    TransferProvider,
    TransferRequest,
    assign_uids,
)
from heatmap_core.providers.errors import (
    AllProvidersExhaustedError,
    AuthError,
    QuotaExceededError,
    RateLimitedError,
    TransientProviderError,
    UnsupportedError,
)
from heatmap_core.providers.etherscan import EtherscanProvider
from heatmap_core.providers.keypool import InMemoryUsageStore, KeyPool, UsageStore
from heatmap_core.providers.ratelimit import Clock, SystemClock

T = TypeVar("T")
log = get_logger(__name__)

# Waiting longer than this for a key is pointless inside one request.
MAX_WAIT_S = 30.0


class ProviderRouter:
    def __init__(
        self,
        providers: dict[str, TransferProvider],
        pools: dict[str, KeyPool],
        priorities: dict[str, int],
        *,
        max_retries: dict[str, int] | None = None,
        clock: Clock | None = None,
        store: UsageStore | None = None,
    ) -> None:
        self.providers = providers
        self.pools = pools
        self.priorities = priorities
        self.max_retries = max_retries or {}
        self.clock = clock or SystemClock()
        self.store = store or InMemoryUsageStore()

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        *,
        http_client: httpx.Client | None = None,
        clock: Clock | None = None,
        store: UsageStore | None = None,
    ) -> ProviderRouter:
        clock = clock or SystemClock()
        store = store or InMemoryUsageStore()
        providers: dict[str, TransferProvider] = {}
        pools: dict[str, KeyPool] = {}
        for name, cfg in settings.providers.items():
            client = http_client or httpx.Client(timeout=cfg.timeout_s)
            provider: TransferProvider
            if cfg.kind == "alchemy":
                provider = AlchemyProvider(client, cfg.base_url)
            else:
                provider = EtherscanProvider(client, cfg.base_url)
            provider.name = name
            providers[name] = provider
            pools[name] = KeyPool(name, cfg.keys, clock, store, cfg.cooldown_s)
        return cls(
            providers,
            pools,
            {name: cfg.priority for name, cfg in settings.providers.items()},
            max_retries={name: cfg.max_retries for name, cfg in settings.providers.items()},
            clock=clock,
            store=store,
        )

    def _candidates(self, chain: Chain, exclude: set[str]) -> list[str]:
        allowed = chain.config.providers or list(self.providers)
        names = [
            n
            for n in allowed
            if n in self.providers
            and n not in exclude
            and self.pools[n].keys
            and self.providers[n].supports(chain)
        ]
        return sorted(names, key=lambda n: self.priorities.get(n, 100))

    def call(
        self,
        chain: Chain,
        operation: Callable[[TransferProvider, str], T],
        *,
        prefer: str | None = None,
    ) -> tuple[str, T]:
        """Run ``operation(provider, key)`` on the best available key.

        Rate-limited keys are benched and the next key or provider is tried;
        transient errors are retried with backoff on the same key first.
        Returns the provider name that served the call and its result.
        """
        unsupported: set[str] = set()
        attempts: dict[tuple[str, str], int] = {}
        while True:
            names = self._candidates(chain, unsupported)
            if prefer in names:
                names.remove(prefer)
                names.insert(0, prefer)
            if not names:
                raise AllProvidersExhaustedError(f"no provider can serve chain {chain.name}")

            chosen = None
            for name in names:
                key = self.pools[name].acquire()
                if key is not None:
                    chosen = (name, key)
                    break

            if chosen is None:
                waits = [w for n in names if (w := self.pools[n].next_ready_in()) is not None]
                if not waits or min(waits) > MAX_WAIT_S:
                    raise AllProvidersExhaustedError(
                        f"all keys for chain {chain.name} are rate limited or out of quota"
                    )
                self.clock.sleep(min(waits))
                continue

            name, key = chosen
            pool = self.pools[name]
            try:
                result = operation(self.providers[name], key.secret)
            except RateLimitedError as exc:
                log.warning("provider.rate_limited", provider=name, key=key.key_id)
                pool.bench(key, exc.retry_after)
            except QuotaExceededError:
                log.warning("provider.quota_exceeded", provider=name, key=key.key_id)
                pool.bench_until_tomorrow(key)
            except AuthError as exc:
                log.error("provider.auth_failed", provider=name, key=key.key_id, error=str(exc))
                pool.disable(key, str(exc))
            except UnsupportedError:
                unsupported.add(name)
            except TransientProviderError as exc:
                pool.record_error(key)
                tries = attempts.get((name, key.key_id), 0) + 1
                attempts[(name, key.key_id)] = tries
                log.warning(
                    "provider.transient_error",
                    provider=name,
                    key=key.key_id,
                    attempt=tries,
                    error=str(exc),
                )
                if tries > self.max_retries.get(name, 3):
                    pool.bench(key)
                    attempts.pop((name, key.key_id))
                else:
                    self.clock.sleep(min(2.0**tries, MAX_WAIT_S))
            else:
                pool.record_success(key)
                return name, result

    def fetch_transfers(
        self, chain: Chain, address: str, from_block: int, to_block: int
    ) -> list[RawTransfer]:
        """All transfers touching ``address`` in ``[from_block, to_block]``.

        Paging continues on the same provider while it has keys. If a different
        provider takes over mid-way, pages from the previous provider are
        discarded and the range is fetched again, because page cursors and
        result sets are provider specific.
        """
        collected: list[RawTransfer] = []
        current: str | None = None
        cursor: dict[str, Any] | None = None
        while True:
            request = TransferRequest(
                chain=chain,
                address=address,
                from_block=from_block,
                to_block=to_block,
                cursor=cursor,
            )
            served_by, page = self.call(
                chain, partial(_fetch_page, request=request, cursor_owner=current), prefer=current
            )
            if served_by != current:
                if current is not None:
                    log.info("provider.switched", from_provider=current, to_provider=served_by)
                collected = []
                current = served_by
            collected.extend(page.transfers)
            cursor = page.next_cursor
            if cursor is None:
                break
        return assign_uids(collected)

    def latest_block(self, chain: Chain) -> int:
        return self.call(chain, lambda p, k: p.latest_block(k, chain))[1]

    def get_code(self, chain: Chain, address: str) -> str:
        return self.call(chain, lambda p, k: p.get_code(k, chain, address))[1]

    def get_transaction_count(self, chain: Chain, address: str) -> int:
        return self.call(chain, lambda p, k: p.get_transaction_count(k, chain, address))[1]

    def get_logs(
        self, chain: Chain, from_block: int, to_block: int, topics: list[Any]
    ) -> list[dict[str, Any]]:
        return self.call(chain, lambda p, k: p.get_logs(k, chain, from_block, to_block, topics))[1]

    def get_block(self, chain: Chain, number: int) -> dict[str, Any]:
        return self.call(chain, lambda p, k: p.get_block(k, chain, number))[1]

    def eth_call(self, chain: Chain, to: str, data: str) -> str:
        return self.call(chain, lambda p, k: p.eth_call(k, chain, to, data))[1]


def _fetch_page(
    provider: TransferProvider, key: str, *, request: TransferRequest, cursor_owner: str | None
) -> TransferPage:
    # Cursors belong to the provider that issued them.
    if provider.name != cursor_owner:
        request = replace(request, cursor=None)
    return provider.fetch_transfers_page(key, request)
