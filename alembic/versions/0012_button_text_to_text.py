"""button_settings.text → TEXT (allow long button bodies)

Widens ``button_settings.text`` from VARCHAR(128) to TEXT so admins can store
long, multi-line button bodies (e.g. the «راه‌های ارتباطی» contact card). The
old VARCHAR(128) overflowed and raised MySQL error 1406 «Data too long».

Revision ID: 0012_button_text_to_text
Revises: 0011_admins
Create Date: 2026-06-10
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0012_button_text_to_text"
down_revision: Union[str, None] = "0011_admins"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "button_settings",
        "text",
        existing_type=sa.String(128),
        type_=sa.Text(),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "button_settings",
        "text",
        existing_type=sa.Text(),
        type_=sa.String(128),
        existing_nullable=True,
    )
