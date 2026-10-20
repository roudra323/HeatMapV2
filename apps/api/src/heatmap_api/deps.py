"""Request-scoped dependencies."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, HTTPException, Path, Query, Request
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from heatmap_core.config import Chain, ChainRegistry, Settings, UnknownChainError
from heatmap_core.primitives import InvalidAddressError, normalize_address


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_engine(request: Request) -> Engine:
    engine: Engine = request.app.state.engine
    return engine


def get_session(engine: Annotated[Engine, Depends(get_engine)]) -> Iterator[Session]:
    with Session(engine, expire_on_commit=False) as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise


def get_chain(
    settings: Annotated[Settings, Depends(get_settings)],
    chain: Annotated[str, Query(description="Configured chain name")] = "ethereum",
) -> Chain:
    try:
        return ChainRegistry(settings).get(chain)
    except UnknownChainError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def address_param(
    address: Annotated[str, Path(description="EVM address (any case)")],
) -> str:
    try:
        return normalize_address(address)
    except InvalidAddressError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def page_size(
    settings: Annotated[Settings, Depends(get_settings)],
    limit: Annotated[int | None, Query(ge=1)] = None,
) -> int:
    if limit is None:
        return settings.api.default_page_size
    return min(limit, settings.api.max_page_size)


SessionDep = Annotated[Session, Depends(get_session)]
ChainDep = Annotated[Chain, Depends(get_chain)]
AddressDep = Annotated[str, Depends(address_param)]
LimitDep = Annotated[int, Depends(page_size)]
OffsetDep = Annotated[int, Query(ge=0)]
