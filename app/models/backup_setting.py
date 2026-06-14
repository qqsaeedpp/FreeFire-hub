"""Automatic-backup configuration — a single global row.

Holds where backups are sent (a Telegram user id or a private channel id), how
often the automatic job runs, and whether it is enabled. The actual data lives
in the MySQL dump produced by :class:`~app.services.backup_service.BackupService`;
this row only configures destination + cadence.
"""
from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, Enum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.constants import BackupScheduleType, BackupTargetType
from app.core.database import Base


class BackupSetting(Base):
    __tablename__ = "backup_settings"

    target_type: Mapped[BackupTargetType | None] = mapped_column(
        Enum(BackupTargetType), nullable=True
    )
    target_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    schedule_type: Mapped[BackupScheduleType] = mapped_column(
        Enum(BackupScheduleType),
        default=BackupScheduleType.DAILY,
        server_default=BackupScheduleType.DAILY.value,
    )
    is_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0"
    )
