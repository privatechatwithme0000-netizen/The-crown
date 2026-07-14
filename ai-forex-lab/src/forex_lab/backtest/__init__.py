"""Event-driven backtesting: config, engine, splits."""

from .config import BacktestConfig, IntrabarTieBreak
from .engine import Backtester, BacktestOutcome
from .splits import Split, WalkForwardWindow, chronological_split, walk_forward_windows

__all__ = [
    "BacktestConfig",
    "BacktestOutcome",
    "Backtester",
    "IntrabarTieBreak",
    "Split",
    "WalkForwardWindow",
    "chronological_split",
    "walk_forward_windows",
]
