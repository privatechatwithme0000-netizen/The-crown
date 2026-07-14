"""Chronological data splits and walk-forward windows.

Time-series data is never shuffled. Train/validation/out-of-sample sets are
contiguous and non-overlapping. Walk-forward windows train only on earlier data
and test only on later, unseen data, advancing chronologically.
"""

from __future__ import annotations

from dataclasses import dataclass

from forex_lab.domain.candle import Candle


@dataclass(frozen=True, slots=True)
class Split:
    kind: str  # TRAIN / VALIDATION / OOS
    candles: list[Candle]

    @property
    def start(self) -> Candle:
        return self.candles[0]

    @property
    def end(self) -> Candle:
        return self.candles[-1]


@dataclass(frozen=True, slots=True)
class WalkForwardWindow:
    index: int
    train: list[Candle]
    test: list[Candle]


def chronological_split(
    candles: list[Candle],
    train_frac: float = 0.6,
    validation_frac: float = 0.2,
) -> dict[str, Split]:
    """Split candles into contiguous train/validation/out-of-sample sets."""
    if not candles:
        raise ValueError("no candles to split")
    if train_frac <= 0 or validation_frac < 0 or train_frac + validation_frac >= 1:
        raise ValueError("invalid split fractions")
    ordered = sorted(candles, key=lambda c: c.timestamp)
    n = len(ordered)
    train_end = int(n * train_frac)
    val_end = int(n * (train_frac + validation_frac))
    train = ordered[:train_end]
    validation = ordered[train_end:val_end]
    oos = ordered[val_end:]
    result: dict[str, Split] = {}
    if train:
        result["TRAIN"] = Split("TRAIN", train)
    if validation:
        result["VALIDATION"] = Split("VALIDATION", validation)
    if oos:
        result["OOS"] = Split("OOS", oos)
    return result


def walk_forward_windows(
    candles: list[Candle],
    train_size: int,
    test_size: int,
    step: int | None = None,
) -> list[WalkForwardWindow]:
    """Generate non-overlapping-test walk-forward windows.

    Each window trains on ``train_size`` bars and tests on the immediately
    following ``test_size`` bars. Windows advance by ``step`` (default
    ``test_size``) so test segments do not overlap.
    """
    if train_size <= 0 or test_size <= 0:
        raise ValueError("train_size and test_size must be positive")
    step = step or test_size
    if step <= 0:
        raise ValueError("step must be positive")
    ordered = sorted(candles, key=lambda c: c.timestamp)
    windows: list[WalkForwardWindow] = []
    start = 0
    index = 0
    n = len(ordered)
    while start + train_size + test_size <= n:
        train = ordered[start : start + train_size]
        test = ordered[start + train_size : start + train_size + test_size]
        # Guarantee chronology: train strictly precedes test.
        assert train[-1].timestamp < test[0].timestamp
        windows.append(WalkForwardWindow(index=index, train=train, test=test))
        start += step
        index += 1
    return windows
