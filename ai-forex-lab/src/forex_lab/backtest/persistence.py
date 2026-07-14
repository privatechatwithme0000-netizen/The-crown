"""Persist backtest runs and outcomes to PostgreSQL.

Converts stored candle rows into domain candles, runs the deterministic engine,
and writes signals, risk decisions, orders, fills, trades, equity snapshots,
metrics, and audit events. Every result row carries full provenance
(dataset/run/version/config_hash/seed/mode/account currency).
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from forex_lab.db import models
from forex_lab.domain.candle import Candle
from forex_lab.domain.enums import Timeframe
from forex_lab.metrics import compute_metrics
from forex_lab.strategies.base import Strategy

from .config import BacktestConfig
from .engine import Backtester, BacktestOutcome


def _now() -> datetime:
    return datetime.now(tz=UTC)


def db_candle_to_domain(row: models.Candle) -> Candle:
    return Candle(
        timestamp=row.timestamp,
        instrument=row.instrument,
        timeframe=Timeframe(row.timeframe),
        bid_open=row.bid_open,
        bid_high=row.bid_high,
        bid_low=row.bid_low,
        bid_close=row.bid_close,
        ask_open=row.ask_open,
        ask_high=row.ask_high,
        ask_low=row.ask_low,
        ask_close=row.ask_close,
        tick_volume=row.tick_volume,
        complete=row.complete,
    )


async def ensure_strategy_version(
    session: AsyncSession, strategy: Strategy
) -> models.StrategyVersion:
    """Get-or-create the Strategy and StrategyVersion rows for pinning."""
    fp = strategy.version_fingerprint()
    strat = (
        await session.execute(select(models.Strategy).where(models.Strategy.key == strategy.key))
    ).scalar_one_or_none()
    if strat is None:
        strat = models.Strategy(
            key=strategy.key, name=strategy.key, description="", created_at=_now()
        )
        session.add(strat)
        await session.flush()

    version = (
        await session.execute(
            select(models.StrategyVersion).where(
                models.StrategyVersion.strategy_key == strategy.key,
                models.StrategyVersion.semver == strategy.semver,
            )
        )
    ).scalar_one_or_none()
    if version is None:
        version = models.StrategyVersion(
            strategy_id=strat.id,
            strategy_key=strategy.key,
            semver=strategy.semver,
            parameters=fp["parameters"],
            source_hash=fp["source_hash"],
            created_at=_now(),
        )
        session.add(version)
        await session.flush()
    return version


async def load_domain_candles(session: AsyncSession, dataset_id: int) -> list[Candle]:
    rows = (
        (
            await session.execute(
                select(models.Candle)
                .where(models.Candle.dataset_id == dataset_id)
                .order_by(models.Candle.timestamp)
            )
        )
        .scalars()
        .all()
    )
    return [db_candle_to_domain(r) for r in rows]


async def run_and_persist(
    session: AsyncSession,
    *,
    dataset_id: int,
    strategy: Strategy,
    config: BacktestConfig,
) -> tuple[int, dict[str, object]]:
    """Run a backtest over a dataset and persist everything. Returns (run_id, metrics)."""
    version = await ensure_strategy_version(session, strategy)
    run = models.BacktestRun(
        strategy_version_id=version.id,
        dataset_id=dataset_id,
        execution_mode=config.execution_mode.value,
        account_currency=config.account_currency,
        seed=config.seed,
        config_hash=config.config_hash(),
        config_snapshot=config.snapshot(),
        status="RUNNING",
        started_at=_now(),
    )
    session.add(run)
    await session.flush()

    try:
        candles = await load_domain_candles(session, dataset_id)
        if not candles:
            raise ValueError(f"dataset {dataset_id} has no candles")
        outcome = Backtester(strategy=strategy, config=config).run(candles)
        metrics = compute_metrics(outcome, config.timeframe, config.initial_cash).values
        await _persist_outcome(session, run, version.id, dataset_id, config, outcome, metrics)
        run.status = "COMPLETED"
        run.finished_at = _now()
    except Exception as exc:
        run.status = "FAILED"
        run.finished_at = _now()
        run.error = str(exc)
        session.add(
            models.AuditLog(
                run_id=run.id,
                execution_mode=config.execution_mode.value,
                event_type="BACKTEST_FAILURE",
                timestamp=_now(),
                payload={"error": str(exc)},
            )
        )
        raise
    return run.id, metrics


async def _persist_outcome(
    session: AsyncSession,
    run: models.BacktestRun,
    version_id: int,
    dataset_id: int,
    config: BacktestConfig,
    outcome: BacktestOutcome,
    metrics: dict[str, object],
) -> None:
    mode = config.execution_mode.value

    for s in outcome.signals:
        session.add(
            models.Signal(
                run_id=run.id,
                strategy_version_id=version_id,
                instrument=config.instrument,
                timestamp=s.timestamp,
                action=s.action,
                confidence=s.confidence,
                explanation=s.explanation,
                indicator_snapshot=s.snapshot,
                suggested_stop_distance=s.suggested_stop_distance,
                suggested_target_distance=s.suggested_target_distance,
            )
        )
    for r in outcome.risk_events:
        session.add(
            models.RiskDecision(
                run_id=run.id,
                timestamp=r.timestamp,
                outcome=r.outcome,
                reason=r.reason,
                suggested_quantity=r.suggested_quantity,
                risk_score=r.risk_score,
                detail=r.detail,
            )
        )
    for f in outcome.fills:
        order = models.Order(
            run_id=run.id,
            execution_mode=mode,
            strategy_version_id=version_id,
            instrument=config.instrument,
            side=f.side.value,
            order_type="MARKET",
            quantity=f.quantity,
            reference_price=f.reference_price,
            status="FILLED",
            reason=f.reason,
            created_at=f.timestamp,
        )
        session.add(order)
        await session.flush()
        session.add(
            models.Fill(
                order_id=order.id,
                run_id=run.id,
                execution_mode=mode,
                strategy_version_id=version_id,
                instrument=config.instrument,
                side=f.side.value,
                quantity=f.quantity,
                timestamp=f.timestamp,
                reference_price=f.reference_price,
                fill_price=f.fill_price,
                bid=f.bid,
                ask=f.ask,
                spread=f.spread,
                slippage=f.slippage,
                commission=f.commission,
                reason=f.reason,
            )
        )
    for t in outcome.trades:
        session.add(
            models.Trade(
                run_id=run.id,
                execution_mode=mode,
                strategy_version_id=version_id,
                instrument=config.instrument,
                side=t.side.value,
                quantity=t.quantity,
                entry_time=t.entry_time,
                exit_time=t.exit_time,
                entry_price=t.entry_price,
                exit_price=t.exit_price,
                gross_pnl=t.gross_pnl,
                net_pnl=t.net_pnl,
                pips=t.pips,
                commission=t.commission,
                slippage_cost=t.slippage_cost,
                spread_cost=t.spread_cost,
                financing=t.financing,
                exit_reason=t.exit_reason,
                ambiguous_intrabar=t.ambiguous_intrabar,
            )
        )
    for eq in outcome.equity_curve:
        session.add(
            models.EquitySnapshot(
                run_id=run.id,
                execution_mode=mode,
                timestamp=eq.timestamp,
                equity=eq.equity,
                cash=eq.cash,
                realized_pnl=eq.realized_pnl,
                unrealized_pnl=eq.unrealized_pnl,
                used_margin=eq.used_margin,
                free_margin=eq.free_margin,
                exposure=eq.exposure,
            )
        )
    for ev in outcome.audit:
        session.add(
            models.AuditLog(
                run_id=run.id,
                execution_mode=mode,
                event_type=ev.event_type,
                timestamp=ev.timestamp,
                payload=ev.payload,
            )
        )
    session.add(
        models.BacktestResult(
            run_id=run.id,
            dataset_id=dataset_id,
            strategy_version_id=version_id,
            config_hash=config.config_hash(),
            seed=config.seed,
            execution_mode=mode,
            account_currency=config.account_currency,
            metrics=metrics,
            created_at=_now(),
        )
    )
    session.add(
        models.MetricsReport(run_id=run.id, split_kind="FULL", metrics=metrics, created_at=_now())
    )
