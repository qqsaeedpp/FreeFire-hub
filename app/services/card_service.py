"""Card service — manages the card-to-card destination for each sales channel."""
from __future__ import annotations

from app.core.constants import CardPurpose
from app.models.payment_card import PaymentCard
from app.repositories.cards import PaymentCardRepository


class CardService:
    def __init__(self, cards: PaymentCardRepository) -> None:
        self.cards = cards

    async def get_card(self, purpose: CardPurpose) -> PaymentCard | None:
        return await self.cards.get_by_purpose(purpose)

    async def set_card(
        self, purpose: CardPurpose, card_number: str, holder_name: str
    ) -> PaymentCard:
        """Create or overwrite the stored card for ``purpose``."""
        card = await self.cards.get_by_purpose(purpose)
        if card is None:
            card = PaymentCard(
                purpose=purpose, card_number=card_number, holder_name=holder_name
            )
            return await self.cards.add(card)
        card.card_number = card_number
        card.holder_name = holder_name
        return card
