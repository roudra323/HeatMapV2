from __future__ import annotations

from datetime import UTC, date, datetime, time
from decimal import Decimal

import httpx
import pytest
import respx

from heatmap_core.config.settings import PricingConfig
from heatmap_core.db.models import Token
from heatmap_core.normalize.pricing import (
    CoinGeckoPrices,
    DefiLlamaPrices,
    day_ranges,
    make_price_source,
)
from heatmap_core.primitives import NATIVE_TOKEN
from heatmap_core.providers import TransientProviderError
from tests.support import addr, ethereum

CHART = "https://coins.llama.fi/chart/"
PEPE = addr(0x9E9E)
KEY = f"ethereum:{PEPE}"


def ts(day: date, seconds: int = 0) -> int:
    return int(datetime.combine(day, time.min, UTC).timestamp()) + seconds


def chart(key: str, points: list[tuple[int, float]]) -> httpx.Response:
    prices = [{"timestamp": t, "price": p} for t, p in points]
    return httpx.Response(200, json={"coins": {key: {"symbol": "X", "prices": prices}}})


def token(address: str, standard: str = "erc20", price_id: str | None = None) -> Token:
    return Token(chain_id=1, address=address, standard=standard, price_id=price_id)


def test_defillama_price_keys() -> None:
    source = DefiLlamaPrices(PricingConfig())
    chain = ethereum()
    assert source.price_key(chain, token(PEPE)) == KEY
    assert source.price_key(chain, token(NATIVE_TOKEN, "native", "ethereum")) == (
        "coingecko:ethereum"
    )
    assert source.price_key(chain, token(NATIVE_TOKEN, "native")) is None
    assert source.price_key(chain, token(addr(7), "erc721")) is None
    assert source.price_key(ethereum(defillama_chain="eth"), token(PEPE)) == f"eth:{PEPE}"


@respx.mock
def test_defillama_rounds_points_to_the_nearest_day() -> None:
    route = respx.get(CHART + KEY).mock(
        return_value=chart(
            KEY,
            [
                (ts(date(2025, 1, 1), 1), 1.0),
                (ts(date(2025, 1, 2), 3), 2.0),
                (ts(date(2025, 1, 3), -1), 3.0),  # 23:59:59 on Jan 2 is Jan 3's point
            ],
        )
    )
    prices = DefiLlamaPrices(PricingConfig()).daily_prices(KEY, date(2025, 1, 1), date(2025, 1, 3))
    assert prices == {
        date(2025, 1, 1): Decimal("1.0"),
        date(2025, 1, 2): Decimal("2.0"),
        date(2025, 1, 3): Decimal("3.0"),
    }
    params = route.calls[0].request.url.params
    assert params["start"] == str(ts(date(2025, 1, 1))) and params["span"] == "3"


@respx.mock
def test_defillama_splits_long_ranges_and_handles_unknown_coins() -> None:
    route = respx.get(CHART + KEY).mock(return_value=httpx.Response(200, json={"coins": {}}))
    prices = DefiLlamaPrices(PricingConfig()).daily_prices(KEY, date(2023, 1, 1), date(2025, 1, 1))
    assert prices == {}
    spans = [int(c.request.url.params["span"]) for c in route.calls]
    assert spans == [500, 232]  # 732 days, at most 500 points per request


@respx.mock
def test_defillama_errors_are_provider_errors() -> None:
    respx.get(CHART + KEY).mock(return_value=httpx.Response(400, json={"message": "too many"}))
    with pytest.raises(TransientProviderError):
        DefiLlamaPrices(PricingConfig()).daily_prices(KEY, date(2025, 1, 1), date(2025, 1, 2))


def test_day_ranges_split_on_gaps() -> None:
    days = {date(2025, 1, 1), date(2025, 1, 5), date(2025, 6, 1), date(2025, 6, 2)}
    assert day_ranges(days, max_gap=30) == [
        (date(2025, 1, 1), date(2025, 1, 5)),
        (date(2025, 6, 1), date(2025, 6, 2)),
    ]
    assert day_ranges(set()) == []


def test_make_price_source() -> None:
    assert isinstance(make_price_source(PricingConfig()), DefiLlamaPrices)
    assert isinstance(make_price_source(PricingConfig(source="coingecko")), CoinGeckoPrices)
    assert make_price_source(PricingConfig(enabled=False)) is None
