"""Provider registry with explicit failover.

Failover is explicit and always produces a *separate* dataset. Candles from
different providers are never merged. When the primary fails and a fallback is
used, the resulting dataset spec is flagged SECONDARY/DEGRADED so provenance
records the substitution.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from forex_lab.domain.candle import Candle
from forex_lab.domain.enums import (
    DatasetSourceClass,
    PriceComponent,
    Timeframe,
)
from forex_lab.domain.errors import ProviderUnavailableError
from forex_lab.marketdata.dataset import DatasetSpec

from .base import MarketDataProvider


@dataclass(frozen=True, slots=True)
class FetchResult:
    """Candles plus the dataset spec they must be pinned to."""

    provider_name: str
    spec: DatasetSpec
    candles: list[Candle]
    used_failover: bool


class ProviderRegistry:
    """Holds an ordered list of providers and performs explicit failover."""

    def __init__(self, providers: list[MarketDataProvider]) -> None:
        if not providers:
            raise ValueError("at least one provider is required")
        self._providers = providers

    @property
    def primary(self) -> MarketDataProvider:
        return self._providers[0]

    def get(self, name: str) -> MarketDataProvider:
        for p in self._providers:
            if p.name == name:
                return p
        raise KeyError(f"no provider named {name!r}")

    def names(self) -> list[str]:
        return [p.name for p in self._providers]

    def fetch_candles(
        self,
        instrument: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
        price_component: PriceComponent = PriceComponent.BID_ASK,
    ) -> FetchResult:
        """Fetch from the primary; on failure, fall back to the next provider.

        The returned :class:`FetchResult` is pinned to exactly one provider.
        """
        errors: list[str] = []
        for index, provider in enumerate(self._providers):
            try:
                candles = provider.get_candles(
                    instrument, timeframe, start, end, price_component
                )
            except Exception as exc:  # noqa: BLE001 - any provider failure -> failover
                errors.append(f"{provider.name}: {exc}")
                continue
            used_failover = index > 0
            source_class = (
                DatasetSourceClass.SECONDARY if used_failover else DatasetSourceClass.PRIMARY
            )
            spec = DatasetSpec(
                provider=provider.name,
                broker_environment=provider.broker_environment.value,
                instrument=instrument,
                timeframe=timeframe,
                price_component=price_component,
                start_time=start,
                end_time=end,
                source_class=source_class,
                provenance={
                    "used_failover": used_failover,
                    "failover_chain": self.names(),
                    "errors": errors,
                },
            )
            return FetchResult(
                provider_name=provider.name,
                spec=spec,
                candles=candles,
                used_failover=used_failover,
            )
        raise ProviderUnavailableError("all providers failed: " + "; ".join(errors))

    def health(self) -> dict[str, bool]:
        return {p.name: p.health().healthy for p in self._providers}
