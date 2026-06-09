"""Admin roster — the authoritative, runtime-editable list of bot admins.

Admins added here take effect immediately (no restart): :class:`AdminService`
mirrors the privilege onto ``User.is_admin`` so every existing access check keeps
working, while this table carries the role + profile for the management panel.

The ``ADMIN_ID`` env var still bootstraps the initial owner(s); those are treated
as OWNER and are not stored here.
"""
from __future__ import annotations

from sqlalchemy import BigInteger, Enum, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.constants import AdminRole
from app.core.database import Base


class Admin(Base):
    __tablename__ = "admins"

    user_id: Mapped[int] = mapped_column(
        BigInteger, unique=True, index=True, nullable=False
    )
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[AdminRole] = mapped_column(
        Enum(AdminRole), default=AdminRole.ADMIN, server_default=AdminRole.ADMIN.value
    )
