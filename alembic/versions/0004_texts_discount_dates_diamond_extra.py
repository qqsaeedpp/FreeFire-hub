"""bot_texts, discount start date, diamond extra credentials, DELETED account status

Revision ID: 0004_texts_extra
Revises: 0003_cards_discounts
Create Date: 2026-06-06
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.core.constants import AccountStatus

revision: str = "0004_texts_extra"
down_revision: Union[str, None] = "0003_cards_discounts"
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


# accountstatus before/after this migration (widen to add DELETED).
_OLD_ACCOUNT_STATUS = sa.Enum(
    "PENDING_REVIEW", "AVAILABLE", "LISTED_FOR_SALE", "RESERVED", "SOLD",
    "SOLD_TO_ADMIN", "HIDDEN",
    name="accountstatus",
)
_NEW_ACCOUNT_STATUS = sa.Enum(AccountStatus, name="accountstatus")


def upgrade() -> None:
    # 1) widen accountstatus to include DELETED (soft delete).
    op.alter_column(
        "accounts",
        "status",
        existing_type=_OLD_ACCOUNT_STATUS,
        type_=_NEW_ACCOUNT_STATUS,
        existing_nullable=False,
    )

    # 2) discount_codes.starts_at — optional activation date.
    op.add_column(
        "discount_codes",
        sa.Column("starts_at", sa.DateTime(), nullable=True),
    )

    # 3) diamond_orders — extra (encrypted) account credentials.
    op.add_column("diamond_orders", sa.Column("gmail", sa.String(255), nullable=True))
    op.add_column("diamond_orders", sa.Column("gmail_password", sa.String(255), nullable=True))
    op.add_column("diamond_orders", sa.Column("gmail_backup_code", sa.String(255), nullable=True))
    op.add_column("diamond_orders", sa.Column("account_backup_code", sa.String(255), nullable=True))

    # 4) bot_texts — admin-editable user-facing texts (+ premium-emoji entities).
    op.create_table(
        "bot_texts",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("key", sa.String(64), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("entities_json", sa.Text(), nullable=True),
        *_ts(),
        sa.UniqueConstraint("key", name="uq_bot_texts_key"),
    )
    op.create_index("ix_bot_texts_key", "bot_texts", ["key"])


def downgrade() -> None:
    op.drop_index("ix_bot_texts_key", table_name="bot_texts")
    op.drop_table("bot_texts")
    op.drop_column("diamond_orders", "account_backup_code")
    op.drop_column("diamond_orders", "gmail_backup_code")
    op.drop_column("diamond_orders", "gmail_password")
    op.drop_column("diamond_orders", "gmail")
    op.drop_column("discount_codes", "starts_at")
    op.alter_column(
        "accounts",
        "status",
        existing_type=_NEW_ACCOUNT_STATUS,
        type_=_OLD_ACCOUNT_STATUS,
        existing_nullable=False,
    )
