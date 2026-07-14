"""SQLAlchemy declarative base and shared column types.

Uses the SQLAlchemy 2.0 typed ORM. Money columns are ``NUMERIC``; timestamps
are ``TIMESTAMPTZ`` stored in UTC; config snapshots use ``JSONB``.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated

from sqlalchemy import BigInteger, DateTime, Numeric
from sqlalchemy.orm import DeclarativeBase, mapped_column, registry


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""

    registry = registry()


# Reusable annotated column types.
timestamptz = Annotated[datetime, mapped_column(DateTime(timezone=True))]
money = Annotated[Decimal, mapped_column(Numeric(28, 10))]
price = Annotated[Decimal, mapped_column(Numeric(20, 10))]
bigint_pk = Annotated[int, mapped_column(BigInteger, primary_key=True, autoincrement=True)]
