"""Ingestion orchestration.

Fetches candles via the provider registry, creates a pinned dataset row,
persists candles (bid/ask/mid), records gaps, and writes audit events. Datasets
from different providers are never merged: each fetch yields exactly one dataset
tied to one provider.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from forex_lab.db import models
from forex_lab.domain.enums import AuditEventType, PriceComponent, Timeframe
from forex_lab.providers.registry import FetchResult, ProviderRegistry

from .gaps import detect_gaps


@dataclass(frozen=True, slots=True)
class IngestionReport:
    dataset_id: int
    provider: str
    instrument: str
    timeframe: str
    candle_count: int
    gap_count: int
    used_failover: bool
    source_class: str


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


async def _audit(
    session: AsyncSession,
    event_type: AuditEventType,
    payload: dict[str, object],
) -> None:
    session.add(
        models.AuditLog(
            run_id=None,
            execution_mode=None,
            event_type=event_type.value,
            timestamp=_now(),
            payload=payload,
        )
    )


async def ingest_candles(
    session: AsyncSession,
    registry: ProviderRegistry,
    instrument: str,
    timeframe: Timeframe,
    start: datetime,
    end: datetime,
    price_component: PriceComponent = PriceComponent.BID_ASK,
) -> IngestionReport:
    """Fetch and persist candles into a single pinned dataset."""
    result: FetchResult = registry.fetch_candles(
        instrument, timeframe, start, end, price_component
    )
    spec = result.spec

    if result.used_failover:
        await _audit(
            session,
            AuditEventType.PROVIDER_FAILOVER,
            {"provider": result.provider_name, "chain": registry.names()},
        )

    dataset = models.Dataset(
        provider=spec.provider,
        broker_environment=spec.broker_environment,
        instrument=spec.instrument,
        timeframe=spec.timeframe.value,
        price_component=spec.price_component.value,
        start_time=spec.start_time,
        end_time=spec.end_time,
        source_class=spec.source_class.value,
        candle_count=len(result.candles),
        provenance={**spec.provenance, "spec_key": spec.key()},
        created_at=_now(),
    )
    session.add(dataset)
    await session.flush()  # assign dataset.id

    await _audit(
        session,
        AuditEventType.DATASET_CREATION,
        {"dataset_id": dataset.id, "provider": spec.provider, "key": spec.key()},
    )

    for c in result.candles:
        session.add(
            models.Candle(
                dataset_id=dataset.id,
                instrument=c.instrument,
                timeframe=c.timeframe.value,
                provider=spec.provider,
                broker_environment=spec.broker_environment,
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

    gaps = detect_gaps(result.candles, timeframe)
    for gap in gaps:
        session.add(
            models.DataGap(
                dataset_id=dataset.id,
                gap_start=gap.gap_start,
                gap_end=gap.gap_end,
                missing_bars=gap.missing_bars,
                reason=gap.reason,
                created_at=_now(),
            )
        )
        await _audit(
            session,
            AuditEventType.GAP_DETECTION,
            {
                "dataset_id": dataset.id,
                "gap_start": gap.gap_start.isoformat(),
                "gap_end": gap.gap_end.isoformat(),
                "missing_bars": gap.missing_bars,
                "reason": gap.reason,
            },
        )

    await _audit(
        session,
        AuditEventType.DATA_INGESTION,
        {"dataset_id": dataset.id, "candles": len(result.candles), "gaps": len(gaps)},
    )

    return IngestionReport(
        dataset_id=dataset.id,
        provider=spec.provider,
        instrument=instrument,
        timeframe=timeframe.value,
        candle_count=len(result.candles),
        gap_count=len(gaps),
        used_failover=result.used_failover,
        source_class=spec.source_class.value,
    )


async def load_candles_for_dataset(
    session: AsyncSession, dataset_id: int
) -> list[models.Candle]:
    """Load all candles for a dataset, ordered chronologically."""
    rows = await session.execute(
        select(models.Candle)
        .where(models.Candle.dataset_id == dataset_id)
        .order_by(models.Candle.timestamp)
    )
    return list(rows.scalars().all())
