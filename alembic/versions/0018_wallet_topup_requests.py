"""wallet_topup_requests + wallet_transactions.type ENUM += WALLET_CHARGE

Adds the ``wallet_topup_requests`` table backing «📋 سفارشات در انتظار → 💰
سفارش‌های کیف پول». A user's wallet-charge receipt is now *persisted* (instead of
living only inside a notification button), so it can be listed, paginated and
approved exactly once. The wallet itself is credited only on approval, recorded as
the new ``WALLET_CHARGE`` transaction type — so the column's native ENUM is widened
on MySQL (SQLite tests build the schema via ``create_all`` and need no ALTER). The
table mirrors the existing ``requested_accounts`` shape (same id/FK/enum
conventions), so DDL and ORM agree on both engines.

Revision ID: 0018_wallet_topup_requests
Revises: 0017_referral_counted
Create Date: 2026-06-18
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.core.constants import PaymentMethod, TransactionType, WalletTopUpStatus

revision: str = "0018_wallet_topup_requests"
down_revision: Union[str, None] = "0017_referral_counted"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# SQLAlchemy's ``Enum`` persists the member *names*; mirror that here (same as 0013).
_TX_ALL = ", ".join(f"'{m.name}'" for m in TransactionType)
_TX_WITHOUT_CHARGE = ", ".join(
    f"'{m.name}'" for m in TransactionType if m is not TransactionType.WALLET_CHARGE
)


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
        "wallet_topup_requests",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("amount", sa.BigInteger()),
        sa.Column("payment_method", sa.Enum(PaymentMethod), nullable=True),
        sa.Column("receipt_file_id", sa.String(255), nullable=True),
        sa.Column(
            "status", sa.Enum(WalletTopUpStatus), default=WalletTopUpStatus.PENDING
        ),
        *_ts(),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_wallet_topup_requests_user_id", "wallet_topup_requests", ["user_id"]
    )
    op.create_index(
        "ix_wallet_topup_requests_status", "wallet_topup_requests", ["status"]
    )

    # Widen the native ENUM so the new WALLET_CHARGE transaction type can be
    # stored. The column was created nullable (0001), so keep it nullable here.
    bind = op.get_bind()
    if bind.dialect.name == "mysql":
        op.execute(f"ALTER TABLE wallet_transactions MODIFY type ENUM({_TX_ALL})")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "mysql":
        op.execute(
            f"ALTER TABLE wallet_transactions MODIFY type ENUM({_TX_WITHOUT_CHARGE})"
        )
    op.drop_index("ix_wallet_topup_requests_status", table_name="wallet_topup_requests")
    op.drop_index(
        "ix_wallet_topup_requests_user_id", table_name="wallet_topup_requests"
    )
    op.drop_table("wallet_topup_requests")
