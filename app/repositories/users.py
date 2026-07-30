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

    async def get_for_update(self, user_id: int) -> User | None:
        """Read one user row under ``SELECT … FOR UPDATE``.

        Used to serialize verification finalization: two concurrent captcha
        callbacks for the same invitee both take this lock, so the loser only
        proceeds after the winner committed and then sees
        ``verification_completed_at`` already set. ``populate_existing`` forces
        the post-lock values onto any copy already in the session's identity map.
        On SQLite the locking clause is a no-op (serial test sessions).
        """
        result = await self.session.execute(
            select(User)
            .where(User.id == user_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def get_by_phone(self, phone: str) -> User | None:
        """Find the owner of a verified E.164 number (uniqueness pre-check)."""
        result = await self.session.execute(
            select(User).where(User.phone == phone)
        )
        return result.scalar_one_or_none()

    async def get_by_referral_code(self, code: str) -> User | None:
        result = await self.session.execute(
            select(User).where(User.referral_code == code)
        )
        return result.scalar_one_or_none()

    async def get_by_username(self, username: str) -> User | None:
        """Resolve an exact @username (case-insensitive; a leading @ is optional)."""
        uname = username.lstrip("@").strip()
        if not uname:
            return None
        result = await self.session.execute(
            select(User).where(func.lower(User.username) == uname.lower())
        )
        return result.scalars().first()

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

    async def list_active(self) -> list[User]:
        """Every non-banned, active user — used for the lottery draw."""
        result = await self.session.execute(
            select(User).where(
                User.is_active.is_(True), User.is_banned.is_(False)
            )
        )
        return list(result.scalars().all())
