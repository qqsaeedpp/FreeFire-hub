"""users.pending_referral_code — hold a deep-link referral code across the gate

Adds a nullable ``pending_referral_code`` column to ``users``. A forced-join
channel lock can intercept the very first ``/start <code>`` (consuming the
deep-link payload) before the referral handler runs; persisting the code lets
the referral reward fire once the new user finally passes the gate. Plain
``ADD COLUMN`` works on both MySQL (prod) and SQLite (tests).

Revision ID: 0014_user_pending_referral
Revises: 0013_account_status_rejected
Create Date: 2026-06-11
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0014_user_pending_referral"
down_revision: Union[str, None] = "0013_account_status_rejected"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("pending_referral_code", sa.String(64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "pending_referral_code")
