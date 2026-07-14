"""Redis client wrapper.

Redis is a cache and coordination layer only — never the source of truth. It
holds provider-health snapshots, rate-limit state, backtest task status,
paper-session status, and short-lived locks. All permanent trading records live
in PostgreSQL.
"""

from __future__ import annotations

import json
from typing import Any

import redis.asyncio as aioredis

from forex_lab.config import Settings, get_settings

_client: aioredis.Redis | None = None


def get_redis(settings: Settings | None = None) -> aioredis.Redis:
    """Return a shared async Redis client."""
    global _client
    if _client is None:
        settings = settings or get_settings()
        _client = aioredis.from_url(
            settings.redis_dsn, encoding="utf-8", decode_responses=True
        )
    return _client


async def close_redis() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


async def ping() -> bool:
    try:
        return bool(await get_redis().ping())
    except Exception:  # noqa: BLE001 - readiness probe must not raise
        return False


async def set_json(key: str, value: Any, ttl_seconds: int | None = None) -> None:
    await get_redis().set(key, json.dumps(value, default=str), ex=ttl_seconds)


async def get_json(key: str) -> Any | None:
    raw = await get_redis().get(key)
    return json.loads(raw) if raw else None


# Namespaced key helpers -----------------------------------------------------
def provider_health_key(name: str) -> str:
    return f"provider:health:{name}"


def rate_limit_key(name: str) -> str:
    return f"provider:ratelimit:{name}"


def backtest_status_key(run_id: int) -> str:
    return f"backtest:status:{run_id}"


def paper_session_key(session_id: str) -> str:
    return f"paper:session:{session_id}"
