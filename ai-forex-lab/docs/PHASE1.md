# Phase 1 acceptance criteria

Status of each criterion and where it is satisfied. Items requiring a live
PostgreSQL/Redis are marked **[needs stack]** and are exercised by
`docker compose up` and the DB-guarded integration tests
(`FOREX_LAB_TEST_DB=1`).

| # | Criterion | Where |
|---|-----------|-------|
| 1 | `docker compose up` starts FastAPI, Postgres, Redis | `docker-compose.yml`, `Dockerfile` **[needs stack]** |
| 2 | Migrations apply from empty DB | `alembic/versions/0001_initial.py` (metadata) **[needs stack]** |
| 3 | `/health/ready` confirms DB + Redis | `api/health.py::readiness` |
| 4 | OANDA practice configuration supported | `config.py`, `providers/oanda.py` |
| 5 | AUD/CAD historical candles ingested | `marketdata/ingest.py`, `api/marketdata.py` |
| 6 | Bid, ask, mid preserved | `domain/candle.py`, `db/models.py::Candle` |
| 7 | Dataset provenance stored | `marketdata/dataset.py`, `db/models.py::Dataset` |
| 8 | Provider datasets never mix | `providers/registry.py`, `test_providers_and_gaps.py` |
| 9 | Data gaps recorded | `marketdata/gaps.py`, `test_providers_and_gaps.py` |
| 10 | M15 default timeframe | `config.py`, `domain/enums.py` |
| 11 | Indicators return None during warmup | `indicators/core.py`, `test_indicators_and_causality.py` |
| 12 | Future access raises LookAheadError | `marketdata/causal_view.py`, same test |
| 13 | Signals after bar t fill ≥ t+1 open | `backtest/engine.py`, `test_backtest_engine.py` |
| 14 | Long entries use ask | `execution/costs.py`, `test_execution_costs.py` |
| 15 | Long exits use bid | same |
| 16 | Short entries use bid | same |
| 17 | Short exits use ask | same |
| 18 | Spread costs reduce returns | `broker/paper_broker.py`, metrics `total_spread_cost` |
| 19 | Slippage reduces returns | `execution/costs.py`, engine |
| 20 | Commission tracked separately | `execution/costs.py`, metrics `total_commission` |
| 21 | Account-currency position sizing | `risk/sizing.py`, `test_sizing.py` |
| 22 | AUD/CAD pip calculations tested | `test_sizing.py`, `test_domain.py` |
| 23 | JPY pip calculations tested | `test_sizing.py::test_jpy_pair_sizing` |
| 24 | Risk rejections persisted | `db/models.py::RiskDecision`, `backtest/persistence.py` |
| 25 | HOLD signals persisted | `backtest/persistence.py`, engine records all signals |
| 26 | Every order & fill audited | `backtest/engine.py`, `db/models.py::AuditLog` |
| 27 | Buy-and-hold baseline runs | `baselines/__init__.py`, `test_splits_baselines_metrics.py` |
| 28 | Random-entry baseline deterministic | `baselines/__init__.py`, `test_determinism_and_strategies.py` |
| 29 | No-trade baseline runs | `test_splits_baselines_metrics.py` |
| 30 | Walk-forward windows chronological, non-overlapping | `backtest/splits.py`, tests |
| 31 | Timeframe-aware annualization | `domain/enums.py`, `metrics/compute.py`, tests |
| 32 | Losing trades & consecutive losses reported | `metrics/compute.py`, tests |
| 33 | Insufficient-trade strategies not eligible | `ranking/ranker.py`, `test_ranking_commentary_graveyard.py` |
| 34 | Failed strategies -> Strategy Graveyard | `ranking/graveyard.py`, `db/models.py`, `api/strategies.py` |
| 35 | Commentary cannot create/modify trades | `commentary/`, `test_ranking_commentary_graveyard.py` |
| 36 | Same seed & config -> identical output | `backtest/engine.py`, `test_determinism_and_strategies.py` |
| 37 | Ruff passes | `make lint` / CI |
| 38 | mypy --strict passes | `make typecheck` / CI |
| 39 | Tests pass | `make test` / CI |
| 40 | No profitability claim | README, commentary text, honest metrics |
| 41 | Real-money execution unavailable | `config.assert_live_execution_blocked`, `main.py`, `api/paper.py` |

## Running the checks

```bash
make check            # ruff + mypy --strict + pytest (no stack needed)
docker compose up     # full stack; migrations run on api startup
FOREX_LAB_TEST_DB=1 pytest tests/integration   # DB round-trip tests
```

## Honesty guarantees

- No fabricated backtest numbers: all results trace to a real dataset, run,
  strategy version, config snapshot, and seed. Synthetic data exists only in
  `tests/fixtures/` and is clearly labeled.
- Losing trades, HOLD signals, and risk rejections are persisted and reported —
  never hidden.
- Estimated financing is labeled (`financing_estimated`) and never presented as
  historical broker truth.
