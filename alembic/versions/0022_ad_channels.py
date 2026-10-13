"""ad_channels — admin-managed advertising channels

Adds the ``ad_channels`` table behind «📢 مدیریت کانال‌ها → 📣 کانال‌های تبلیغ»:
every active row receives a copy of each new-listing announcement the moment an
admin lists an account.

Until now listings were mirrored into exactly one channel, read from the
``LISTING_CHANNEL_ID`` setting (env var, then ``.env``, else ``-1003783566987``;
``0`` turned the mirror off). That channel is carried over as the first row so it
keeps receiving listings and shows up in the new admin list. The migration can't
reach Telegram, so the row's title starts as its chat id; the bot fills in the
real name the first time an admin opens the list.

Revision ID: 0022_ad_channels
Revises: 0021_user_verification
Create Date: 2026-10-13
"""
from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from dotenv import dotenv_values

revision: str = "0022_ad_channels"
down_revision: Union[str, None] = "0021_user_verification"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# --- frozen copy of how the removed LISTING_CHANNEL_ID setting was resolved ---
_LEGACY_ENV_KEY = "LISTING_CHANNEL_ID"
_LEGACY_DEFAULT = -1003783566987


def _legacy_channel_id(
    environ: Mapping[str, str] | None = None, env_file: str | Path = ".env"
) -> int | None:
    """The channel the bot mirrored listings into before this migration.

    Same precedence the old pydantic setting used: the process environment, then
    the ``.env`` file, then the built-in default. ``0`` (mirror off) or a value
    the old setting would have rejected means there is nothing to carry over.
    """
    environ = os.environ if environ is None else environ
    raw = environ.get(_LEGACY_ENV_KEY)
    if raw is None and Path(env_file).is_file():
        raw = dotenv_values(env_file).get(_LEGACY_ENV_KEY)
    if raw is None:
        return _LEGACY_DEFAULT
    try:
        value = int(str(raw).strip())
    except ValueError:
        return None
    return value or None


def upgrade() -> None:
    table = op.create_table(
        "ad_channels",
        # BIGINT AUTO_INCREMENT on MySQL; INTEGER on SQLite so its rowid
        # autoincrement applies (same variant as the ORM base, for the tests).
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            autoincrement=True,
            primary_key=True,
        ),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.UniqueConstraint("chat_id", name="uq_ad_channels_chat_id"),
    )
    op.create_index("ix_ad_channels_chat_id", "ad_channels", ["chat_id"])

    legacy = _legacy_channel_id()
    if legacy is not None:
        op.bulk_insert(
            table,
            [{"title": str(legacy), "chat_id": legacy, "username": None, "is_active": True}],
        )


def downgrade() -> None:
    op.drop_index("ix_ad_channels_chat_id", table_name="ad_channels")
    op.drop_table("ad_channels")
