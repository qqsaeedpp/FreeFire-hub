"""Payment-card repository (one card per sales channel)."""
from __future__ import annotations

from sqlalchemy import select

from app.core.constants import CardPurpose
from app.models.payment_card import PaymentCard
from app.repositories.base import BaseRepository


class PaymentCardRepository(BaseRepository[PaymentCard]):
    model = PaymentCard

    async def get_by_purpose(self, purpose: CardPurpose) -> PaymentCard | None:
        result = await self.session.execute(
            select(PaymentCard).where(PaymentCard.purpose == purpose)
        )
        return result.scalar_one_or_none()
