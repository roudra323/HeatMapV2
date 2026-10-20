from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import text

from heatmap_api.deps import SessionDep, get_settings
from heatmap_api.schemas import ChainOut
from heatmap_core.config import ChainRegistry, Settings

router = APIRouter()


@router.get("/health", tags=["meta"])
def health(session: SessionDep) -> dict[str, str]:
    session.execute(text("SELECT 1"))
    return {"status": "ok", "database": "ok"}


@router.get("/v1/chains", response_model=list[ChainOut], tags=["meta"])
def chains(settings: Annotated[Settings, Depends(get_settings)]) -> list[ChainOut]:
    return [
        ChainOut(
            name=c.name,
            chain_id=c.chain_id,
            native_symbol=c.config.native_symbol,
            explorer_url=c.config.explorer_url,
        )
        for c in ChainRegistry(settings).all()
    ]
