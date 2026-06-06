"""payment cards, discount codes, wallet payment + LISTED_FOR_SALE status

Revision ID: 0003_cards_discounts
Revises: 0002_payment_unified_account
Create Date: 2026-06-06
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.core.constants import AccountStatus, CardPurpose, PaymentMethod

revision: str = "0003_cards_discounts"
down_revision: Union[str, None] = "0002_payment_unified_account"
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


# accountstatus before/after this migration (for the ENUM widen/narrow).
_OLD_ACCOUNT_STATUS = sa.Enum(
    "PENDING_REVIEW", "AVAILABLE", "RESERVED", "SOLD", "SOLD_TO_ADMIN", "HIDDEN",
    name="accountstatus",
)
_NEW_ACCOUNT_STATUS = sa.Enum(AccountStatus, name="accountstatus")

# paymentmethod before/after (WALLET added).
_OLD_PAYMENT_METHOD = sa.Enum("ONLINE", "CARD_TO_CARD", name="paymentmethod")
_NEW_PAYMENT_METHOD = sa.Enum(PaymentMethod, name="paymentmethod")


def upgrade() -> None:
    # 1) widen accountstatus to include LISTED_FOR_SALE.
    op.alter_column(
        "accounts",
        "status",
        existing_type=_OLD_ACCOUNT_STATUS,
        type_=_NEW_ACCOUNT_STATUS,
        existing_nullable=False,
    )

    # 2) widen orders.payment_method to include WALLET.
    op.alter_column(
        "orders",
        "payment_method",
        existing_type=_OLD_PAYMENT_METHOD,
        type_=_NEW_PAYMENT_METHOD,
        existing_nullable=True,
    )

    # 3) payment_cards — one card per sales channel.
    op.create_table(
        "payment_cards",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("purpose", sa.Enum(CardPurpose), nullable=False),
        sa.Column("card_number", sa.String(32), nullable=False),
        sa.Column("holder_name", sa.String(128), nullable=False),
        *_ts(),
        sa.UniqueConstraint("purpose", name="uq_payment_cards_purpose"),
    )
    op.create_index("ix_payment_cards_purpose", "payment_cards", ["purpose"])

    # 4) discount_codes.
    op.create_table(
        "discount_codes",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("percent", sa.Integer(), nullable=False),
        sa.Column("max_uses", sa.Integer(), default=0),
        sa.Column("used_count", sa.Integer(), default=0),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("is_active", sa.Boolean(), default=True),
        *_ts(),
        sa.UniqueConstraint("code", name="uq_discount_codes_code"),
    )
    op.create_index("ix_discount_codes_code", "discount_codes", ["code"])


def downgrade() -> None:
    op.drop_index("ix_discount_codes_code", table_name="discount_codes")
    op.drop_table("discount_codes")
    op.drop_index("ix_payment_cards_purpose", table_name="payment_cards")
    op.drop_table("payment_cards")
    op.alter_column(
        "orders",
        "payment_method",
        existing_type=_NEW_PAYMENT_METHOD,
        type_=_OLD_PAYMENT_METHOD,
        existing_nullable=True,
    )
    op.alter_column(
        "accounts",
        "status",
        existing_type=_NEW_ACCOUNT_STATUS,
        type_=_OLD_ACCOUNT_STATUS,
        existing_nullable=False,
    )
