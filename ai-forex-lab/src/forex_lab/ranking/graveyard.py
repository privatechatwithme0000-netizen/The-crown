"""Strategy Graveyard helper.

Rejected or retired strategies are recorded, never deleted, so the same failed
idea is not recreated repeatedly. This module builds the persistence payload;
the API/service layer performs the actual insert.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any


@dataclass(frozen=True, slots=True)
class GraveyardEntry:
    strategy_key: str
    semver: str
    parameters: dict[str, Any]
    source_hash: str
    dataset_id: int | None
    backtest_start: datetime | None
    backtest_end: datetime | None
    metrics: dict[str, Any]
    max_drawdown: Decimal | None
    max_consecutive_losses: int | None
    failure_reason: str
    eligibility_failures: list[str]
    notes: str = ""


def build_graveyard_entry(
    *,
    strategy_key: str,
    semver: str,
    parameters: dict[str, Any],
    source_hash: str,
    metrics: dict[str, Any],
    failure_reason: str,
    eligibility_failures: list[str],
    dataset_id: int | None = None,
    backtest_start: datetime | None = None,
    backtest_end: datetime | None = None,
    notes: str = "",
) -> GraveyardEntry:
    max_dd = metrics.get("max_drawdown")
    max_cons = metrics.get("max_consecutive_losses")
    return GraveyardEntry(
        strategy_key=strategy_key,
        semver=semver,
        parameters=parameters,
        source_hash=source_hash,
        dataset_id=dataset_id,
        backtest_start=backtest_start,
        backtest_end=backtest_end,
        metrics=metrics,
        max_drawdown=None if max_dd is None else Decimal(str(max_dd)),
        max_consecutive_losses=None if max_cons is None else int(max_cons),
        failure_reason=failure_reason,
        eligibility_failures=eligibility_failures,
        notes=notes,
    )
