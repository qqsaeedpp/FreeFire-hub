"""requested_accounts.deposit_receipt_file_id

Revision ID: 0005_requested_receipt
Revises: 0004_texts_extra
Create Date: 2026-06-07
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005_requested_receipt"
down_revision: Union[str, None] = "0004_texts_extra"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "requested_accounts",
        sa.Column("deposit_receipt_file_id", sa.String(255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("requested_accounts", "deposit_receipt_file_id")
