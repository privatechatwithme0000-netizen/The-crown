"""Pytest configuration and shared fixtures."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# Ensure the src layout is importable without installation.
SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

FIXTURES = Path(__file__).resolve().parent / "fixtures"
if str(FIXTURES.parent) not in sys.path:
    sys.path.insert(0, str(FIXTURES.parent))


def _database_available() -> bool:
    return os.environ.get("FOREX_LAB_TEST_DB", "").lower() in {"1", "true", "yes"}


requires_db = pytest.mark.skipif(
    not _database_available(),
    reason="integration DB not configured (set FOREX_LAB_TEST_DB=1 with Postgres up)",
)
