"""Add brief_path and finalized_at to audits table (post-mortem v0.5).

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-11
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("audits", sa.Column("brief_path", sa.Text(), nullable=True))
    op.add_column(
        "audits",
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("audits", "finalized_at")
    op.drop_column("audits", "brief_path")
