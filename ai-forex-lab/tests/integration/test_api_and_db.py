"""Integration tests.

These require a running PostgreSQL and Redis and are skipped unless
``FOREX_LAB_TEST_DB=1`` is set. They exercise app construction, the health
endpoints, and a full ingest -> backtest -> metrics round trip against the DB.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from tests.conftest import requires_db


def test_app_builds_and_lists_routes() -> None:
    # Does not require the DB: pure app construction + OpenAPI resolution.
    from forex_lab.main import create_app

    app = create_app()
    paths = set(app.openapi()["paths"].keys())
    assert "/health/ready" in paths
    assert "/backtests/run" in paths
    assert "/marketdata/ingest" in paths


def test_live_execution_guard_blocks_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    from forex_lab.config import Settings

    settings = Settings(live_execution_enabled=True)
    with pytest.raises(RuntimeError):
        settings.assert_live_execution_blocked()


@requires_db
@pytest.mark.asyncio
async def test_health_ready() -> None:
    from forex_lab.main import create_app

    app = create_app()
    transport = ASGITransport(app=app)
    # lifespan runs the live-execution guard + engine init
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=transport, base_url="http://test") as client,
    ):
        resp = await client.get("/health/ready")
    assert resp.status_code == 200
    body = resp.json()
    assert body["postgres"] is True
    assert body["redis"] is True


@requires_db
@pytest.mark.asyncio
async def test_ingest_backtest_roundtrip() -> None:
    from tests.fixtures.synthetic import linear_series

    from forex_lab.backtest.config import BacktestConfig
    from forex_lab.backtest.persistence import run_and_persist
    from forex_lab.db import models
    from forex_lab.db.session import session_scope
    from forex_lab.domain.enums import Timeframe
    from forex_lab.risk.config import RiskConfig
    from forex_lab.risk.sizing import ConversionRates
    from forex_lab.strategies import TrendFollowing

    start = datetime(2024, 1, 2, tzinfo=UTC)
    candles = linear_series(120, start_time=start)

    async with session_scope() as session:
        dataset = models.Dataset(
            provider="csv",
            broker_environment="synthetic",
            instrument="AUD_CAD",
            timeframe="M15",
            price_component="BID_ASK",
            start_time=start,
            end_time=start + timedelta(minutes=15 * 120),
            source_class="PRIMARY",
            candle_count=len(candles),
            provenance={"synthetic": True},
            created_at=datetime.now(tz=UTC),
        )
        session.add(dataset)
        await session.flush()
        for c in candles:
            session.add(
                models.Candle(
                    dataset_id=dataset.id,
                    instrument=c.instrument,
                    timeframe=c.timeframe.value,
                    provider="csv",
                    broker_environment="synthetic",
                    timestamp=c.timestamp,
                    bid_open=c.bid_open,
                    bid_high=c.bid_high,
                    bid_low=c.bid_low,
                    bid_close=c.bid_close,
                    ask_open=c.ask_open,
                    ask_high=c.ask_high,
                    ask_low=c.ask_low,
                    ask_close=c.ask_close,
                    mid_open=c.mid_open,
                    mid_high=c.mid_high,
                    mid_low=c.mid_low,
                    mid_close=c.mid_close,
                    tick_volume=c.tick_volume,
                    spread_open=c.spread_open,
                    spread_close=c.spread_close,
                    complete=c.complete,
                )
            )
        dataset_id = dataset.id

    config = BacktestConfig(
        timeframe=Timeframe.M15,
        account_currency="CAD",
        initial_cash=Decimal("10000"),
        conversions=ConversionRates({}),
        risk=RiskConfig(respect_weekend=False),
    )
    async with session_scope() as session:
        run_id, metrics = await run_and_persist(
            session, dataset_id=dataset_id, strategy=TrendFollowing(), config=config
        )
    assert run_id > 0
    assert "num_trades" in metrics
