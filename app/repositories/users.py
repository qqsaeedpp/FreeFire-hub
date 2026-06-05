"""User repository."""
from __future__ import annotations

from sqlalchemy import String, cast, func, or_, select

from app.models.user import User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    model = User

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        result = await self.session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()

    async def get_by_referral_code(self, code: str) -> User | None:
        result = await self.session.execute(
            select(User).where(User.referral_code == code)
        )
        return result.scalar_one_or_none()

    async def search(self, query: str, *, offset: int = 0, limit: int = 20) -> list[User]:
        like = f"%{query}%"
        result = await self.session.execute(
            select(User)
            .where(
                or_(
                    User.username.ilike(like),
                    User.full_name.ilike(like),
                    cast(User.telegram_id, String).ilike(like),
                )
            )
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def count_active(self) -> int:
        result = await self.session.execute(
            select(func.count()).select_from(User).where(User.is_active.is_(True))
        )
        return int(result.scalar_one())
