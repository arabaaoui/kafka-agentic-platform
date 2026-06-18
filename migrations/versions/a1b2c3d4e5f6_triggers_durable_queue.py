"""triggers_durable_queue

Add claimed_at, claimed_by, attempts, last_error columns to triggers table
and a partial index for efficient pending-trigger queries.

Revision ID: a1b2c3d4e5f6
Revises: ba677a1f0fab
Create Date: 2026-06-12 00:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "ba677a1f0fab"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("triggers", sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("triggers", sa.Column("claimed_by", sa.String(), nullable=True))
    op.add_column("triggers", sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("triggers", sa.Column("last_error", sa.Text(), nullable=True))

    op.execute(
        """
        CREATE INDEX idx_triggers_pending ON triggers (received_at)
        WHERE matched = true AND processed_at IS NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_triggers_pending")
    op.drop_column("triggers", "last_error")
    op.drop_column("triggers", "attempts")
    op.drop_column("triggers", "claimed_by")
    op.drop_column("triggers", "claimed_at")
