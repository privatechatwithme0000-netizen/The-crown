"""Decimal money/price helpers.

All cash, price, quantity, fee, P&L, margin, financing, and spread values use
``Decimal``. Binary floating point is only permitted inside statistical
calculations after an explicit conversion (see :func:`to_float`).
"""

from __future__ import annotations

from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal, InvalidOperation

# Common quantization exponents.
PRICE_Q = Decimal("0.00001")  # 5 dp covers pipettes for non-JPY pairs
MONEY_Q = Decimal("0.01")


def dec(value: str | int | float | Decimal) -> Decimal:
    """Construct a Decimal safely from mixed input.

    Floats are routed through ``str`` to avoid binary artifacts. This is the
    only sanctioned float -> Decimal path and is used for parsing provider
    payloads (which arrive as JSON numbers).
    """
    if isinstance(value, Decimal):
        return value
    if isinstance(value, float):
        return Decimal(str(value))
    try:
        return Decimal(value)
    except InvalidOperation as exc:  # pragma: no cover - defensive
        raise ValueError(f"cannot convert {value!r} to Decimal") from exc


def to_float(value: Decimal) -> float:
    """Explicit Decimal -> float conversion for statistics (Sharpe, etc.)."""
    return float(value)


def quantize_price(value: Decimal, tick: Decimal) -> Decimal:
    """Quantize a price to a tick size, rounding half up."""
    return value.quantize(tick, rounding=ROUND_HALF_UP)


def quantize_money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_Q, rounding=ROUND_HALF_UP)


def floor_to_step(quantity: Decimal, step: Decimal) -> Decimal:
    """Round a quantity DOWN to the nearest valid broker step.

    Rounding down never increases risk beyond the configured budget.
    """
    if step <= 0:
        raise ValueError("quantity step must be positive")
    steps = (quantity / step).to_integral_value(rounding=ROUND_DOWN)
    return (steps * step).quantize(step)
