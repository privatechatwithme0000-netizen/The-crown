"""CSV market-data provider for deterministic testing and offline backtests.

Reads candles from a CSV with an explicit bid/ask schema. Used for
reproducibility tests and synthetic datasets. Synthetic data produced here must
be clearly marked as such by the caller (source class / provenance).

Expected CSV columns (header required):
    timestamp,bid_open,bid_high,bid_low,bid_close,
    ask_open,ask_high,ask_low,ask_close,tick_volume[,complete]

``timestamp`` is ISO-8601 UTC.
"""

from __future__ import annotations

import csv
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from forex_lab.domain.candle import Candle
from forex_lab.domain.enums import BrokerEnvironment, PriceComponent, Timeframe

from .base import LatestPrice, ProviderHealth, RateLimitStatus


class CsvProvider:
    """Deterministic provider backed by a CSV file per (instrument, timeframe)."""

    def __init__(
        self,
        candles_by_instrument: dict[str, list[Candle]],
        *,
        name: str = "csv",
        timeframe: Timeframe = Timeframe.M15,
    ) -> None:
        self._data = candles_by_instrument
        self._name = name
        self._timeframe = timeframe

    # --- construction -------------------------------------------------------
    @classmethod
    def from_file(
        cls,
        path: str | Path,
        instrument: str,
        timeframe: Timeframe,
        *,
        name: str = "csv",
    ) -> CsvProvider:
        candles = cls._read_csv(Path(path), instrument, timeframe)
        return cls({instrument: candles}, name=name, timeframe=timeframe)

    @staticmethod
    def _read_csv(path: Path, instrument: str, timeframe: Timeframe) -> list[Candle]:
        rows: list[Candle] = []
        with path.open(newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                ts = datetime.fromisoformat(row["timestamp"])
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=UTC)
                complete = row.get("complete", "true").strip().lower() != "false"
                rows.append(
                    Candle.from_bid_ask(
                        timestamp=ts,
                        instrument=instrument,
                        timeframe=timeframe,
                        bid_ohlc=(
                            row["bid_open"],
                            row["bid_high"],
                            row["bid_low"],
                            row["bid_close"],
                        ),
                        ask_ohlc=(
                            row["ask_open"],
                            row["ask_high"],
                            row["ask_low"],
                            row["ask_close"],
                        ),
                        tick_volume=int(row.get("tick_volume", "0") or 0),
                        complete=complete,
                    )
                )
        rows.sort(key=lambda c: c.timestamp)
        return rows

    # --- provider protocol --------------------------------------------------
    @property
    def name(self) -> str:
        return self._name

    @property
    def broker_environment(self) -> BrokerEnvironment:
        return BrokerEnvironment.SYNTHETIC

    @property
    def supported_instruments(self) -> frozenset[str]:
        return frozenset(self._data.keys())

    @property
    def supported_timeframes(self) -> frozenset[Timeframe]:
        return frozenset({self._timeframe})

    def get_candles(
        self,
        instrument: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
        price_component: PriceComponent = PriceComponent.BID_ASK,
    ) -> list[Candle]:
        candles = self._data.get(instrument, [])
        return [c for c in candles if start <= c.timestamp <= end and c.complete]

    def get_latest_price(self, instrument: str) -> LatestPrice:
        candles = self._data.get(instrument, [])
        if not candles:
            raise LookupError(f"no data for {instrument}")
        last = candles[-1]
        return LatestPrice(
            instrument=instrument,
            timestamp=last.timestamp,
            bid=last.bid_close,
            ask=last.ask_close,
        )

    def health(self) -> ProviderHealth:
        return ProviderHealth(name=self._name, healthy=True, detail="in-memory")

    def rate_limit_status(self) -> RateLimitStatus:
        return RateLimitStatus(limit=None, remaining=None, reset_epoch=None)

    @staticmethod
    def _d(value: str) -> Decimal:  # pragma: no cover - convenience
        return Decimal(value)
