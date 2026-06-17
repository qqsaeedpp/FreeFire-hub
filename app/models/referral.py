"""Referral relationship model."""
from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Referral(Base):
    __tablename__ = "referrals"
    __table_args__ = (UniqueConstraint("referred_id", name="uq_referred_once"),)

    referrer_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    referred_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    rewarded: Mapped[bool] = mapped_column(Boolean, default=False)
    reward_amount: Mapped[int] = mapped_column(BigInteger, default=0)
    # Whether this relation contributes to its referrer's *displayed* statistics.
    # A reset (per-user or global) flips this to False to zero the counters WITHOUT
    # deleting the row, so the invite relation and the double-reward guard
    # (``get_by_referred``) stay intact. Defaults True → every new referral counts.
    counted: Mapped[bool] = mapped_column(Boolean, default=True)
