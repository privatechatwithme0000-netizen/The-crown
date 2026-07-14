"""Paper-trading endpoints.

Phase 1 supports internal paper sessions and *practice* OANDA sessions only.
Real-money execution is hard-blocked: starting any OANDA-practice session
asserts ``LIVE_EXECUTION_ENABLED=false`` and there is no live order path.

Session bookkeeping status lives in Redis; trading records live in PostgreSQL.
Every record is labeled with its execution mode (INTERNAL_PAPER / OANDA_PRACTICE)
so modes are never mixed unlabeled.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from forex_lab.cache.redis_client import get_json, paper_session_key, set_json
from forex_lab.config import get_settings
from forex_lab.domain.enums import ExecutionMode

router = APIRouter(prefix="/paper", tags=["paper"])


class StartSessionRequest(BaseModel):
    instrument: str = "AUD_CAD"
    timeframe: str = "M15"
    strategy_key: str = "trend_following"


async def _start(mode: ExecutionMode, req: StartSessionRequest) -> dict[str, Any]:
    settings = get_settings()
    if mode is ExecutionMode.OANDA_PRACTICE:
        # Enforce the practice-only guarantee before opening any broker session.
        settings.assert_live_execution_blocked()
        if settings.oanda_env != "practice":
            raise HTTPException(status_code=400, detail="OANDA_ENV must be 'practice'")
    session_id = str(uuid.uuid4())
    state = {
        "session_id": session_id,
        "mode": mode.value,
        "instrument": req.instrument,
        "timeframe": req.timeframe,
        "strategy_key": req.strategy_key,
        "status": "RUNNING",
    }
    await set_json(paper_session_key(session_id), state)
    return state


@router.post("/internal/start")
async def start_internal(req: StartSessionRequest) -> dict[str, Any]:
    return await _start(ExecutionMode.INTERNAL_PAPER, req)


@router.post("/oanda-practice/start")
async def start_oanda_practice(req: StartSessionRequest) -> dict[str, Any]:
    return await _start(ExecutionMode.OANDA_PRACTICE, req)


@router.post("/{session_id}/stop")
async def stop_session(session_id: str) -> dict[str, Any]:
    state = await get_json(paper_session_key(session_id))
    if not isinstance(state, dict):
        raise HTTPException(status_code=404, detail="session not found")
    state["status"] = "STOPPED"
    await set_json(paper_session_key(session_id), state)
    return state


@router.get("/{session_id}")
async def session_status(session_id: str) -> dict[str, Any]:
    state = await get_json(paper_session_key(session_id))
    if not isinstance(state, dict):
        raise HTTPException(status_code=404, detail="session not found")
    return state
