"""PostgreSQL-backed usage counters for provider keys."""

from __future__ import annotations

from collections import defaultdict
from datetime import date

from sqlalchemy import Engine, select
from sqlalchemy.dialects.postgresql import insert

from heatmap_core.db.models import ProviderKeyUsage
from heatmap_core.db.session import session_scope


class SqlUsageStore:
    """Buffers counters in memory and upserts them every ``flush_every`` records."""

    def __init__(self, engine: Engine, flush_every: int = 50) -> None:
        self._engine = engine
        self._flush_every = flush_every
        self._pending: dict[tuple[str, str, date], list[int]] = defaultdict(lambda: [0, 0, 0])
        self._since_flush = 0

    def requests_today(self, provider: str, key_id: str, day: date) -> int:
        with session_scope(self._engine) as session:
            stored = session.scalar(
                select(ProviderKeyUsage.request_count).where(
                    ProviderKeyUsage.provider == provider,
                    ProviderKeyUsage.key_id == key_id,
                    ProviderKeyUsage.day == day,
                )
            )
        pending = self._pending.get((provider, key_id, day), [0, 0, 0])[0]
        return (stored or 0) + pending

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
        row = self._pending[(provider, key_id, day)]
        row[0] += requests
        row[1] += rate_limited
        row[2] += errors
        self._since_flush += 1
        if self._since_flush >= self._flush_every:
            self.flush()

    def flush(self) -> None:
        if not self._pending:
            return
        rows = [
            {
                "provider": provider,
                "key_id": key_id,
                "day": day,
                "request_count": counts[0],
                "rate_limited_count": counts[1],
                "error_count": counts[2],
            }
            for (provider, key_id, day), counts in self._pending.items()
        ]
        stmt = insert(ProviderKeyUsage).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["provider", "key_id", "day"],
            set_={
                "request_count": ProviderKeyUsage.request_count + stmt.excluded.request_count,
                "rate_limited_count": ProviderKeyUsage.rate_limited_count
                + stmt.excluded.rate_limited_count,
                "error_count": ProviderKeyUsage.error_count + stmt.excluded.error_count,
            },
        )
        with session_scope(self._engine) as session:
            session.execute(stmt)
        self._pending.clear()
        self._since_flush = 0
