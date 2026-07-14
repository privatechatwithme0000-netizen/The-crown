"""Backtest endpoints: start, status, trades, signals, rejections, equity,
metrics, baseline comparison, walk-forward."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from forex_lab.api.deps import db_session
from forex_lab.backtest.config import BacktestConfig
from forex_lab.backtest.engine import Backtester
from forex_lab.backtest.persistence import load_domain_candles, run_and_persist
from forex_lab.backtest.walkforward import run_walk_forward
from forex_lab.baselines import available_baselines, get_baseline_class
from forex_lab.db import models
from forex_lab.domain.enums import ExecutionMode, Timeframe
from forex_lab.metrics import compute_metrics
from forex_lab.ranking import RankingConfig, rank_strategy
from forex_lab.risk.sizing import ConversionRates
from forex_lab.strategies import get_strategy_class

router = APIRouter(prefix="/backtests", tags=["backtests"])


class BacktestRequest(BaseModel):
    dataset_id: int
    strategy_key: str
    parameters: dict[str, Any] = {}
    account_currency: str = "USD"
    initial_cash: str = "10000"
    seed: int = 12345
    conversions: dict[str, str] = {}


def _config_from_request(req: BacktestRequest, timeframe: Timeframe) -> BacktestConfig:
    return BacktestConfig(
        instrument="AUD_CAD",
        timeframe=timeframe,
        account_currency=req.account_currency,
        initial_cash=Decimal(req.initial_cash),
        seed=req.seed,
        execution_mode=ExecutionMode.BACKTEST,
        conversions=ConversionRates({k: Decimal(v) for k, v in req.conversions.items()}),
    )


async def _dataset_timeframe(session: AsyncSession, dataset_id: int) -> Timeframe:
    ds = await session.get(models.Dataset, dataset_id)
    if ds is None:
        raise HTTPException(status_code=404, detail="dataset not found")
    return Timeframe(ds.timeframe)


@router.post("/run")
async def start_backtest(
    req: BacktestRequest, session: AsyncSession = Depends(db_session)
) -> dict[str, Any]:
    try:
        cls = get_strategy_class(req.strategy_key)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    timeframe = await _dataset_timeframe(session, req.dataset_id)
    config = _config_from_request(req, timeframe)
    strategy = cls(**req.parameters)
    try:
        run_id, metrics = await run_and_persist(
            session, dataset_id=req.dataset_id, strategy=strategy, config=config
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"run_id": run_id, "status": "COMPLETED", "metrics": metrics}


@router.get("/{run_id}")
async def get_status(run_id: int, session: AsyncSession = Depends(db_session)) -> dict[str, Any]:
    run = await session.get(models.BacktestRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    return {
        "run_id": run.id,
        "status": run.status,
        "config_hash": run.config_hash,
        "seed": run.seed,
        "execution_mode": run.execution_mode,
        "account_currency": run.account_currency,
        "error": run.error,
    }


@router.get("/{run_id}/trades")
async def get_trades(run_id: int, session: AsyncSession = Depends(db_session)) -> dict[str, Any]:
    rows = (
        (await session.execute(select(models.Trade).where(models.Trade.run_id == run_id)))
        .scalars()
        .all()
    )
    return {
        "run_id": run_id,
        "trades": [
            {
                "side": t.side,
                "quantity": str(t.quantity),
                "entry_time": t.entry_time.isoformat(),
                "exit_time": t.exit_time.isoformat(),
                "entry_price": str(t.entry_price),
                "exit_price": str(t.exit_price),
                "net_pnl": str(t.net_pnl),
                "pips": str(t.pips),
                "exit_reason": t.exit_reason,
                "ambiguous_intrabar": t.ambiguous_intrabar,
            }
            for t in rows
        ],
    }


@router.get("/{run_id}/signals")
async def get_signals(run_id: int, session: AsyncSession = Depends(db_session)) -> dict[str, Any]:
    rows = (
        (await session.execute(select(models.Signal).where(models.Signal.run_id == run_id)))
        .scalars()
        .all()
    )
    return {
        "run_id": run_id,
        "signals": [
            {
                "timestamp": s.timestamp.isoformat(),
                "action": s.action,
                "confidence": str(s.confidence),
                "explanation": s.explanation,
            }
            for s in rows
        ],
    }


@router.get("/{run_id}/rejections")
async def get_rejections(
    run_id: int, session: AsyncSession = Depends(db_session)
) -> dict[str, Any]:
    rows = (
        (
            await session.execute(
                select(models.RiskDecision).where(
                    models.RiskDecision.run_id == run_id,
                    models.RiskDecision.outcome == "REJECTED",
                )
            )
        )
        .scalars()
        .all()
    )
    return {
        "run_id": run_id,
        "rejections": [
            {"timestamp": r.timestamp.isoformat(), "reason": r.reason, "detail": r.detail}
            for r in rows
        ],
    }


@router.get("/{run_id}/equity")
async def get_equity(run_id: int, session: AsyncSession = Depends(db_session)) -> dict[str, Any]:
    rows = (
        (
            await session.execute(
                select(models.EquitySnapshot)
                .where(models.EquitySnapshot.run_id == run_id)
                .order_by(models.EquitySnapshot.timestamp)
            )
        )
        .scalars()
        .all()
    )
    return {
        "run_id": run_id,
        "equity_curve": [
            {"timestamp": e.timestamp.isoformat(), "equity": str(e.equity)} for e in rows
        ],
    }


@router.get("/{run_id}/metrics")
async def get_metrics(run_id: int, session: AsyncSession = Depends(db_session)) -> dict[str, Any]:
    row = (
        await session.execute(
            select(models.MetricsReport).where(models.MetricsReport.run_id == run_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="metrics not found")
    ranking = rank_strategy(row.metrics, RankingConfig())
    return {
        "run_id": run_id,
        "metrics": row.metrics,
        "eligible": ranking.eligible,
        "score": None if ranking.score is None else str(ranking.score),
        "eligibility_failures": ranking.failures,
    }


@router.post("/{run_id}/compare-baselines")
async def compare_baselines(
    run_id: int, session: AsyncSession = Depends(db_session)
) -> dict[str, Any]:
    run = await session.get(models.BacktestRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    timeframe = await _dataset_timeframe(session, run.dataset_id)
    candles = await load_domain_candles(session, run.dataset_id)
    if not candles:
        raise HTTPException(status_code=400, detail="dataset has no candles")
    config = BacktestConfig(
        timeframe=timeframe,
        account_currency=run.account_currency,
        initial_cash=Decimal(str(run.config_snapshot.get("initial_cash", "10000"))),
        seed=run.seed,
        conversions=ConversionRates(
            {k: Decimal(v) for k, v in run.config_snapshot.get("conversions", {}).items()}
        ),
    )
    results: dict[str, Any] = {}
    for key in available_baselines():
        strategy = get_baseline_class(key)()
        outcome = Backtester(strategy=strategy, config=config).run(candles)
        m = compute_metrics(outcome, timeframe, config.initial_cash).values
        results[key] = {"num_trades": m["num_trades"], "net_pnl": m["net_pnl"]}
    return {"run_id": run_id, "baselines": results}


@router.get("/{run_id}/commentary")
async def get_commentary(
    run_id: int, session: AsyncSession = Depends(db_session)
) -> dict[str, Any]:
    rows = (
        (
            await session.execute(
                select(models.Commentary)
                .where(models.Commentary.run_id == run_id)
                .order_by(models.Commentary.created_at)
            )
        )
        .scalars()
        .all()
    )
    return {
        "run_id": run_id,
        "commentary": [
            {"subject": c.subject, "model": c.model, "content": c.content} for c in rows
        ],
    }


class WalkForwardRequest(BaseModel):
    dataset_id: int
    strategy_key: str
    parameters: dict[str, Any] = {}
    account_currency: str = "USD"
    initial_cash: str = "10000"
    seed: int = 12345
    conversions: dict[str, str] = {}
    train_size: int = 500
    test_size: int = 200
    step: int | None = None


@router.post("/walk-forward")
async def walk_forward(
    req: WalkForwardRequest, session: AsyncSession = Depends(db_session)
) -> dict[str, Any]:
    try:
        cls = get_strategy_class(req.strategy_key)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    timeframe = await _dataset_timeframe(session, req.dataset_id)
    candles = await load_domain_candles(session, req.dataset_id)
    if not candles:
        raise HTTPException(status_code=400, detail="dataset has no candles")
    config = BacktestConfig(
        instrument="AUD_CAD",
        timeframe=timeframe,
        account_currency=req.account_currency,
        initial_cash=Decimal(req.initial_cash),
        seed=req.seed,
        conversions=ConversionRates({k: Decimal(v) for k, v in req.conversions.items()}),
    )
    try:
        report = run_walk_forward(
            candles=candles,
            strategy_factory=cls,
            parameters=req.parameters,
            config=config,
            train_size=req.train_size,
            test_size=req.test_size,
            step=req.step,
            timeframe=timeframe,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "num_windows": report.num_windows,
        "stability": str(report.stability),
        "mean_net_pnl": str(report.mean_net_pnl),
        "windows": [
            {
                "index": w.index,
                "train": [w.train_start, w.train_end],
                "test": [w.test_start, w.test_end],
                "net_pnl": w.metrics["net_pnl"],
                "num_trades": w.metrics["num_trades"],
            }
            for w in report.windows
        ],
    }
