# AI Forex Lab — Phase 1

A **deterministic** forex strategy research and paper-trading platform. First
instrument **AUD_CAD**, default timeframe **M15**.

> This is a strategy-research laboratory, **not** a guaranteed-profit trading
> bot. Phase 1 makes **no profitability claim**, hides no losing trades, and
> contains **no real-money execution path**. `LIVE_EXECUTION_ENABLED=false` is
> enforced.

## What Phase 1 does

- Ingests and stores historical AUD/CAD candles (bid / ask / mid) with full
  dataset provenance and gap tracking.
- Runs deterministic indicators, strategies, agents, a risk engine, and a
  paper broker inside an event-driven, bid/ask-aware, next-bar-open backtester.
- Models spread, slippage, commission, and (labeled) financing.
- Computes timeframe-aware metrics, applies eligibility gates, ranks
  strategies, and retires failures to a Strategy Graveyard.
- Exposes a REST API and an optional read-only LLM commentary layer that
  **cannot** create or modify trades.

## Non-negotiable determinism

The same `(dataset_id, strategy_version_id, configuration, seed)` always
produces byte-identical signals, orders, fills, trades, equity curve, and
metrics. No LLM makes, approves, resizes, or executes any trade.

## Quick start (Docker)

```bash
cp .env.example .env          # fill in values; OANDA optional for backtests
docker compose up --build     # starts postgres + redis + api, runs migrations
curl http://localhost:8000/health/ready
open http://localhost:8000/docs
```

## Local development

```bash
python -m venv .venv && source .venv/bin/activate
make install
make check      # ruff + mypy --strict + pytest
```

Point at a local Postgres/Redis by editing `.env` (`POSTGRES_HOST=localhost`,
`REDIS_HOST=localhost`), then `make migrate`.

## Execution modes

Every order, fill, and trade is labeled with the mode that created it:
`BACKTEST`, `INTERNAL_PAPER`, `OANDA_PRACTICE`. Results from different modes —
and datasets from different providers — are never mixed without labeling.

## Layout

See `docs/ARCHITECTURE.md` for the module map and data flow, and
`docs/PHASE1.md` for the acceptance-criteria checklist.

## Safety

- `LIVE_EXECUTION_ENABLED=false` hard-blocks any real-money order path; the app
  refuses to start a live execution service.
- Secrets come from `.env` only; OANDA tokens and DB/Redis passwords are
  redacted from logs.
