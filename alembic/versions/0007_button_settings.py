"""button_settings — admin-editable main button text/emoji & appearance

Revision ID: 0007_button_settings
Revises: 0006_tutorial_media
Create Date: 2026-06-07
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007_button_settings"
down_revision: Union[str, None] = "0006_tutorial_media"
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
        "button_settings",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("key", sa.String(64), nullable=False),
        sa.Column("text", sa.String(128), nullable=True),
        sa.Column("emoji", sa.String(32), nullable=True),
        sa.Column("button_type", sa.String(16), nullable=True),
        sa.Column(
            "is_enabled", sa.Boolean(), nullable=False, server_default="1"
        ),
        sa.Column("custom_emoji_id", sa.String(64), nullable=True),
        sa.Column("emoji_text", sa.String(32), nullable=True),
        *_ts(),
        sa.UniqueConstraint("key", name="uq_button_settings_key"),
    )
    op.create_index("ix_button_settings_key", "button_settings", ["key"])


def downgrade() -> None:
    op.drop_index("ix_button_settings_key", table_name="button_settings")
    op.drop_table("button_settings")
