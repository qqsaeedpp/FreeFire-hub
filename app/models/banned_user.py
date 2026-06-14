"""Ban records — the audit trail behind the ``users.is_banned`` fast-path flag.

Why both: the :class:`~app.middlewares.ban.BanMiddleware` reads ``User.is_banned``
(already loaded with ``db_user`` on every update, so the hot path stays a single
boolean check). This table carries the *why/who/when* so the admin panel can list
active bans, show the reason, and unban — without changing the gate's hot path.

One row per ban action; ``is_active`` flips to ``False`` on unban (history kept).
``user_id`` / ``banned_by`` are Telegram ids (consistent with ``admins.user_id``).
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class BannedUser(Base):
    __tablename__ = "banned_users"

    user_id: Mapped[int] = mapped_column(
        BigInteger, index=True, nullable=False
    )
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    banned_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    banned_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    unbanned_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="1", index=True
    )
