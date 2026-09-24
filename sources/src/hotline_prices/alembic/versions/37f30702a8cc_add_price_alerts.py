"""add_price_alerts

Revision ID: 37f30702a8cc
Revises: 6bf7338d4492
Create Date: 2026-09-24 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "37f30702a8cc"
down_revision: str | None = "6bf7338d4492"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "configs",
        sa.Column("owner_discord_email", sa.String(), nullable=True),
    )
    op.add_column(
        "configs",
        sa.Column(
            "alert_state",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("configs", "alert_state")
    op.drop_column("configs", "owner_discord_email")
