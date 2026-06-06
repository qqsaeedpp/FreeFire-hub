"""Admin-editable bot texts, with optional premium-emoji entities.

Each row overrides a hardcoded default keyed by a stable ``key``. ``entities_json``
stores the message entities (notably ``custom_emoji``) as a JSON array so the text
can be re-sent with the exact same premium emoji the admin typed.
"""
from __future__ import annotations

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class BotText(Base):
    __tablename__ = "bot_texts"

    key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    content: Mapped[str] = mapped_column(Text)
    entities_json: Mapped[str | None] = mapped_column(Text, nullable=True)
