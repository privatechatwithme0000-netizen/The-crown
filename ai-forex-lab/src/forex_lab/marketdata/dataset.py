"""Dataset provenance and pinning.

A dataset is permanently pinned to a single provider, broker environment,
instrument, timeframe, price component, and time range. Candles from different
providers are never merged into one dataset. A deterministic dataset key makes
provenance auditable.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from forex_lab.domain.enums import DatasetSourceClass, PriceComponent, Timeframe


@dataclass(frozen=True, slots=True)
class DatasetSpec:
    """The immutable identity of a dataset."""

    provider: str
    broker_environment: str
    instrument: str
    timeframe: Timeframe
    price_component: PriceComponent
    start_time: datetime
    end_time: datetime
    source_class: DatasetSourceClass = DatasetSourceClass.PRIMARY
    provenance: dict[str, Any] = field(default_factory=dict)

    def key(self) -> str:
        """Stable content hash of the pinning tuple."""
        raw = "|".join(
            [
                self.provider,
                self.broker_environment,
                self.instrument,
                self.timeframe.value,
                self.price_component.value,
                self.start_time.isoformat(),
                self.end_time.isoformat(),
                self.source_class.value,
            ]
        )
        return hashlib.sha256(raw.encode()).hexdigest()[:32]

    def is_compatible_with(self, other: DatasetSpec) -> bool:
        """Two specs may share a dataset only if provider/env/instrument/tf match."""
        return (
            self.provider == other.provider
            and self.broker_environment == other.broker_environment
            and self.instrument == other.instrument
            and self.timeframe == other.timeframe
            and self.price_component == other.price_component
        )
