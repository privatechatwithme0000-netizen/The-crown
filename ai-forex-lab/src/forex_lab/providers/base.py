"""Normalized market-data provider interface.

All providers expose the same surface so the core never depends on a specific
broker. Provider-specific translation (symbols, payload shapes) is confined to
the adapter implementations in this package.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol, runtime_checkable

from forex_lab.domain.candle import Candle
from forex_lab.domain.enums import BrokerEnvironment, PriceComponent, Timeframe


@dataclass(frozen=True, slots=True)
class LatestPrice:
    instrument: str
    timestamp: datetime
    bid: Decimal
    ask: Decimal

    @property
    def spread(self) -> Decimal:
        return self.ask - self.bid


@dataclass(frozen=True, slots=True)
class ProviderHealth:
    name: str
    healthy: bool
    detail: str = ""


@dataclass(frozen=True, slots=True)
class RateLimitStatus:
    limit: int | None
    remaining: int | None
    reset_epoch: int | None


@runtime_checkable
class MarketDataProvider(Protocol):
    """The contract every provider adapter satisfies."""

    @property
    def name(self) -> str: ...

    @property
    def broker_environment(self) -> BrokerEnvironment: ...

    @property
    def supported_instruments(self) -> frozenset[str]: ...

    @property
    def supported_timeframes(self) -> frozenset[Timeframe]: ...

    def get_candles(
        self,
        instrument: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
        price_component: PriceComponent = PriceComponent.BID_ASK,
    ) -> list[Candle]: ...

    def get_latest_price(self, instrument: str) -> LatestPrice: ...

    def health(self) -> ProviderHealth: ...

    def rate_limit_status(self) -> RateLimitStatus: ...
