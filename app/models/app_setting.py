"""Durable, admin-editable key/value settings — the single source of truth.

Values an admin edits from the panel (the referral reward, diamond plan prices,
the level-up bundle price, …) live here in MySQL so they survive bot restarts,
Redis data loss and deploys. Previously these lived **only** in Redis and silently
reverted to hardcoded/env defaults whenever Redis lost the key — this table fixes
that class of bug.

Contract: nothing in startup / seeders / migrations may overwrite an existing
row; a default applies only until the first value is written. See
:mod:`app.services.settings_service`.
"""
from __future__ import annotations

from sqlalchemy import BigInteger, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    value: Mapped[str] = mapped_column(Text)
    # Telegram id of the admin who last changed it (NULL for the one-time legacy
    # import that migrates pre-existing Redis values into the table).
    updated_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
