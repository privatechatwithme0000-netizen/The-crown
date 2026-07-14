"""initial schema

Creates the full Phase 1 schema from the SQLAlchemy metadata. Building the
first revision from metadata keeps the migration and the ORM models in exact
agreement, so the schema applies deterministically from an empty database.

Revision ID: 0001_initial
Revises:
Create Date: 2026-07-14
"""

from __future__ import annotations

from alembic import op

from forex_lab.db.base import Base

# Importing models registers every table on Base.metadata.
from forex_lab.db import models  # noqa: F401

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
