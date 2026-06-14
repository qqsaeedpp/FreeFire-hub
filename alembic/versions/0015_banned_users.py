"""banned_users — audit trail behind the users.is_banned fast-path flag

Adds the ``banned_users`` table backing «🚫 مدیریت کاربران». Each ban writes a row
(``user_id`` / ``reason`` / ``banned_by`` / ``banned_at``) while the gate keeps
reading the cheap ``users.is_banned`` boolean; ``is_active`` flips to ``False`` on
unban so history is preserved. Plain ``CREATE TABLE`` works on both MySQL (prod)
and SQLite (tests).

Revision ID: 0015_banned_users
Revises: 0014_user_pending_referral
Create Date: 2026-06-14
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0015_banned_users"
down_revision: Union[str, None] = "0014_user_pending_referral"
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
        "banned_users",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("reason", sa.String(255), nullable=True),
        sa.Column("banned_by", sa.BigInteger(), nullable=True),
        sa.Column("banned_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("unbanned_at", sa.DateTime(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        *_ts(),
    )
    op.create_index("ix_banned_users_user_id", "banned_users", ["user_id"])
    op.create_index("ix_banned_users_is_active", "banned_users", ["is_active"])


def downgrade() -> None:
    op.drop_index("ix_banned_users_is_active", table_name="banned_users")
    op.drop_index("ix_banned_users_user_id", table_name="banned_users")
    op.drop_table("banned_users")
