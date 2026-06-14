"""backup_settings — destination + cadence for automatic database backups

Adds the single-row ``backup_settings`` table backing «💾 تنظیمات بکاپ»: where
backups are delivered (``target_type`` USER/CHANNEL + ``target_id``), how often
the automatic job runs (``schedule_type``) and whether it is enabled. The backup
*data* is a MySQL dump produced at runtime — this row only holds configuration.
``sa.Enum(...)`` mirrors the model exactly (same construct as ``0011_admins``), so
the DDL and the ORM agree on the stored representation. Plain ``CREATE TABLE``
works on both MySQL (prod) and SQLite (tests).

Revision ID: 0016_backup_settings
Revises: 0015_banned_users
Create Date: 2026-06-14
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.core.constants import BackupScheduleType, BackupTargetType

revision: str = "0016_backup_settings"
down_revision: Union[str, None] = "0015_banned_users"
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
        "backup_settings",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("target_type", sa.Enum(BackupTargetType), nullable=True),
        sa.Column("target_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "schedule_type",
            sa.Enum(BackupScheduleType),
            nullable=False,
            server_default=BackupScheduleType.DAILY.value,
        ),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default="0"),
        *_ts(),
    )


def downgrade() -> None:
    op.drop_table("backup_settings")
