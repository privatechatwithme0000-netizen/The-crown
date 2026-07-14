"""Ranking endpoints: leaderboard of eligible strategy versions."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from forex_lab.api.deps import db_session
from forex_lab.db import models

router = APIRouter(prefix="/rankings", tags=["rankings"])


@router.get("/leaderboard")
async def leaderboard(
    limit: int = Query(20, le=100),
    include_ineligible: bool = False,
    session: AsyncSession = Depends(db_session),
) -> dict[str, Any]:
    """Return ranked strategy versions, most-eligible/highest-score first.

    Ineligible entries carry no score (NOT_ELIGIBLE) and are excluded by
    default; win rate is never the sole ranking metric.
    """
    stmt = select(models.StrategyRanking)
    if not include_ineligible:
        stmt = stmt.where(models.StrategyRanking.eligible.is_(True))
    stmt = stmt.order_by(
        models.StrategyRanking.eligible.desc(),
        models.StrategyRanking.score.desc().nullslast(),
    ).limit(limit)
    rows = (await session.execute(stmt)).scalars().all()
    return {
        "leaderboard": [
            {
                "strategy_version_id": r.strategy_version_id,
                "run_id": r.run_id,
                "eligible": r.eligible,
                "score": None if r.score is None else str(r.score),
                "eligibility_failures": r.eligibility_failures,
            }
            for r in rows
        ]
    }
