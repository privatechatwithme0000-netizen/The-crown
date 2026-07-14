"""Health endpoints: liveness, readiness, and dependency status."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from sqlalchemy import text

from forex_lab.cache.redis_client import ping as redis_ping
from forex_lab.config import get_settings
from forex_lab.db.session import session_scope

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


async def _postgres_ok() -> bool:
    try:
        async with session_scope() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception:  # noqa: BLE001 - readiness probe must not raise
        return False


@router.get("/ready")
async def readiness() -> dict[str, Any]:
    settings = get_settings()
    pg = await _postgres_ok()
    rd = await redis_ping()
    ready = pg and rd
    return {
        "ready": ready,
        "postgres": pg,
        "redis": rd,
        "live_execution_enabled": settings.live_execution_enabled,
    }


@router.get("/providers")
async def provider_status() -> dict[str, Any]:
    """Report configured providers and their health (OANDA practice, etc.)."""
    from forex_lab.api.deps import build_registry

    registry = build_registry()
    return {"providers": registry.health(), "chain": registry.names()}
