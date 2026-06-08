"""Forced-membership (lock) channels.

Each active row is a channel the user must join before using the bot. The bot
must be a member/admin of the channel for membership checks to work.
"""
from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class LockedChannel(Base):
    __tablename__ = "locked_channels"

    title: Mapped[str] = mapped_column(String(255))
    # Telegram numeric chat id (e.g. -1001234567890).
    chat_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    # Public @username without the leading "@" (None for private channels).
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    invite_link: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
