"""Advertising channels («کانال‌های تبلیغ»).

Each active row receives a copy of every new-listing announcement the moment an
admin lists an account. The bot must be an admin of the channel with the «Post
Messages» right (or a member, for a group) for the post to go through.
"""
from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AdChannel(Base):
    __tablename__ = "ad_channels"

    # Channel title as last read from Telegram. A row carried over from the old
    # LISTING_CHANNEL_ID setting starts with its chat id here until resolved.
    title: Mapped[str] = mapped_column(String(255))
    # Telegram numeric chat id (e.g. -1001234567890).
    chat_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    # Public @username without the leading "@" (None for private channels).
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")

    @property
    def title_unresolved(self) -> bool:
        """True while the title is still the chat-id placeholder."""
        return self.title == str(self.chat_id)
