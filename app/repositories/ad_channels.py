"""Advertising-channels repository."""
from __future__ import annotations

from sqlalchemy import select

from app.models.ad_channel import AdChannel
from app.repositories.base import BaseRepository


class AdChannelRepository(BaseRepository[AdChannel]):
    model = AdChannel

    async def all_ordered(self) -> list[AdChannel]:
        result = await self.session.execute(select(AdChannel).order_by(AdChannel.id.asc()))
        return list(result.scalars().all())

    async def active(self) -> list[AdChannel]:
        result = await self.session.execute(
            select(AdChannel)
            .where(AdChannel.is_active.is_(True))
            .order_by(AdChannel.id.asc())
        )
        return list(result.scalars().all())

    async def get_by_chat_id(self, chat_id: int) -> AdChannel | None:
        result = await self.session.execute(
            select(AdChannel).where(AdChannel.chat_id == chat_id)
        )
        return result.scalar_one_or_none()
