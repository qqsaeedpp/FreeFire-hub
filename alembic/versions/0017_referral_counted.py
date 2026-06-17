"""referrals.counted — resettable invite stats without deleting any relation

Adds a boolean ``counted`` column to ``referrals`` (default ``1``). Every
referral-stats read (per-referrer count, rewarded sum, the referrers leaderboard,
the invitee list) now filters ``counted = 1`` so an admin can *reset* a single
user's — or everyone's — invite statistics by flipping the flag to ``0`` while
keeping every relation row intact. The double-reward guard reads rows regardless
of the flag (``get_by_referred`` + the unique ``referred_id`` constraint), so a
reset can never re-pay an already-counted invitee. Existing rows backfill to ``1``
via the server default, preserving current stats. Plain ``ADD COLUMN`` works on
both MySQL (prod) and SQLite (tests).

Revision ID: 0017_referral_counted
Revises: 0016_backup_settings
Create Date: 2026-06-17
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0017_referral_counted"
down_revision: Union[str, None] = "0016_backup_settings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "referrals",
        sa.Column("counted", sa.Boolean(), nullable=False, server_default="1"),
    )


def downgrade() -> None:
    op.drop_column("referrals", "counted")
