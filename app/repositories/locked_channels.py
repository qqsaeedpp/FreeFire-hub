"""Locked-channels repository."""
from __future__ import annotations

from sqlalchemy import select

from app.models.locked_channel import LockedChannel
from app.repositories.base import BaseRepository


class LockedChannelRepository(BaseRepository[LockedChannel]):
    model = LockedChannel

    async def all_ordered(self) -> list[LockedChannel]:
        result = await self.session.execute(
            select(LockedChannel).order_by(LockedChannel.id.asc())
        )
        return list(result.scalars().all())

    async def active(self) -> list[LockedChannel]:
        result = await self.session.execute(
            select(LockedChannel)
            .where(LockedChannel.is_active.is_(True))
            .order_by(LockedChannel.id.asc())
        )
        return list(result.scalars().all())

    async def get_by_chat_id(self, chat_id: int) -> LockedChannel | None:
        result = await self.session.execute(
            select(LockedChannel).where(LockedChannel.chat_id == chat_id)
        )
        return result.scalar_one_or_none()
