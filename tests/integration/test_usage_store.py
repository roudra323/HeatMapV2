from datetime import date

from sqlalchemy import Engine

from heatmap_core.providers.usage_store import SqlUsageStore


def test_counters_accumulate_across_flushes_and_instances(engine: Engine) -> None:
    day = date(2026, 1, 1)
    store = SqlUsageStore(engine, flush_every=2)
    store.record("alchemy", "k1", day, requests=1)
    store.record("alchemy", "k1", day, requests=1)  # triggers flush
    store.record("alchemy", "k1", day, requests=1)  # pending
    assert store.requests_today("alchemy", "k1", day) == 3
    store.flush()

    restarted = SqlUsageStore(engine)
    assert restarted.requests_today("alchemy", "k1", day) == 3
    assert restarted.requests_today("alchemy", "k2", day) == 0
