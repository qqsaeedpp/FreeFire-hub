"""tutorial_media — admin-managed tutorial videos (file_id store)

Revision ID: 0006_tutorial_media
Revises: 0005_requested_receipt
Create Date: 2026-06-07
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006_tutorial_media"
down_revision: Union[str, None] = "0005_requested_receipt"
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
        "tutorial_media",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("key", sa.String(64), nullable=False),
        sa.Column("file_id", sa.String(255), nullable=True),
        sa.Column("caption", sa.Text(), nullable=True),
        *_ts(),
        sa.UniqueConstraint("key", name="uq_tutorial_media_key"),
    )
    op.create_index("ix_tutorial_media_key", "tutorial_media", ["key"])


def downgrade() -> None:
    op.drop_index("ix_tutorial_media_key", table_name="tutorial_media")
    op.drop_table("tutorial_media")
