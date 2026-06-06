"""payment method on orders + unified account fields

Revision ID: 0002_payment_unified_account
Revises: 0001_initial
Create Date: 2026-06-06
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.core.constants import AccountStatus, PaymentMethod

revision: str = "0002_payment_unified_account"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# AccountStatus before this migration (used for the ENUM widen/narrow).
_OLD_ACCOUNT_STATUS = sa.Enum(
    "AVAILABLE", "RESERVED", "SOLD", "HIDDEN", name="accountstatus"
)
_NEW_ACCOUNT_STATUS = sa.Enum(AccountStatus, name="accountstatus")


def upgrade() -> None:
    # 1) payment method on every order (nullable: legacy orders keep NULL).
    op.add_column(
        "orders",
        sa.Column("payment_method", sa.Enum(PaymentMethod), nullable=True),
    )

    # 2) unified account fields.
    op.add_column("accounts", sa.Column("special_items", sa.Text(), nullable=True))
    op.add_column("accounts", sa.Column("save_info", sa.Text(), nullable=True))
    op.add_column(
        "accounts", sa.Column("seller_user_id", sa.BigInteger(), nullable=True)
    )
    op.create_index(
        "ix_accounts_seller_user_id", "accounts", ["seller_user_id"]
    )

    # 3) widen the account status ENUM to include PENDING_REVIEW / SOLD_TO_ADMIN.
    op.alter_column(
        "accounts",
        "status",
        existing_type=_OLD_ACCOUNT_STATUS,
        type_=_NEW_ACCOUNT_STATUS,
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "accounts",
        "status",
        existing_type=_NEW_ACCOUNT_STATUS,
        type_=_OLD_ACCOUNT_STATUS,
        existing_nullable=False,
    )
    op.drop_index("ix_accounts_seller_user_id", table_name="accounts")
    op.drop_column("accounts", "seller_user_id")
    op.drop_column("accounts", "save_info")
    op.drop_column("accounts", "special_items")
    op.drop_column("orders", "payment_method")
