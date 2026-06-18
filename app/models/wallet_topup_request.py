"""WalletTopUpRequest — a user's wallet-charge receipt awaiting admin review.

Persisting the request (instead of encoding it in a notification button) is what
lets it appear in «📋 سفارشات در انتظار → 💰 سفارش‌های کیف پول», be paginated, and
be approved exactly once. The wallet is **not** credited here — only when an admin
approves the request (see :class:`app.services.wallet_topup_service.WalletTopUpService`),
so the charge request and the wallet transaction stay separate concerns.
"""
from __future__ import annotations

from sqlalchemy import BigInteger, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.constants import PaymentMethod, WalletTopUpStatus
from app.core.database import Base


class WalletTopUpRequest(Base):
    __tablename__ = "wallet_topup_requests"

    # internal users.id (matches Order/Wallet/Referral; wallet credit uses this id)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    amount: Mapped[int] = mapped_column(BigInteger)  # Toman
    payment_method: Mapped[PaymentMethod | None] = mapped_column(
        Enum(PaymentMethod), nullable=True
    )
    receipt_file_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[WalletTopUpStatus] = mapped_column(
        Enum(WalletTopUpStatus), default=WalletTopUpStatus.PENDING, index=True
    )
