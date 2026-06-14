"""Banned-user repository — active-ban lookups for the management panel."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select, update

from app.models.banned_user import BannedUser
from app.repositories.base import BaseRepository


class BannedUserRepository(BaseRepository[BannedUser]):
    model = BannedUser

    async def get_active(self, user_id: int) -> BannedUser | None:
        result = await self.session.execute(
            select(BannedUser).where(
                BannedUser.user_id == user_id, BannedUser.is_active.is_(True)
            )
        )
        return result.scalars().first()

    async def list_active(self, *, offset: int = 0, limit: int = 10) -> list[BannedUser]:
        result = await self.session.execute(
            select(BannedUser)
            .where(BannedUser.is_active.is_(True))
            .order_by(BannedUser.id.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def count_active(self) -> int:
        result = await self.session.execute(
            select(func.count())
            .select_from(BannedUser)
            .where(BannedUser.is_active.is_(True))
        )
        return int(result.scalar_one())

    async def deactivate_for(self, user_id: int) -> None:
        """Close every open ban record for a user (called on unban / re-ban)."""
        await self.session.execute(
            update(BannedUser)
            .where(BannedUser.user_id == user_id, BannedUser.is_active.is_(True))
            .values(is_active=False, unbanned_at=datetime.utcnow())
        )
        await self.session.flush()
