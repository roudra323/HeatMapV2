"""Daily USD prices with a database cache."""

from __future__ import annotations

import os
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Protocol

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from heatmap_core.config.settings import PricingConfig
from heatmap_core.db.models import TokenPrice
from heatmap_core.logging import get_logger
from heatmap_core.providers._http import send_json
from heatmap_core.providers.errors import ProviderError

log = get_logger(__name__)


class PriceSource(Protocol):
    name: str

    def daily_prices(self, price_id: str, start: date, end: date) -> dict[date, Decimal]: ...


class CoinGeckoPrices:
    name = "coingecko"

    def __init__(self, config: PricingConfig, client: httpx.Client | None = None) -> None:
        self._config = config
        self._client = client or httpx.Client(timeout=30)

    def daily_prices(self, price_id: str, start: date, end: date) -> dict[date, Decimal]:
        headers = {}
        if self._config.api_key_env and (key := os.environ.get(self._config.api_key_env)):
            headers["x-cg-demo-api-key"] = key
        params = {
            "vs_currency": "usd",
            "from": int(datetime.combine(start, time.min, UTC).timestamp()),
            "to": int(datetime.combine(end + timedelta(days=1), time.min, UTC).timestamp()),
        }
        body = send_json(
            self._client,
            "GET",
            f"{self._config.base_url}/coins/{price_id}/market_chart/range",
            params=params,
            headers=headers,
        )
        prices: dict[date, Decimal] = {}
        for ts_ms, price in body.get("prices", []):
            day = datetime.fromtimestamp(ts_ms / 1000, tz=UTC).date()
            prices.setdefault(day, Decimal(str(price)))
        return prices


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

    def prime(self, token_address: str, price_id: str | None, days: set[date]) -> None:
        if not days:
            return
        if token_address in self._stable:  # verified stablecoins are pegged at $1
            for day in days:
                self._cache[(token_address, day)] = Decimal(1)
            return
        stored = {
            row.day: row.price_usd
            for row in self._session.scalars(
                select(TokenPrice).where(
                    TokenPrice.chain_id == self._chain_id,
                    TokenPrice.token_address == token_address,
                    TokenPrice.day.in_(days),
                )
            )
        }
        missing = days - stored.keys()
        if missing and price_id and self._source is not None:
            try:
                fetched = self._source.daily_prices(price_id, min(missing), max(missing))
            except ProviderError as exc:
                log.warning("pricing.fetch_failed", price_id=price_id, error=str(exc))
                fetched = {}
            rows = [
                {
                    "chain_id": self._chain_id,
                    "token_address": token_address,
                    "day": day,
                    "price_usd": price,
                    "source": self._source.name,
                }
                for day, price in fetched.items()
            ]
            if rows:
                self._session.execute(insert(TokenPrice).values(rows).on_conflict_do_nothing())
            stored.update(fetched)
        for day in days:
            self._cache[(token_address, day)] = stored.get(day)

    def price(self, token_address: str, day: date) -> Decimal | None:
        return self._cache.get((token_address, day))
