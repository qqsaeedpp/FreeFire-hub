"""Admin-roster repository."""
from __future__ import annotations

from sqlalchemy import select

from app.models.admin import Admin
from app.repositories.base import BaseRepository


class AdminRepository(BaseRepository[Admin]):
    model = Admin

    async def all_ordered(self) -> list[Admin]:
        result = await self.session.execute(
            select(Admin).order_by(Admin.id.asc())
        )
        return list(result.scalars().all())

    async def get_by_user_id(self, user_id: int) -> Admin | None:
        result = await self.session.execute(
            select(Admin).where(Admin.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def all_user_ids(self) -> list[int]:
        result = await self.session.execute(select(Admin.user_id))
        return [int(uid) for uid in result.scalars().all()]
