"""add_config_owner

Revision ID: 6bf7338d4492
Revises: d413ff1678f4
Create Date: 2026-08-07 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "6bf7338d4492"
down_revision: str | None = "d413ff1678f4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "configs",
        sa.Column("owner_discord_user_id", sa.String(), nullable=True),
    )
    op.create_index(
        op.f("ix_configs_owner_discord_user_id"),
        "configs",
        ["owner_discord_user_id"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_configs_owner_discord_user_id"), table_name="configs")
    op.drop_column("configs", "owner_discord_user_id")
