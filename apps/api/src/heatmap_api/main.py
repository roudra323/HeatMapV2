"""FastAPI application factory."""

from __future__ import annotations

import os

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import Engine

from heatmap_api.routers import analytics, meta, traders, wallets, watchlist
from heatmap_core import __version__
from heatmap_core.config import Settings, get_settings
from heatmap_core.db.session import make_engine
from heatmap_core.logging import configure_logging


def create_app(settings: Settings | None = None, engine: Engine | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.log_json)
    app = FastAPI(
        title="HeatMap API",
        version=__version__,
        description="Wallet tracking, behaviour and neighbourhood analytics.",
    )
    app.state.settings = settings
    app.state.engine = engine or make_engine(settings.database_url)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.api.cors_origins,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["*"],
    )
    for module in (meta, watchlist, wallets, traders, analytics):
        app.include_router(module.router)
    return app


app = create_app()


def run() -> None:
    uvicorn.run(
        "heatmap_api.main:app",
        host=os.environ.get("API_HOST", "0.0.0.0"),
        port=int(os.environ.get("API_PORT", "8000")),
    )
