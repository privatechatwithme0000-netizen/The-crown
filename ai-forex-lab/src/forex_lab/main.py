"""FastAPI application factory.

On startup the app asserts the Phase 1 safety guarantee
(``LIVE_EXECUTION_ENABLED=false``) so no real-money execution service can be
started. It wires the DB engine and Redis client and mounts the REST routers
with OpenAPI docs at ``/docs``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from forex_lab.api import backtests, health, marketdata, paper, strategies
from forex_lab.cache.redis_client import close_redis
from forex_lab.config import get_settings
from forex_lab.db.session import dispose_engine, init_engine
from forex_lab.logging_setup import configure_logging


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    # Phase 1 hard block: refuse to start if live execution is enabled.
    settings.assert_live_execution_blocked()
    init_engine(settings)
    try:
        yield
    finally:
        await dispose_engine()
        await close_redis()


def create_app() -> FastAPI:
    app = FastAPI(
        title="AI Forex Lab",
        version="0.1.0",
        description=(
            "Deterministic forex strategy research and paper-trading platform "
            "(Phase 1). No real-money execution; no profitability claims."
        ),
        lifespan=lifespan,
    )
    app.include_router(health.router)
    app.include_router(marketdata.router)
    app.include_router(strategies.router)
    app.include_router(backtests.router)
    app.include_router(paper.router)

    @app.get("/", tags=["root"])
    async def root() -> dict[str, str]:
        return {
            "name": "AI Forex Lab",
            "phase": "1",
            "docs": "/docs",
            "live_execution": "disabled",
        }

    return app


app = create_app()
