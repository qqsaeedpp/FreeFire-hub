"""Order models — base Order plus diamond/account specializations (joined table)."""
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import LoginMethod, OrderStatus, OrderType, PaymentMethod
from app.core.database import Base

if TYPE_CHECKING:
    from app.models.payment import Payment
    from app.models.user import User


class Order(Base):
    __tablename__ = "orders"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    order_type: Mapped[OrderType] = mapped_column(Enum(OrderType), index=True)
    amount: Mapped[int] = mapped_column(BigInteger)  # total price in Toman
    status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus), default=OrderStatus.PENDING, index=True
    )
    paid_from_wallet: Mapped[bool] = mapped_column(default=False)
    payment_method: Mapped[PaymentMethod | None] = mapped_column(
        Enum(PaymentMethod), nullable=True
    )
    admin_note: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # discriminator for the joined-table specializations
    type: Mapped[str] = mapped_column(String(32))

    user: Mapped["User"] = relationship(back_populates="orders")
    payment: Mapped["Payment | None"] = relationship(
        back_populates="order", uselist=False, cascade="all, delete-orphan"
    )

    __mapper_args__ = {"polymorphic_identity": "order", "polymorphic_on": type}


class DiamondOrder(Order):
    __tablename__ = "diamond_orders"

    id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), primary_key=True
    )
    plan_name: Mapped[str] = mapped_column(String(64))
    diamonds: Mapped[int] = mapped_column(Integer)

    # UID flow
    uid: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # account-credentials flow (all encrypted)
    account_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    account_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    backup_code: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # extra recovery details collected for the account-credentials flow
    gmail: Mapped[str | None] = mapped_column(String(255), nullable=True)
    gmail_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    gmail_backup_code: Mapped[str | None] = mapped_column(String(255), nullable=True)
    account_backup_code: Mapped[str | None] = mapped_column(String(255), nullable=True)
    login_method: Mapped[LoginMethod | None] = mapped_column(
        Enum(LoginMethod), nullable=True
    )

    # "inline" → subclass columns are loaded via an OUTER JOIN in the base query
    # whenever an Order is loaded polymorphically (session.get(Order, id) or
    # select(Order)). Without it the subclass columns are deferred and a first
    # access (e.g. order.login_method) triggers a *synchronous* lazy SELECT,
    # which raises MissingGreenlet under the async engine.
    __mapper_args__ = {"polymorphic_identity": "diamond", "polymorphic_load": "inline"}


class AccountOrder(Order):
    __tablename__ = "account_orders"

    id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), primary_key=True
    )
    account_id: Mapped[int] = mapped_column(BigInteger, index=True)
    delivered_credentials: Mapped[str | None] = mapped_column(Text, nullable=True)

    # See DiamondOrder: load subclass columns inline to avoid async lazy-loads.
    __mapper_args__ = {"polymorphic_identity": "account", "polymorphic_load": "inline"}
