"""Discount codes — percentage-off coupons for diamond purchases."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class DiscountCode(Base):
    """A percentage discount usable on diamond orders.

    Validity is the conjunction of: ``is_active``, ``used_count < max_uses``
    (``max_uses == 0`` means unlimited), and ``expires_at`` in the future
    (``None`` means no time limit).
    """

    __tablename__ = "discount_codes"

    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    percent: Mapped[int] = mapped_column(Integer)  # 1..100
    max_uses: Mapped[int] = mapped_column(Integer, default=0)  # 0 = unlimited
    used_count: Mapped[int] = mapped_column(Integer, default=0)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
