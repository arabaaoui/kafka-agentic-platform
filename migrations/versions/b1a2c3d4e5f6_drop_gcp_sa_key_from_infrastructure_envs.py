"""drop gcp_sa_key from infrastructure_envs (align with spec-007 impersonation-only)

Revision ID: b1a2c3d4e5f6
Revises: 57f19c05fb6a
Create Date: 2026-05-18 00:00:00.000000

Spec 007 mandates GSA impersonation via GCPTokenProvider (target_gsa_email) for
production and ADC (gcloud auth application-default login) for local dev.
Static JSON keys in DB are explicitly prohibited by spec 007.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b1a2c3d4e5f6'
down_revision: Union[str, None] = '1e9f1701d1a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column('infrastructure_envs', 'gcp_sa_key')


def downgrade() -> None:
    op.add_column(
        'infrastructure_envs',
        sa.Column('gcp_sa_key', sa.Text(), nullable=False, server_default=''),
    )
