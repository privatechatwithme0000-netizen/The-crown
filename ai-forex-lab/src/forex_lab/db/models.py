"""SQLAlchemy ORM models for the AI Forex Lab.

Every backtest result traces to dataset, run, strategy version, config hash,
seed, execution mode, and account currency. Money is NUMERIC, timestamps are
TIMESTAMPTZ (UTC), configuration snapshots are JSONB. The audit log is
append-only by convention (no update/delete paths in the application).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, bigint_pk, money, price, timestamptz


class Provider(Base):
    __tablename__ = "providers"

    id: Mapped[bigint_pk]
    name: Mapped[str] = mapped_column(String(64), unique=True)
    display_name: Mapped[str] = mapped_column(String(128))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[timestamptz]


class BrokerEnvironmentRow(Base):
    __tablename__ = "broker_environments"

    id: Mapped[bigint_pk]
    provider_id: Mapped[int] = mapped_column(ForeignKey("providers.id"))
    name: Mapped[str] = mapped_column(String(64))  # practice/demo/synthetic
    description: Mapped[str] = mapped_column(String(256), default="")

    __table_args__ = (UniqueConstraint("provider_id", "name", name="uq_broker_env"),)


class InstrumentRow(Base):
    __tablename__ = "instruments"

    id: Mapped[bigint_pk]
    name: Mapped[str] = mapped_column(String(32), unique=True)  # AUD_CAD
    base_currency: Mapped[str] = mapped_column(String(8))
    quote_currency: Mapped[str] = mapped_column(String(8))
    pip_size: Mapped[price]
    pipette_size: Mapped[price]
    min_trade_size: Mapped[money]
    max_trade_size: Mapped[money]
    quantity_step: Mapped[money]
    contract_size: Mapped[money]
    margin_rate: Mapped[price]
    trading_status: Mapped[str] = mapped_column(String(32), default="TRADABLE")


class SymbolMapping(Base):
    __tablename__ = "symbol_mappings"

    id: Mapped[bigint_pk]
    provider_id: Mapped[int] = mapped_column(ForeignKey("providers.id"))
    instrument_name: Mapped[str] = mapped_column(String(32))
    provider_symbol: Mapped[str] = mapped_column(String(64))  # AUDCAD.a, AUDCADm ...

    __table_args__ = (UniqueConstraint("provider_id", "instrument_name", name="uq_symbol_map"),)


class Dataset(Base):
    """A dataset is permanently pinned to one provider/env/instrument/timeframe.

    Datasets from different providers are never merged. A fallback dataset is
    flagged via ``source_class`` (SECONDARY/DEGRADED).
    """

    __tablename__ = "datasets"

    id: Mapped[bigint_pk]
    provider: Mapped[str] = mapped_column(String(64))
    broker_environment: Mapped[str] = mapped_column(String(64))
    instrument: Mapped[str] = mapped_column(String(32))
    timeframe: Mapped[str] = mapped_column(String(8))
    price_component: Mapped[str] = mapped_column(String(16))
    start_time: Mapped[timestamptz]
    end_time: Mapped[timestamptz]
    source_class: Mapped[str] = mapped_column(String(16), default="PRIMARY")
    candle_count: Mapped[int] = mapped_column(Integer, default=0)
    provenance: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[timestamptz]

    candles: Mapped[list[Candle]] = relationship(back_populates="dataset")

    __table_args__ = (
        Index(
            "ix_dataset_pin",
            "provider",
            "broker_environment",
            "instrument",
            "timeframe",
            "price_component",
        ),
    )


class Candle(Base):
    __tablename__ = "candles"

    id: Mapped[bigint_pk]
    dataset_id: Mapped[int] = mapped_column(ForeignKey("datasets.id"))
    instrument: Mapped[str] = mapped_column(String(32))
    timeframe: Mapped[str] = mapped_column(String(8))
    provider: Mapped[str] = mapped_column(String(64))
    broker_environment: Mapped[str] = mapped_column(String(64))
    timestamp: Mapped[timestamptz]

    bid_open: Mapped[price]
    bid_high: Mapped[price]
    bid_low: Mapped[price]
    bid_close: Mapped[price]
    ask_open: Mapped[price]
    ask_high: Mapped[price]
    ask_low: Mapped[price]
    ask_close: Mapped[price]
    mid_open: Mapped[price]
    mid_high: Mapped[price]
    mid_low: Mapped[price]
    mid_close: Mapped[price]

    tick_volume: Mapped[int] = mapped_column(Integer, default=0)
    spread_open: Mapped[price]
    spread_close: Mapped[price]
    complete: Mapped[bool] = mapped_column(Boolean, default=True)

    dataset: Mapped[Dataset] = relationship(back_populates="candles")

    __table_args__ = (
        UniqueConstraint("dataset_id", "timestamp", name="uq_candle_ts"),
        Index("ix_candle_dataset_ts", "dataset_id", "timestamp"),
    )


class DataGap(Base):
    __tablename__ = "data_gaps"

    id: Mapped[bigint_pk]
    dataset_id: Mapped[int] = mapped_column(ForeignKey("datasets.id"))
    gap_start: Mapped[timestamptz]
    gap_end: Mapped[timestamptz]
    missing_bars: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(64), default="MISSING")
    created_at: Mapped[timestamptz]


class Strategy(Base):
    __tablename__ = "strategies"

    id: Mapped[bigint_pk]
    key: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[timestamptz]

    versions: Mapped[list[StrategyVersion]] = relationship(back_populates="strategy")


class StrategyVersion(Base):
    __tablename__ = "strategy_versions"

    id: Mapped[bigint_pk]
    strategy_id: Mapped[int] = mapped_column(ForeignKey("strategies.id"))
    strategy_key: Mapped[str] = mapped_column(String(64))
    semver: Mapped[str] = mapped_column(String(32))
    parameters: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    source_hash: Mapped[str] = mapped_column(String(64))
    is_retired: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[timestamptz]

    strategy: Mapped[Strategy] = relationship(back_populates="versions")

    __table_args__ = (UniqueConstraint("strategy_key", "semver", name="uq_strategy_version"),)


class BacktestRun(Base):
    __tablename__ = "backtest_runs"

    id: Mapped[bigint_pk]
    strategy_version_id: Mapped[int] = mapped_column(ForeignKey("strategy_versions.id"))
    dataset_id: Mapped[int] = mapped_column(ForeignKey("datasets.id"))
    execution_mode: Mapped[str] = mapped_column(String(32))
    account_currency: Mapped[str] = mapped_column(String(8))
    seed: Mapped[int] = mapped_column(Integer)
    config_hash: Mapped[str] = mapped_column(String(64))
    config_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(32), default="PENDING")
    started_at: Mapped[timestamptz]
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class BacktestSplit(Base):
    __tablename__ = "backtest_splits"

    id: Mapped[bigint_pk]
    run_id: Mapped[int] = mapped_column(ForeignKey("backtest_runs.id"))
    kind: Mapped[str] = mapped_column(String(32))  # TRAIN/VALIDATION/OOS/WF_WINDOW
    window_index: Mapped[int] = mapped_column(Integer, default=0)
    start_time: Mapped[timestamptz]
    end_time: Mapped[timestamptz]


class BacktestResult(Base):
    __tablename__ = "backtest_results"

    id: Mapped[bigint_pk]
    run_id: Mapped[int] = mapped_column(ForeignKey("backtest_runs.id"))
    split_id: Mapped[int | None] = mapped_column(ForeignKey("backtest_splits.id"), nullable=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey("datasets.id"))
    strategy_version_id: Mapped[int] = mapped_column(ForeignKey("strategy_versions.id"))
    config_hash: Mapped[str] = mapped_column(String(64))
    seed: Mapped[int] = mapped_column(Integer)
    execution_mode: Mapped[str] = mapped_column(String(32))
    account_currency: Mapped[str] = mapped_column(String(8))
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[timestamptz]


class Signal(Base):
    __tablename__ = "signals"

    id: Mapped[bigint_pk]
    run_id: Mapped[int | None] = mapped_column(ForeignKey("backtest_runs.id"), nullable=True)
    strategy_version_id: Mapped[int] = mapped_column(ForeignKey("strategy_versions.id"))
    instrument: Mapped[str] = mapped_column(String(32))
    timestamp: Mapped[timestamptz]
    action: Mapped[str] = mapped_column(String(8))  # BUY/SELL/HOLD/CLOSE
    confidence: Mapped[price]
    explanation: Mapped[str] = mapped_column(Text, default="")
    indicator_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    suggested_stop_distance: Mapped[price | None] = mapped_column(nullable=True)
    suggested_target_distance: Mapped[price | None] = mapped_column(nullable=True)


class AgentDecision(Base):
    __tablename__ = "agent_decisions"

    id: Mapped[bigint_pk]
    run_id: Mapped[int | None] = mapped_column(ForeignKey("backtest_runs.id"), nullable=True)
    signal_id: Mapped[int | None] = mapped_column(ForeignKey("signals.id"), nullable=True)
    agent: Mapped[str] = mapped_column(String(64))
    timestamp: Mapped[timestamptz]
    output: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class RiskDecision(Base):
    __tablename__ = "risk_decisions"

    id: Mapped[bigint_pk]
    run_id: Mapped[int | None] = mapped_column(ForeignKey("backtest_runs.id"), nullable=True)
    signal_id: Mapped[int | None] = mapped_column(ForeignKey("signals.id"), nullable=True)
    timestamp: Mapped[timestamptz]
    outcome: Mapped[str] = mapped_column(String(16))  # APPROVED/REJECTED
    reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    suggested_quantity: Mapped[money | None] = mapped_column(nullable=True)
    risk_score: Mapped[price | None] = mapped_column(nullable=True)
    detail: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[bigint_pk]
    run_id: Mapped[int | None] = mapped_column(ForeignKey("backtest_runs.id"), nullable=True)
    execution_mode: Mapped[str] = mapped_column(String(32))
    signal_id: Mapped[int | None] = mapped_column(ForeignKey("signals.id"), nullable=True)
    strategy_version_id: Mapped[int] = mapped_column(ForeignKey("strategy_versions.id"))
    instrument: Mapped[str] = mapped_column(String(32))
    side: Mapped[str] = mapped_column(String(8))
    order_type: Mapped[str] = mapped_column(String(16))
    quantity: Mapped[money]
    reference_price: Mapped[price | None] = mapped_column(nullable=True)
    stop_loss: Mapped[price | None] = mapped_column(nullable=True)
    take_profit: Mapped[price | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="PENDING")
    reason: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[timestamptz]


class Fill(Base):
    __tablename__ = "fills"

    id: Mapped[bigint_pk]
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"))
    run_id: Mapped[int | None] = mapped_column(ForeignKey("backtest_runs.id"), nullable=True)
    execution_mode: Mapped[str] = mapped_column(String(32))
    strategy_version_id: Mapped[int] = mapped_column(ForeignKey("strategy_versions.id"))
    instrument: Mapped[str] = mapped_column(String(32))
    side: Mapped[str] = mapped_column(String(8))
    quantity: Mapped[money]
    timestamp: Mapped[timestamptz]
    reference_price: Mapped[price]
    fill_price: Mapped[price]
    bid: Mapped[price]
    ask: Mapped[price]
    spread: Mapped[price]
    slippage: Mapped[price]
    commission: Mapped[money]
    reason: Mapped[str] = mapped_column(String(64), default="")


class Trade(Base):
    """A closed round-trip trade (entry + exit)."""

    __tablename__ = "trades"

    id: Mapped[bigint_pk]
    run_id: Mapped[int | None] = mapped_column(ForeignKey("backtest_runs.id"), nullable=True)
    execution_mode: Mapped[str] = mapped_column(String(32))
    strategy_version_id: Mapped[int] = mapped_column(ForeignKey("strategy_versions.id"))
    instrument: Mapped[str] = mapped_column(String(32))
    side: Mapped[str] = mapped_column(String(8))
    quantity: Mapped[money]
    entry_time: Mapped[timestamptz]
    exit_time: Mapped[timestamptz]
    entry_price: Mapped[price]
    exit_price: Mapped[price]
    gross_pnl: Mapped[money]
    net_pnl: Mapped[money]
    pips: Mapped[price]
    commission: Mapped[money]
    slippage_cost: Mapped[money]
    spread_cost: Mapped[money]
    financing: Mapped[money]
    exit_reason: Mapped[str] = mapped_column(String(64))
    ambiguous_intrabar: Mapped[bool] = mapped_column(Boolean, default=False)


class Position(Base):
    __tablename__ = "positions"

    id: Mapped[bigint_pk]
    run_id: Mapped[int | None] = mapped_column(ForeignKey("backtest_runs.id"), nullable=True)
    execution_mode: Mapped[str] = mapped_column(String(32))
    instrument: Mapped[str] = mapped_column(String(32))
    side: Mapped[str] = mapped_column(String(8))
    quantity: Mapped[money]
    entry_price: Mapped[price]
    opened_at: Mapped[timestamptz]
    closed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    is_open: Mapped[bool] = mapped_column(Boolean, default=True)


class EquitySnapshot(Base):
    __tablename__ = "equity_snapshots"

    id: Mapped[bigint_pk]
    run_id: Mapped[int | None] = mapped_column(ForeignKey("backtest_runs.id"), nullable=True)
    execution_mode: Mapped[str] = mapped_column(String(32))
    timestamp: Mapped[timestamptz]
    equity: Mapped[money]
    cash: Mapped[money]
    realized_pnl: Mapped[money]
    unrealized_pnl: Mapped[money]
    used_margin: Mapped[money]
    free_margin: Mapped[money]
    exposure: Mapped[money]

    __table_args__ = (Index("ix_equity_run_ts", "run_id", "timestamp"),)


class MetricsReport(Base):
    __tablename__ = "metrics_reports"

    id: Mapped[bigint_pk]
    run_id: Mapped[int] = mapped_column(ForeignKey("backtest_runs.id"))
    split_kind: Mapped[str] = mapped_column(String(32), default="FULL")
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[timestamptz]


class StrategyRanking(Base):
    __tablename__ = "strategy_rankings"

    id: Mapped[bigint_pk]
    strategy_version_id: Mapped[int] = mapped_column(ForeignKey("strategy_versions.id"))
    run_id: Mapped[int] = mapped_column(ForeignKey("backtest_runs.id"))
    eligible: Mapped[bool] = mapped_column(Boolean)
    score: Mapped[price | None] = mapped_column(nullable=True)
    eligibility_failures: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    score_breakdown: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[timestamptz]


class StrategyGraveyard(Base):
    __tablename__ = "strategy_graveyard"

    id: Mapped[bigint_pk]
    strategy_key: Mapped[str] = mapped_column(String(64))
    semver: Mapped[str] = mapped_column(String(32))
    parameters: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    source_hash: Mapped[str] = mapped_column(String(64))
    dataset_id: Mapped[int | None] = mapped_column(ForeignKey("datasets.id"), nullable=True)
    backtest_start: Mapped[datetime | None] = mapped_column(nullable=True)
    backtest_end: Mapped[datetime | None] = mapped_column(nullable=True)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    max_drawdown: Mapped[price | None] = mapped_column(nullable=True)
    max_consecutive_losses: Mapped[int | None] = mapped_column(nullable=True)
    failure_reason: Mapped[str] = mapped_column(Text)
    eligibility_failures: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    notes: Mapped[str] = mapped_column(Text, default="")
    retired_at: Mapped[timestamptz]


class AuditLog(Base):
    """Append-only event log. The application never updates or deletes rows."""

    __tablename__ = "audit_log"

    id: Mapped[bigint_pk]
    run_id: Mapped[int | None] = mapped_column(ForeignKey("backtest_runs.id"), nullable=True)
    execution_mode: Mapped[str | None] = mapped_column(String(32), nullable=True)
    event_type: Mapped[str] = mapped_column(String(48))
    timestamp: Mapped[timestamptz]
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    __table_args__ = (Index("ix_audit_run_type", "run_id", "event_type"),)


class Commentary(Base):
    """LLM commentary. Stored separately; never read back into decisions."""

    __tablename__ = "commentary"

    id: Mapped[bigint_pk]
    run_id: Mapped[int | None] = mapped_column(ForeignKey("backtest_runs.id"), nullable=True)
    subject: Mapped[str] = mapped_column(String(64))  # e.g. BACKTEST_SUMMARY
    content: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(String(64), default="none")
    created_at: Mapped[timestamptz]
