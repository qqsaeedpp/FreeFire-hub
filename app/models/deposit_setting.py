"""Admin-managed deposit (بیعانه) settings, one row per :class:`DepositType`.

Each flow that takes a deposit (requested account, account purchase) reads its
amount and destination card from here, so nothing is hardcoded in the handlers.
The card is stored inline (number + holder) to keep the setting self-contained.
"""
from __future__ import annotations

from sqlalchemy import BigInteger, Enum, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.constants import DepositType
from app.core.database import Base


class DepositSetting(Base):
    __tablename__ = "deposit_settings"

    deposit_type: Mapped[DepositType] = mapped_column(
        Enum(DepositType), unique=True, index=True
    )
    amount: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    card_number: Mapped[str] = mapped_column(String(32), default="", server_default="")
    card_holder: Mapped[str] = mapped_column(String(128), default="", server_default="")
