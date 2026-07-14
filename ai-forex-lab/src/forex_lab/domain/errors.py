"""Domain-level exceptions.

These are raised by the deterministic core. They must be exceptions, not
warnings, so that violations (e.g. look-ahead access) fail loudly and are
caught by tests.
"""

from __future__ import annotations


class ForexLabError(Exception):
    """Base class for all domain errors."""


class LookAheadError(ForexLabError):
    """Raised when code attempts to read candle data from the future.

    A strategy or indicator operating at bar index ``t`` may only access bars
    ``0..t``. Any attempt to read ``t + 1`` or later raises this error.
    """


class InsufficientDataError(ForexLabError):
    """Raised when there is not enough data (e.g. indicator warmup not met)."""


class RiskRejectionError(ForexLabError):
    """Raised when a trade is rejected by the risk engine in a strict path."""


class ConfigurationError(ForexLabError):
    """Raised for invalid or inconsistent configuration."""


class ProviderError(ForexLabError):
    """Base class for market-data provider failures."""


class ProviderUnavailableError(ProviderError):
    """Raised when a provider is unreachable or unhealthy."""


class SymbolNotFoundError(ProviderError):
    """Raised when a provider cannot map a normalized instrument to a symbol."""
