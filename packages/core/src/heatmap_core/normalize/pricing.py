"""Daily USD prices with a database cache.

``token_prices`` also records misses: a row with a NULL price means the source
answered but had no price for that token and day (or cannot price the token at
all), so it is not asked again. Fetch errors record nothing and are retried.
"""

from __future__ import annotations

import os
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any, Protocol

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from heatmap_core.config import Chain
from heatmap_core.config.settings import PricingConfig
from heatmap_core.db.models import Token, TokenPrice
from heatmap_core.logging import get_logger
from heatmap_core.primitives import NATIVE_TOKEN
from heatmap_core.providers._http import send_json
from heatmap_core.providers.errors import ProviderError

log = get_logger(__name__)

# Missing days further apart than this are fetched as separate ranges.
MAX_GAP_DAYS = 30


class PriceSource(Protocol):
    name: str

    def price_key(self, chain: Chain, token: Token) -> str | None:
        """The id this source prices ``token`` under, or None if it cannot price it."""
        ...

    def daily_prices(self, key: str, start: date, end: date) -> dict[date, Decimal]: ...


def _midnight(day: date) -> int:
    return int(datetime.combine(day, time.min, UTC).timestamp())


class CoinGeckoPrices:
    """CoinGecko market charts; only tokens with a ``price_id`` can be priced."""

    name = "coingecko"

    def __init__(self, config: PricingConfig, client: httpx.Client | None = None) -> None:
        self._config = config
        self._client = client or httpx.Client(timeout=30)

    def price_key(self, chain: Chain, token: Token) -> str | None:
        return token.price_id

    def daily_prices(self, key: str, start: date, end: date) -> dict[date, Decimal]:
        headers = {}
        key_env = self._config.coingecko_api_key_env
        if key_env and (api_key := os.environ.get(key_env)):
            headers["x-cg-demo-api-key"] = api_key
        params = {"vs_currency": "usd", "from": _midnight(start), "to": _midnight(end) + 86_400}
        body = send_json(
            self._client,
            "GET",
            f"{self._config.coingecko_url}/coins/{key}/market_chart/range",
            params=params,
            headers=headers,
        )
        prices: dict[date, Decimal] = {}
        for ts_ms, price in body.get("prices", []):
            day = datetime.fromtimestamp(ts_ms / 1000, tz=UTC).date()
            prices.setdefault(day, Decimal(str(price)))
        return prices


class DefiLlamaPrices:
    """DefiLlama coins API: free, keyless, prices tokens by contract address."""

    name = "defillama"
    # The API rejects requests for more than 500 points (coins x days).
    MAX_POINTS = 500

    def __init__(self, config: PricingConfig, client: httpx.Client | None = None) -> None:
        self._config = config
        self._client = client or httpx.Client(timeout=30)

    def price_key(self, chain: Chain, token: Token) -> str | None:
        if token.address == NATIVE_TOKEN:
            # The native asset has no contract; DefiLlama also accepts CoinGecko ids.
            return f"coingecko:{token.price_id}" if token.price_id else None
        if token.standard != "erc20":
            return None
        return f"{chain.config.defillama_chain or chain.name}:{token.address}"

    def daily_prices(self, key: str, start: date, end: date) -> dict[date, Decimal]:
        prices: dict[date, Decimal] = {}
        day = start
        while day <= end:
            span = min((end - day).days + 1, self.MAX_POINTS)
            body = send_json(
                self._client,
                "GET",
                f"{self._config.defillama_url}/chart/{key}",
                params={"start": _midnight(day), "span": span, "period": "1d"},
            )
            coins: dict[str, Any] = (body.get("coins") if isinstance(body, dict) else None) or {}
            for point in (coins.get(key) or {}).get("prices", []):
                # Points land a few seconds either side of midnight: round to the nearest day.
                when = datetime.fromtimestamp(point["timestamp"], tz=UTC) + timedelta(hours=12)
                prices.setdefault(when.date(), Decimal(str(point["price"])))
            day += timedelta(days=span)
        return {d: p for d, p in prices.items() if start <= d <= end}


def make_price_source(config: PricingConfig) -> PriceSource | None:
    if not config.enabled:
        return None
    if config.source == "coingecko":
        return CoinGeckoPrices(config)
    return DefiLlamaPrices(config)


def day_ranges(days: set[date], max_gap: int = MAX_GAP_DAYS) -> list[tuple[date, date]]:
    """Group days into ``(start, end)`` ranges, splitting where the gap exceeds ``max_gap``."""
    ranges: list[tuple[date, date]] = []
    for day in sorted(days):
        if ranges and (day - ranges[-1][1]).days <= max_gap:
            ranges[-1] = (ranges[-1][0], day)
        else:
            ranges.append((day, day))
    return ranges


class PriceBook:
    """Resolves (token, day) to a USD price, fetching and caching missing days.

    Verified stablecoins are valued at $1 without a lookup.
    """

    def __init__(
        self,
        session: Session,
        chain_id: int,
        source: PriceSource | None,
        stable_tokens: set[str],
    ) -> None:
        self._session = session
        self._chain_id = chain_id
        self._source = source
        self._stable = stable_tokens
        self._cache: dict[tuple[str, date], Decimal | None] = {}

    def prime(self, token_address: str, key: str | None, days: set[date]) -> None:
        if not days:
            return
        if token_address in self._stable:  # verified stablecoins are pegged at $1
            for day in days:
                self._cache[(token_address, day)] = Decimal(1)
            return
        source = self._source
        stored: dict[date, Decimal | None] = {}
        for row in self._session.scalars(
            select(TokenPrice).where(
                TokenPrice.chain_id == self._chain_id,
                TokenPrice.token_address == token_address,
                TokenPrice.day.in_(days),
            )
        ):
            # A miss recorded by another source says nothing about this one.
            if row.price_usd is not None or (source is not None and row.source == source.name):
                stored[row.day] = row.price_usd

        missing = days - stored.keys()
        if missing and source is not None:
            fetched = self._fetch(source, token_address, key, missing)
            stored.update(fetched)
            self._store(source, token_address, fetched)
        for day in days:
            self._cache[(token_address, day)] = stored.get(day)

    def _fetch(
        self, source: PriceSource, token_address: str, key: str | None, missing: set[date]
    ) -> dict[date, Decimal | None]:
        if key is None:
            return dict.fromkeys(missing)  # this source cannot price the token at all
        today = datetime.now(UTC).date()
        result: dict[date, Decimal | None] = {}
        for start, end in day_ranges(missing):
            try:
                prices = source.daily_prices(key, start, end)
            except ProviderError as exc:
                log.warning("pricing.fetch_failed", key=key, error=str(exc))
                continue
            for day in missing:
                if start <= day <= end and (day in prices or day < today):
                    # Today's price may not be published yet, so it is not recorded as a miss.
                    result[day] = prices.get(day)
        return result

    def _store(
        self, source: PriceSource, token_address: str, prices: dict[date, Decimal | None]
    ) -> None:
        if not prices:
            return
        stmt = insert(TokenPrice).values(
            [
                {
                    "chain_id": self._chain_id,
                    "token_address": token_address,
                    "day": day,
                    "price_usd": price,
                    "source": source.name,
                }
                for day, price in prices.items()
            ]
        )
        self._session.execute(
            stmt.on_conflict_do_update(
                index_elements=["chain_id", "token_address", "day"],
                set_={"price_usd": stmt.excluded.price_usd, "source": stmt.excluded.source},
                # Never replace a known price, only a recorded miss.
                where=TokenPrice.price_usd.is_(None),
            )
        )

    def price(self, token_address: str, day: date) -> Decimal | None:
        return self._cache.get((token_address, day))
