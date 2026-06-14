"""Ban-management service — ban/unban with reason, owner/admin protected.

The bot gate (``BanMiddleware``) only reads ``User.is_banned``; this service is
the single writer of that flag and keeps the :class:`BannedUser` audit row in
sync. Owners (env ``ADMIN_ID``) and admins (``User.is_admin``) can never be
banned, so a misclick can't lock an operator out of the bot.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.core.config import settings
from app.models.banned_user import BannedUser
from app.models.user import User
from app.repositories.banned_users import BannedUserRepository
from app.repositories.users import UserRepository


class BanError(Exception):
    """Raised on an invalid ban/unban action (carries a user-facing message)."""


@dataclass
class BanEntry:
    """A banned-user row for the management list (ban record + user profile)."""

    user_id: int
    reason: str | None
    banned_by: int | None
    banned_at: object
    username: str | None
    full_name: str | None


class BanService:
    def __init__(self, repo: BannedUserRepository, users: UserRepository) -> None:
        self.repo = repo
        self.users = users

    # ------------------------------ checks ------------------------------
    def _is_owner(self, user_id: int) -> bool:
        return user_id in settings.admin_ids

    async def is_banned(self, user_id: int) -> bool:
        return await self.repo.get_active(user_id) is not None

    # ------------------------------ mutations ------------------------------
    async def ban_user(
        self, user_id: int, *, reason: str | None, banned_by: int | None
    ) -> BannedUser:
        """Ban ``user_id`` (a Telegram id). Owners/admins are protected."""
        if self._is_owner(user_id):
            raise BanError("مالک ربات (OWNER) قابل مسدودسازی نیست.")
        user = await self.users.get_by_telegram_id(user_id)
        if user is None:
            raise BanError(
                "کاربری با این آیدی پیدا نشد. کاربر باید حداقل یک‌بار ربات را استارت کرده باشد."
            )
        if user.is_admin:
            raise BanError("این کاربر ادمین است و قابل مسدودسازی نیست.")
        if user.is_banned:
            raise BanError("این کاربر از قبل مسدود است.")
        # Close any stale open record, then write a fresh active one.
        await self.repo.deactivate_for(user_id)
        record = BannedUser(user_id=user_id, reason=reason, banned_by=banned_by)
        await self.repo.add(record)
        user.is_banned = True
        await self.repo.session.flush()
        return record

    async def unban_user(self, user_id: int) -> None:
        """Lift the ban: clear the flag and close the audit record(s)."""
        user = await self.users.get_by_telegram_id(user_id)
        active = await self.repo.get_active(user_id)
        if user is None and active is None:
            raise BanError("این کاربر مسدود نیست.")
        await self.repo.deactivate_for(user_id)
        if user is not None:
            user.is_banned = False
        await self.repo.session.flush()

    # ------------------------------ listing ------------------------------
    async def list_banned(
        self, *, page: int = 1, page_size: int = 10
    ) -> tuple[list[BanEntry], int]:
        offset = (page - 1) * page_size
        rows = await self.repo.list_active(offset=offset, limit=page_size)
        total = await self.repo.count_active()
        entries: list[BanEntry] = []
        for r in rows:
            user: User | None = await self.users.get_by_telegram_id(r.user_id)
            entries.append(
                BanEntry(
                    user_id=r.user_id,
                    reason=r.reason,
                    banned_by=r.banned_by,
                    banned_at=r.banned_at,
                    username=user.username if user else None,
                    full_name=user.full_name if user else None,
                )
            )
        return entries, total
