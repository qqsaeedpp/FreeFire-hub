"""app_settings — durable store for admin-editable settings

Creates the ``app_settings`` key/value table that becomes the single source of
truth for settings an admin edits from the panel (referral reward, diamond plan
prices, level-up bundle price). These previously lived only in Redis and reverted
to hardcoded/env defaults on any Redis data loss or key bump; persisting them in
MySQL stops the automatic reverts and lets them ride along in DB backups.

The app's one-time startup import then copies any current Redis values into this
table (create-if-absent only), so existing admin prices survive the upgrade.

Revision ID: 0020_app_settings
Revises: 0019_account_text_entities
Create Date: 2026-06-25
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0020_app_settings"
down_revision: Union[str, None] = "0019_account_text_entities"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "app_settings",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("key", sa.String(64), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("updated_by", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_app_settings_key", "app_settings", ["key"], unique=True
    )


def downgrade() -> None:
    op.drop_index("ix_app_settings_key", table_name="app_settings")
    op.drop_table("app_settings")
