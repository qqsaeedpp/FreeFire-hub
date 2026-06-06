"""Bot-text repository."""
from __future__ import annotations

from sqlalchemy import select

from app.models.bot_text import BotText
from app.repositories.base import BaseRepository


class BotTextRepository(BaseRepository[BotText]):
    model = BotText

    async def get_by_key(self, key: str) -> BotText | None:
        result = await self.session.execute(
            select(BotText).where(BotText.key == key)
        )
        return result.scalar_one_or_none()
