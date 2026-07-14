"""Execution adapter interface.

An execution adapter mirrors the deterministic broker's decisions to an external
venue. Phase 2 ships an internal no-op adapter and an OANDA *practice* adapter.
The deterministic accounting always runs locally regardless of adapter, so
results stay reproducible; the adapter only forwards orders to a practice venue.

Real-money execution is never provided by any Phase 2 adapter.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol, runtime_checkable

from forex_lab.domain.enums import ExecutionMode, Side


@dataclass(frozen=True, slots=True)
class ExecutionAck:
    accepted: bool
    order_id: str
    status: str
    detail: dict[str, str]


@runtime_checkable
class ExecutionAdapter(Protocol):
    @property
    def mode(self) -> ExecutionMode: ...

    def submit_market_order(
        self,
        instrument: str,
        side: Side,
        units: Decimal,
        *,
        stop_loss: Decimal | None = None,
        take_profit: Decimal | None = None,
    ) -> ExecutionAck: ...


class NullExecutor:
    """No-op adapter for internal paper sessions (no external side effects)."""

    @property
    def mode(self) -> ExecutionMode:
        return ExecutionMode.INTERNAL_PAPER

    def submit_market_order(
        self,
        instrument: str,
        side: Side,
        units: Decimal,
        *,
        stop_loss: Decimal | None = None,
        take_profit: Decimal | None = None,
    ) -> ExecutionAck:
        return ExecutionAck(
            accepted=True,
            order_id="internal",
            status="SIMULATED",
            detail={"instrument": instrument, "side": side.value, "units": str(units)},
        )
