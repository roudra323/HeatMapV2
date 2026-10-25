"""Engine and session helpers."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from functools import lru_cache
from typing import Any

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from heatmap_core.config import get_settings


def make_engine(url: str, *, echo: bool = False) -> Engine:
    return create_engine(url, echo=echo, pool_pre_ping=True, future=True)


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    return make_engine(get_settings().database_url)


# PostgreSQL accepts at most this many bind parameters in one statement.
MAX_BIND_PARAMS = 65_535


def insert_batches(rows: Sequence[dict[str, Any]]) -> Iterator[Sequence[dict[str, Any]]]:
    """Split multi-row INSERT values so no statement exceeds the bind-parameter limit."""
    if not rows:
        return
    per_batch = max(1, MAX_BIND_PARAMS // len(rows[0]))
    for start in range(0, len(rows), per_batch):
        yield rows[start : start + per_batch]


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


@contextmanager
def session_scope(engine: Engine | None = None) -> Iterator[Session]:
    """Transactional scope: commits on success, rolls back on error."""
    factory = make_session_factory(engine or get_engine())
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
