# Architecture

AI Forex Lab is a **deterministic** forex strategy-research platform. The core
principle: the same `(dataset_id, strategy_version_id, configuration, seed)`
always produces byte-identical signals, orders, fills, trades, equity curve, and
metrics. No LLM makes, approves, resizes, or executes a trade.

## Layered module map

```
domain/        pure value objects: enums, money (Decimal), instruments (pip
               logic), bid/ask/mid candle, trading-week/session calendar, errors
marketdata/    CausalView (look-ahead protection), dataset provenance/pinning,
               gap detection, ingestion orchestration
providers/     normalized provider protocol + CSV / OANDA practice / MT5
               adapters + explicit-failover registry
indicators/    causal Decimal indicators (None during warmup, never fake 0)
strategies/    versioned Strategy base + trend/mean-reversion/momentum/breakout
baselines/     buy-and-hold, no-trade, deterministic seeded random
agents/        market analyst, risk agent, decision engine (deterministic)
risk/          position sizing (currency conversion) + RiskGuard + RiskConfig
execution/     cost model (bid/ask fills, slippage, commission, financing) +
               execution adapters (internal no-op, OANDA practice-only)
broker/        deterministic paper broker (cash/margin/equity/P&L)
backtest/      shared per-bar runtime (BarProcessor) used by both the
               historical engine and live sessions, config+hashing,
               chronological splits, walk-forward orchestration, DB persistence
live/          real-time paper-trading session (streams candles through the
               same deterministic runtime; proven bit-identical to backtest)
metrics/       timeframe-aware metrics
ranking/       eligibility gates + scoring + graveyard
commentary/    read-only LLM layer (cannot trade)
db/            SQLAlchemy 2.0 models, base types, async session
cache/         Redis wrapper (cache only)
api/           FastAPI routers: health, marketdata, strategies, backtests, paper
```

**Isolation rule:** provider-specific code lives only in `providers/`. The
deterministic core (indicators → strategies → agents → risk → broker → backtest
→ metrics) consumes normalized `Candle`/`Instrument` value objects and never
imports a provider module. The commentary layer imports none of the trading
modules (enforced by a test).

## Data flow

1. **Ingest** — `providers.*` fetch native candles → normalized `Candle`
   (bid/ask/mid, `Decimal`) → `marketdata.dataset` pins a dataset to
   `(provider, broker_env, instrument, timeframe, price_component, start, end)`
   → candles persisted with `dataset_id` → gaps recorded (never interpolated).
2. **Backtest** — load one pinned dataset → wrap in `CausalView` → per bar `t`:
   fill queued orders at `t` open (bid/ask aware) → mark & check SL/TP within
   `t` → close bar → indicators consume completed `t` → strategy → agents →
   risk guard (persisted either way) → approved orders queued for `t+1` →
   audit. Then `metrics` → `ranking` → optional `commentary`.

## Determinism & safety

- All money/price/quantity/fee/P&L uses `Decimal` / `NUMERIC`. Floats appear
  only inside statistics (Sharpe/Sortino) after an explicit conversion.
- `LookAheadError` is raised on any future-bar access — an exception, not a
  warning.
- `LIVE_EXECUTION_ENABLED=false` is asserted on app startup; Phase 1 has no
  functional live-order path.
- Every order/fill/trade is tagged `BACKTEST | INTERNAL_PAPER | OANDA_PRACTICE`;
  datasets from different providers are never merged.

## Backtest event lifecycle

Decisions made after bar `t` closes fill no earlier than bar `t+1` open. Fills
read only bar `t`'s open (never its high/low/close). Intrabar stop/target uses
a conservative tie-break (`CONSERVATIVE_STOP_FIRST`) and counts
`AMBIGUOUS_INTRABAR_PATH` events.
