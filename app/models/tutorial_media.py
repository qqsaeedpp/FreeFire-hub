"""Admin-managed tutorial media (videos), keyed by a stable ``key``.

Each row stores a Telegram ``file_id`` for a tutorial video so it can be
re-sent to users on demand. The admin can replace the file_id from the panel
without any code change (e.g. ``GOOGLE_BACKUP_CODE_VIDEO``).
"""
from __future__ import annotations

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class TutorialMedia(Base):
    __tablename__ = "tutorial_media"

    key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    file_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    caption: Mapped[str | None] = mapped_column(Text, nullable=True)
