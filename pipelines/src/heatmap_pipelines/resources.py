"""Dagster resource that hands stages their settings, database and providers."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import cached_property

import dagster as dg
from sqlalchemy import Engine

from heatmap_core.config import Chain, ChainRegistry, Settings, get_settings
from heatmap_core.db.session import get_engine
from heatmap_core.normalize.pricing import CoinGeckoPrices, PriceSource
from heatmap_core.providers.router import ProviderRouter
from heatmap_core.providers.usage_store import SqlUsageStore


class HeatmapResource(dg.ConfigurableResource):  # type: ignore[type-arg]
    """Settings come from ``config/*.yaml`` and ``HEATMAP_*`` env vars, not Dagster config."""

    @cached_property
    def settings(self) -> Settings:
        return get_settings()

    @cached_property
    def engine(self) -> Engine:
        return get_engine()

    def chain(self, name: str) -> Chain:
        return ChainRegistry(self.settings).get(name)

    @contextmanager
    def router(self) -> Iterator[ProviderRouter]:
        store = SqlUsageStore(self.engine)
        try:
            yield ProviderRouter.from_settings(self.settings, store=store)
        finally:
            store.flush()

    def prices(self) -> PriceSource | None:
        if not self.settings.pricing.enabled:
            return None
        return CoinGeckoPrices(self.settings.pricing)
