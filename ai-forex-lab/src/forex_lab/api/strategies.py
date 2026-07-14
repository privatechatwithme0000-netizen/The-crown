"""Strategy endpoints: list, versions, register, retire, graveyard."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from forex_lab.api.deps import db_session
from forex_lab.backtest.persistence import ensure_strategy_version
from forex_lab.baselines import available_baselines
from forex_lab.db import models
from forex_lab.strategies import available_strategies, get_strategy_class

router = APIRouter(prefix="/strategies", tags=["strategies"])


class RegisterVersionRequest(BaseModel):
    strategy_key: str
    parameters: dict[str, Any] = {}


@router.get("")
async def list_strategies() -> dict[str, Any]:
    return {
        "strategies": available_strategies(),
        "baselines": available_baselines(),
    }


@router.get("/{strategy_key}/parameters")
async def show_parameters(strategy_key: str) -> dict[str, Any]:
    try:
        cls = get_strategy_class(strategy_key)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "strategy_key": strategy_key,
        "semver": cls.semver,
        "default_parameters": cls.default_parameters(),
        "source_hash": cls.source_hash(),
    }


@router.get("/versions")
async def list_versions(session: AsyncSession = Depends(db_session)) -> dict[str, Any]:
    rows = (await session.execute(select(models.StrategyVersion))).scalars().all()
    return {
        "versions": [
            {
                "id": v.id,
                "strategy_key": v.strategy_key,
                "semver": v.semver,
                "source_hash": v.source_hash,
                "is_retired": v.is_retired,
                "parameters": v.parameters,
            }
            for v in rows
        ]
    }


@router.post("/versions")
async def register_version(
    req: RegisterVersionRequest, session: AsyncSession = Depends(db_session)
) -> dict[str, Any]:
    try:
        cls = get_strategy_class(req.strategy_key)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    strategy = cls(**req.parameters)
    version = await ensure_strategy_version(session, strategy)
    return {"id": version.id, "strategy_key": version.strategy_key, "semver": version.semver}


@router.post("/versions/{version_id}/retire")
async def retire_version(
    version_id: int, session: AsyncSession = Depends(db_session)
) -> dict[str, Any]:
    version = await session.get(models.StrategyVersion, version_id)
    if version is None:
        raise HTTPException(status_code=404, detail="version not found")
    version.is_retired = True
    return {"id": version.id, "is_retired": True}


@router.get("/graveyard")
async def view_graveyard(session: AsyncSession = Depends(db_session)) -> dict[str, Any]:
    rows = (
        await session.execute(
            select(models.StrategyGraveyard).order_by(models.StrategyGraveyard.retired_at.desc())
        )
    ).scalars().all()
    return {
        "graveyard": [
            {
                "strategy_key": g.strategy_key,
                "semver": g.semver,
                "failure_reason": g.failure_reason,
                "eligibility_failures": g.eligibility_failures,
                "max_drawdown": None if g.max_drawdown is None else str(g.max_drawdown),
                "max_consecutive_losses": g.max_consecutive_losses,
                "retired_at": g.retired_at.isoformat(),
            }
            for g in rows
        ]
    }


class GraveyardRequest(BaseModel):
    strategy_key: str
    semver: str
    parameters: dict[str, Any] = {}
    source_hash: str = ""
    metrics: dict[str, Any] = {}
    failure_reason: str
    eligibility_failures: list[str] = []
    notes: str = ""


@router.post("/graveyard")
async def add_to_graveyard(
    req: GraveyardRequest, session: AsyncSession = Depends(db_session)
) -> dict[str, Any]:
    entry = models.StrategyGraveyard(
        strategy_key=req.strategy_key,
        semver=req.semver,
        parameters=req.parameters,
        source_hash=req.source_hash,
        metrics=req.metrics,
        max_drawdown=None,
        max_consecutive_losses=req.metrics.get("max_consecutive_losses"),
        failure_reason=req.failure_reason,
        eligibility_failures=req.eligibility_failures,
        notes=req.notes,
        retired_at=datetime.now(tz=timezone.utc),
    )
    session.add(entry)
    await session.flush()
    return {"id": entry.id}
