"""drop_account_stat_columns — remove per-stat fields now folded into description

Drops the structured stat columns from ``accounts`` and ``requested_accounts``.
All specs (level, elite count, skins, guns, special items, sets, …) are now
written as free text in the ``description`` field, so the dedicated columns are
obsolete. ``account_sale_requests`` is intentionally left untouched.

Revision ID: 0008_drop_account_stat_columns
Revises: 0007_button_settings
Create Date: 2026-06-07
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008_drop_account_stat_columns"
down_revision: Union[str, None] = "0007_button_settings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # accounts: level / skins_count / elite_count / gun_skins_count / special_items
    op.drop_column("accounts", "level")
    op.drop_column("accounts", "skins_count")
    op.drop_column("accounts", "elite_count")
    op.drop_column("accounts", "gun_skins_count")
    op.drop_column("accounts", "special_items")
    # requested_accounts: elite_count / sets / guns
    op.drop_column("requested_accounts", "elite_count")
    op.drop_column("requested_accounts", "sets")
    op.drop_column("requested_accounts", "guns")


def downgrade() -> None:
    op.add_column(
        "requested_accounts", sa.Column("guns", sa.Text(), nullable=True)
    )
    op.add_column(
        "requested_accounts", sa.Column("sets", sa.Text(), nullable=True)
    )
    op.add_column(
        "requested_accounts",
        sa.Column("elite_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "accounts", sa.Column("special_items", sa.Text(), nullable=True)
    )
    op.add_column(
        "accounts",
        sa.Column("gun_skins_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "accounts",
        sa.Column("elite_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "accounts",
        sa.Column("skins_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "accounts",
        sa.Column("level", sa.Integer(), nullable=False, server_default="0"),
    )
