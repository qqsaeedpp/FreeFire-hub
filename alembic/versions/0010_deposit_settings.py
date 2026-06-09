"""deposit_settings — admin-managed deposit (بیعانه) amounts + cards

Adds the ``deposit_settings`` table so the deposit amount and destination card
for each flow (requested account / account purchase) are configurable from the
admin panel instead of being hardcoded.

Revision ID: 0010_deposit_settings
Revises: 0009_locked_channels
Create Date: 2026-06-09
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.core.constants import DepositType

revision: str = "0010_deposit_settings"
down_revision: Union[str, None] = "0009_locked_channels"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _ts():
    return (
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )


def upgrade() -> None:
    op.create_table(
        "deposit_settings",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("deposit_type", sa.Enum(DepositType), nullable=False),
        sa.Column("amount", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("card_number", sa.String(32), nullable=False, server_default=""),
        sa.Column("card_holder", sa.String(128), nullable=False, server_default=""),
        *_ts(),
        sa.UniqueConstraint("deposit_type", name="uq_deposit_settings_type"),
    )
    op.create_index(
        "ix_deposit_settings_deposit_type", "deposit_settings", ["deposit_type"]
    )


def downgrade() -> None:
    op.drop_index(
        "ix_deposit_settings_deposit_type", table_name="deposit_settings"
    )
    op.drop_table("deposit_settings")
