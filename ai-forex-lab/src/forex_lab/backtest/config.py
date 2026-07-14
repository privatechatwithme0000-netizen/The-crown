"""Backtest configuration and deterministic config hashing.

The config hash covers every input that can change results, so
``(dataset_id, strategy_version_id, config_hash, seed)`` uniquely determines the
output.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any

from forex_lab.domain.enums import ExecutionMode, Timeframe
from forex_lab.domain.money import dec
from forex_lab.execution.costs import CommissionModel, FinancingModel, SlippageModel
from forex_lab.risk.config import RiskConfig
from forex_lab.risk.sizing import ConversionRates


class IntrabarTieBreak(str, Enum):
    """How to resolve a bar where both stop and target are touched."""

    CONSERVATIVE_STOP_FIRST = "CONSERVATIVE_STOP_FIRST"  # assume the worse outcome
    TARGET_FIRST = "TARGET_FIRST"


@dataclass(frozen=True, slots=True)
class BacktestConfig:
    instrument: str = "AUD_CAD"
    timeframe: Timeframe = Timeframe.M15
    account_currency: str = "USD"
    initial_cash: Decimal = dec("10000")
    seed: int = 12345
    execution_mode: ExecutionMode = ExecutionMode.BACKTEST
    tie_break: IntrabarTieBreak = IntrabarTieBreak.CONSERVATIVE_STOP_FIRST

    conversions: ConversionRates = field(default_factory=lambda: ConversionRates({}))
    slippage: SlippageModel = field(default_factory=SlippageModel)
    commission: CommissionModel = field(default_factory=CommissionModel)
    financing: FinancingModel = field(default_factory=FinancingModel)
    risk: RiskConfig = field(default_factory=RiskConfig)

    def snapshot(self) -> dict[str, Any]:
        """JSON-serializable snapshot of all result-affecting inputs."""
        return {
            "instrument": self.instrument,
            "timeframe": self.timeframe.value,
            "account_currency": self.account_currency,
            "initial_cash": str(self.initial_cash),
            "seed": self.seed,
            "execution_mode": self.execution_mode.value,
            "tie_break": self.tie_break.value,
            "conversions": {k: str(v) for k, v in sorted(self.conversions.rates.items())},
            "slippage": {
                "mode": self.slippage.mode.value,
                "pips": str(self.slippage.pips),
                "bps": str(self.slippage.bps),
                "atr_multiple": str(self.slippage.atr_multiple),
                "spread_multiple": str(self.slippage.spread_multiple),
            },
            "commission": {
                "mode": self.commission.mode.value,
                "per_unit": str(self.commission.per_unit),
                "per_million": str(self.commission.per_million),
                "fixed": str(self.commission.fixed),
            },
            "financing": {
                "mode": self.financing.mode.value,
                "daily_rate": str(self.financing.daily_rate),
                "rollover_hour_utc": self.financing.rollover_hour_utc,
            },
            "risk": self.risk.as_snapshot(),
        }

    def config_hash(self) -> str:
        raw = json.dumps(self.snapshot(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode()).hexdigest()[:32]
