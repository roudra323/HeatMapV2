from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response, status

from heatmap_api.deps import AddressDep, ChainDep, LimitDep, OffsetDep, SessionDep
from heatmap_api.schemas import Page, WatchlistCreate, WatchlistEntryOut
from heatmap_core.exports.read_models import WatchStatus, watch_statuses
from heatmap_core.ingestion.watchlist import add_seed, deactivate
from heatmap_core.primitives import InvalidAddressError, WatchOrigin, normalize_address

router = APIRouter(prefix="/v1/watchlist", tags=["watchlist"])


def to_out(status_: WatchStatus) -> WatchlistEntryOut:
    out = WatchlistEntryOut.model_validate(status_.entry)
    out.last_block = status_.last_block
    out.last_synced_at = status_.last_synced_at
    out.last_error = status_.last_error
    return out


@router.get("", response_model=Page[WatchlistEntryOut])
def list_watchlist(
    session: SessionDep,
    chain: ChainDep,
    limit: LimitDep,
    offset: OffsetDep = 0,
    origin: Annotated[WatchOrigin | None, Query()] = None,
    active: bool | None = None,
) -> Page[WatchlistEntryOut]:
    total, rows = watch_statuses(
        session,
        chain.chain_id,
        origin=origin.value if origin else None,
        active=active,
        limit=limit,
        offset=offset,
    )
    return Page(total=total, limit=limit, offset=offset, items=[to_out(r) for r in rows])


@router.post("", response_model=WatchlistEntryOut, status_code=status.HTTP_201_CREATED)
def add_to_watchlist(
    body: WatchlistCreate, session: SessionDep, chain: ChainDep
) -> WatchlistEntryOut:
    try:
        address = normalize_address(body.address)
    except InvalidAddressError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    entry = add_seed(session, chain.chain_id, address, priority=body.priority, note=body.note)
    session.flush()
    return to_out(WatchStatus(entry, None, None, None))


@router.delete("/{address}", status_code=status.HTTP_204_NO_CONTENT)
def remove_from_watchlist(address: AddressDep, session: SessionDep, chain: ChainDep) -> Response:
    if not deactivate(session, chain.chain_id, address):
        raise HTTPException(status_code=404, detail="address is not on the watchlist")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
