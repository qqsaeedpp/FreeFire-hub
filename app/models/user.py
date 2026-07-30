"""User model."""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.order import Order
    from app.models.ticket import Ticket
    from app.models.wallet import Wallet


class User(Base):
    __tablename__ = "users"

    telegram_id: Mapped[int] = mapped_column(
        BigInteger, unique=True, index=True, nullable=False
    )
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Verified mobile number in E.164 (``+989121234567``). Unique across accounts
    # so one line can onboard exactly one Telegram user; still nullable because a
    # user only gets one after passing the contact step.
    phone: Mapped[str | None] = mapped_column(
        String(20), unique=True, index=True, nullable=True
    )

    referral_code: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    referred_by_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    # Deep-link referral code captured at first /start, held until it can be
    # rewarded. Needed because a forced-join channel lock can intercept the very
    # first /start (consuming the deep-link payload) before the referral handler
    # runs; this lets the reward fire once the user finally passes the gate.
    pending_referral_code: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # --- onboarding verification (MySQL is the single source of truth) ---
    # Each stage stamps its own column so the correct next step survives a bot
    # restart, an FSM reset and a full Redis flush. A non-NULL ``phone`` alone is
    # NOT proof of verification: pre-existing rows may carry a hand-entered value,
    # so access is gated strictly on ``verification_completed_at``.
    phone_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )
    captcha_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )
    verification_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    has_purchased: Mapped[bool] = mapped_column(Boolean, default=False)

    wallet: Mapped["Wallet"] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    orders: Mapped[list["Order"]] = relationship(back_populates="user")
    tickets: Mapped[list["Ticket"]] = relationship(back_populates="user")

    @property
    def is_verified(self) -> bool:
        """Whether onboarding verification finished — the only access criterion."""
        return self.verification_completed_at is not None

    def __repr__(self) -> str:
        return f"<User id={self.id} tg={self.telegram_id}>"
