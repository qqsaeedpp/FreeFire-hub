"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-06-05
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.core.constants import (
    AccountStatus,
    LoginMethod,
    OrderStatus,
    OrderType,
    PaymentStatus,
    SaleRequestStatus,
    TicketStatus,
    TransactionType,
)

revision: str = "0001_initial"
down_revision: Union[str, None] = None
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
        "users",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(64), nullable=True),
        sa.Column("full_name", sa.String(255), nullable=True),
        sa.Column("phone", sa.String(20), nullable=True),
        sa.Column("referral_code", sa.String(16), nullable=False),
        sa.Column("referred_by_id", sa.BigInteger(), nullable=True),
        sa.Column("is_active", sa.Boolean(), default=True),
        sa.Column("is_banned", sa.Boolean(), default=False),
        sa.Column("is_admin", sa.Boolean(), default=False),
        sa.Column("has_purchased", sa.Boolean(), default=False),
        *_ts(),
        sa.UniqueConstraint("telegram_id", name="uq_users_telegram_id"),
        sa.UniqueConstraint("referral_code", name="uq_users_referral_code"),
    )
    op.create_index("ix_users_telegram_id", "users", ["telegram_id"])
    op.create_index("ix_users_referral_code", "users", ["referral_code"])

    op.create_table(
        "wallets",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("balance", sa.BigInteger(), default=0),
        *_ts(),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", name="uq_wallets_user_id"),
    )
    op.create_index("ix_wallets_user_id", "wallets", ["user_id"])

    op.create_table(
        "wallet_transactions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("wallet_id", sa.BigInteger(), nullable=False),
        sa.Column("amount", sa.BigInteger()),
        sa.Column("type", sa.Enum(TransactionType)),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column("balance_after", sa.BigInteger(), default=0),
        *_ts(),
        sa.ForeignKeyConstraint(["wallet_id"], ["wallets.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_wallet_transactions_wallet_id", "wallet_transactions", ["wallet_id"])

    op.create_table(
        "accounts",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("title", sa.String(255)),
        sa.Column("price", sa.BigInteger()),
        sa.Column("level", sa.Integer(), default=0),
        sa.Column("skins_count", sa.Integer(), default=0),
        sa.Column("elite_count", sa.Integer(), default=0),
        sa.Column("gun_skins_count", sa.Integer(), default=0),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("images", sa.Text(), nullable=True),
        sa.Column("status", sa.Enum(AccountStatus), default=AccountStatus.AVAILABLE),
        sa.Column("credentials", sa.Text(), nullable=True),
        sa.Column("reserved_by_id", sa.BigInteger(), nullable=True),
        *_ts(),
    )
    op.create_index("ix_accounts_status", "accounts", ["status"])

    op.create_table(
        "account_sale_requests",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("proposed_price", sa.BigInteger()),
        sa.Column("elite_count", sa.Integer(), default=0),
        sa.Column("skins", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("images", sa.Text(), nullable=True),
        sa.Column("status", sa.Enum(SaleRequestStatus), default=SaleRequestStatus.PENDING),
        sa.Column("admin_note", sa.String(255), nullable=True),
        *_ts(),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_account_sale_requests_user_id", "account_sale_requests", ["user_id"])
    op.create_index("ix_account_sale_requests_status", "account_sale_requests", ["status"])

    op.create_table(
        "requested_accounts",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("target_price", sa.BigInteger()),
        sa.Column("elite_count", sa.Integer(), default=0),
        sa.Column("sets", sa.Text(), nullable=True),
        sa.Column("guns", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("deposit_paid", sa.Boolean(), default=False),
        sa.Column("deposit_amount", sa.BigInteger(), default=0),
        sa.Column("status", sa.Enum(SaleRequestStatus), default=SaleRequestStatus.PENDING),
        *_ts(),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_requested_accounts_user_id", "requested_accounts", ["user_id"])
    op.create_index("ix_requested_accounts_status", "requested_accounts", ["status"])

    op.create_table(
        "orders",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("order_type", sa.Enum(OrderType)),
        sa.Column("amount", sa.BigInteger()),
        sa.Column("status", sa.Enum(OrderStatus), default=OrderStatus.PENDING),
        sa.Column("paid_from_wallet", sa.Boolean(), default=False),
        sa.Column("admin_note", sa.String(255), nullable=True),
        sa.Column("type", sa.String(32)),
        *_ts(),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_orders_user_id", "orders", ["user_id"])
    op.create_index("ix_orders_order_type", "orders", ["order_type"])
    op.create_index("ix_orders_status", "orders", ["status"])

    op.create_table(
        "diamond_orders",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("plan_name", sa.String(64)),
        sa.Column("diamonds", sa.Integer()),
        sa.Column("uid", sa.String(32), nullable=True),
        sa.Column("account_email", sa.String(255), nullable=True),
        sa.Column("account_password", sa.String(255), nullable=True),
        sa.Column("backup_code", sa.String(255), nullable=True),
        sa.Column("login_method", sa.Enum(LoginMethod), nullable=True),
        sa.ForeignKeyConstraint(["id"], ["orders.id"], ondelete="CASCADE"),
    )

    op.create_table(
        "account_orders",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("account_id", sa.BigInteger()),
        sa.Column("delivered_credentials", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["id"], ["orders.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_account_orders_account_id", "account_orders", ["account_id"])

    op.create_table(
        "payments",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("order_id", sa.BigInteger(), nullable=False),
        sa.Column("amount", sa.BigInteger()),
        sa.Column("receipt_file_id", sa.String(255), nullable=True),
        sa.Column("status", sa.Enum(PaymentStatus), default=PaymentStatus.PENDING),
        *_ts(),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("order_id", name="uq_payments_order_id"),
    )
    op.create_index("ix_payments_order_id", "payments", ["order_id"])
    op.create_index("ix_payments_status", "payments", ["status"])

    op.create_table(
        "referrals",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("referrer_id", sa.BigInteger(), nullable=False),
        sa.Column("referred_id", sa.BigInteger(), nullable=False),
        sa.Column("rewarded", sa.Boolean(), default=False),
        sa.Column("reward_amount", sa.BigInteger(), default=0),
        *_ts(),
        sa.ForeignKeyConstraint(["referrer_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["referred_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("referred_id", name="uq_referred_once"),
    )
    op.create_index("ix_referrals_referrer_id", "referrals", ["referrer_id"])
    op.create_index("ix_referrals_referred_id", "referrals", ["referred_id"])

    op.create_table(
        "tickets",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("subject", sa.String(255)),
        sa.Column("status", sa.Enum(TicketStatus), default=TicketStatus.OPEN),
        *_ts(),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_tickets_user_id", "tickets", ["user_id"])
    op.create_index("ix_tickets_status", "tickets", ["status"])

    op.create_table(
        "ticket_messages",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("ticket_id", sa.BigInteger(), nullable=False),
        sa.Column("is_from_admin", sa.Boolean(), default=False),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("file_id", sa.String(255), nullable=True),
        sa.Column("file_type", sa.String(16), nullable=True),
        *_ts(),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_ticket_messages_ticket_id", "ticket_messages", ["ticket_id"])

    op.create_table(
        "admin_logs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("event", sa.String(64)),
        sa.Column("actor_id", sa.BigInteger(), nullable=True),
        sa.Column("payload", sa.Text(), nullable=True),
        *_ts(),
    )
    op.create_index("ix_admin_logs_event", "admin_logs", ["event"])


def downgrade() -> None:
    for table in [
        "admin_logs",
        "ticket_messages",
        "tickets",
        "referrals",
        "payments",
        "account_orders",
        "diamond_orders",
        "orders",
        "requested_accounts",
        "account_sale_requests",
        "accounts",
        "wallet_transactions",
        "wallets",
        "users",
    ]:
        op.drop_table(table)
