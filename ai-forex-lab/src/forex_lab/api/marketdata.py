"""Market-data endpoints: providers, instruments, candles, datasets, gaps."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from forex_lab.api.deps import build_registry, db_session
from forex_lab.db import models
from forex_lab.domain.enums import PriceComponent, Timeframe
from forex_lab.domain.instruments import all_instruments
from forex_lab.marketdata.ingest import ingest_candles

router = APIRouter(prefix="/marketdata", tags=["marketdata"])


class IngestRequest(BaseModel):
    instrument: str = "AUD_CAD"
    timeframe: Timeframe = Timeframe.M15
    start: datetime
    end: datetime
    price_component: PriceComponent = PriceComponent.BID_ASK


@router.get("/providers")
async def list_providers() -> dict[str, Any]:
    registry = build_registry()
    return {"providers": registry.names(), "health": registry.health()}


@router.get("/instruments")
async def list_instruments() -> dict[str, Any]:
    return {
        "instruments": [
            {
                "name": i.name,
                "base_currency": i.base_currency,
                "quote_currency": i.quote_currency,
                "pip_size": str(i.pip_size),
                "pipette_size": str(i.pipette_size),
                "quantity_step": str(i.quantity_step),
            }
            for i in all_instruments()
        ]
    }


@router.post("/ingest")
async def start_ingestion(
    req: IngestRequest, session: AsyncSession = Depends(db_session)
) -> dict[str, Any]:
    registry = build_registry()
    try:
        report = await ingest_candles(
            session, registry, req.instrument, req.timeframe, req.start, req.end, req.price_component
        )
    except Exception as exc:  # noqa: BLE001 - surface provider errors to client
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {
        "dataset_id": report.dataset_id,
        "provider": report.provider,
        "candle_count": report.candle_count,
        "gap_count": report.gap_count,
        "used_failover": report.used_failover,
        "source_class": report.source_class,
    }


@router.get("/datasets")
async def list_datasets(session: AsyncSession = Depends(db_session)) -> dict[str, Any]:
    rows = (await session.execute(select(models.Dataset).order_by(models.Dataset.id.desc()))).scalars().all()
    return {
        "datasets": [
            {
                "id": d.id,
                "provider": d.provider,
                "broker_environment": d.broker_environment,
                "instrument": d.instrument,
                "timeframe": d.timeframe,
                "price_component": d.price_component,
                "source_class": d.source_class,
                "candle_count": d.candle_count,
                "start_time": d.start_time.isoformat(),
                "end_time": d.end_time.isoformat(),
            }
            for d in rows
        ]
    }


@router.get("/datasets/{dataset_id}/candles")
async def get_candles(
    dataset_id: int,
    limit: int = Query(500, le=5000),
    session: AsyncSession = Depends(db_session),
) -> dict[str, Any]:
    rows = (
        await session.execute(
            select(models.Candle)
            .where(models.Candle.dataset_id == dataset_id)
            .order_by(models.Candle.timestamp)
            .limit(limit)
        )
    ).scalars().all()
    return {
        "dataset_id": dataset_id,
        "candles": [
            {
                "timestamp": c.timestamp.isoformat(),
                "bid": [str(c.bid_open), str(c.bid_high), str(c.bid_low), str(c.bid_close)],
                "ask": [str(c.ask_open), str(c.ask_high), str(c.ask_low), str(c.ask_close)],
                "mid": [str(c.mid_open), str(c.mid_high), str(c.mid_low), str(c.mid_close)],
                "tick_volume": c.tick_volume,
                "spread_open": str(c.spread_open),
                "spread_close": str(c.spread_close),
                "complete": c.complete,
            }
            for c in rows
        ],
    }


@router.get("/datasets/{dataset_id}/gaps")
async def get_gaps(
    dataset_id: int, session: AsyncSession = Depends(db_session)
) -> dict[str, Any]:
    rows = (
        await session.execute(
            select(models.DataGap).where(models.DataGap.dataset_id == dataset_id)
        )
    ).scalars().all()
    return {
        "dataset_id": dataset_id,
        "gaps": [
            {
                "gap_start": g.gap_start.isoformat(),
                "gap_end": g.gap_end.isoformat(),
                "missing_bars": g.missing_bars,
                "reason": g.reason,
            }
            for g in rows
        ],
    }
