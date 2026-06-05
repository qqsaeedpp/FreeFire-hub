"""Account catalog, user sale-requests and requested (wanted) accounts."""
from __future__ import annotations

from sqlalchemy import BigInteger, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.constants import AccountStatus, SaleRequestStatus
from app.core.database import Base


class Account(Base):
    """An account listed in the shop for sale."""

    __tablename__ = "accounts"

    title: Mapped[str] = mapped_column(String(255))
    price: Mapped[int] = mapped_column(BigInteger)  # Toman
    level: Mapped[int] = mapped_column(Integer, default=0)
    skins_count: Mapped[int] = mapped_column(Integer, default=0)
    elite_count: Mapped[int] = mapped_column(Integer, default=0)
    gun_skins_count: Mapped[int] = mapped_column(Integer, default=0)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    images: Mapped[str | None] = mapped_column(Text, nullable=True)  # CSV of file_ids

    status: Mapped[AccountStatus] = mapped_column(
        Enum(AccountStatus), default=AccountStatus.AVAILABLE, index=True
    )
    # encrypted credentials, populated/delivered after a confirmed purchase
    credentials: Mapped[str | None] = mapped_column(Text, nullable=True)
    reserved_by_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class AccountSaleRequest(Base):
    """A user asking the shop to buy *their* account."""

    __tablename__ = "account_sale_requests"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    proposed_price: Mapped[int] = mapped_column(BigInteger)
    elite_count: Mapped[int] = mapped_column(Integer, default=0)
    skins: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    images: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[SaleRequestStatus] = mapped_column(
        Enum(SaleRequestStatus), default=SaleRequestStatus.PENDING, index=True
    )
    admin_note: Mapped[str | None] = mapped_column(String(255), nullable=True)


class RequestedAccount(Base):
    """A user requesting the shop to *find* an account for them (with deposit)."""

    __tablename__ = "requested_accounts"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    target_price: Mapped[int] = mapped_column(BigInteger)
    elite_count: Mapped[int] = mapped_column(Integer, default=0)
    sets: Mapped[str | None] = mapped_column(Text, nullable=True)
    guns: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    deposit_paid: Mapped[bool] = mapped_column(default=False)
    deposit_amount: Mapped[int] = mapped_column(BigInteger, default=0)
    status: Mapped[SaleRequestStatus] = mapped_column(
        Enum(SaleRequestStatus), default=SaleRequestStatus.PENDING, index=True
    )
