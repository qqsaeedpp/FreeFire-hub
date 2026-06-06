"""Admin-editable appearance/text settings for the bot's main buttons.

Each row overrides a hardcoded default keyed by a stable ``key``. Only ``text``
and ``emoji`` are used for rendering today (item 5: DB-editable button text).
``button_type``, ``is_enabled`` and ``custom_emoji_id``/``emoji_text`` are stored
now so the later appearance system (colors / premium emoji) needs no migration.

Note: Telegram inline/reply buttons can't render colors or custom (premium)
emoji on the button label itself — those fields are reserved for future use
(e.g. styling the message text around the keyboard).
"""
from __future__ import annotations

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ButtonSettings(Base):
    __tablename__ = "button_settings"

    key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    text: Mapped[str | None] = mapped_column(String(128), nullable=True)
    emoji: Mapped[str | None] = mapped_column(String(32), nullable=True)
    button_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    custom_emoji_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    emoji_text: Mapped[str | None] = mapped_column(String(32), nullable=True)
