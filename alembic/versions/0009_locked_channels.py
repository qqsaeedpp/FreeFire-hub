"""locked_channels — forced-membership (lock) channels

Adds the ``locked_channels`` table backing the admin-managed forced-join feature.

Revision ID: 0009_locked_channels
Revises: 0008_drop_account_stat_columns
Create Date: 2026-06-08
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009_locked_channels"
down_revision: Union[str, None] = "0008_drop_account_stat_columns"
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
        "locked_channels",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(255), nullable=True),
        sa.Column("invite_link", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        *_ts(),
        sa.UniqueConstraint("chat_id", name="uq_locked_channels_chat_id"),
    )
    op.create_index("ix_locked_channels_chat_id", "locked_channels", ["chat_id"])


def downgrade() -> None:
    op.drop_index("ix_locked_channels_chat_id", table_name="locked_channels")
    op.drop_table("locked_channels")
