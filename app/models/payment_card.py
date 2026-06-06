"""Stored card-to-card destinations, one per sales channel (diamond / account)."""
from __future__ import annotations

from sqlalchemy import Enum, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.constants import CardPurpose
from app.core.database import Base


class PaymentCard(Base):
    """A card the buyer transfers to, scoped to a sales channel.

    At most one row per :class:`CardPurpose`; the admin overwrites it in place.
    """

    __tablename__ = "payment_cards"

    purpose: Mapped[CardPurpose] = mapped_column(
        Enum(CardPurpose), unique=True, index=True
    )
    card_number: Mapped[str] = mapped_column(String(32))
    holder_name: Mapped[str] = mapped_column(String(128))
