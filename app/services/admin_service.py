"""Admin-management service — runtime-editable, role-aware admin roster.

Why this exists (root cause of the "third admin does nothing" bug): admin
privilege used to come *only* from the ``ADMIN_ID`` env var, which is parsed once
into a process-cached list and needs a full restart to change. The ``users.is_admin``
column existed but **nothing ever set it**, and there was no add/remove/list flow.
So any attempt to add another admin from inside the bot had no effect.

The fix: admins are stored in the ``admins`` table (unlimited, with roles) and the
privilege is *mirrored* onto ``User.is_admin`` here. Because ``db_user`` is reloaded
on every update, a newly added admin gets access on their very next interaction —
no restart. A short Redis cache keeps the hot ``is_admin`` lookup cheap and is
invalidated immediately on any change.

Roles: the env ``ADMIN_ID`` ids are the bootstrap OWNER(s) (cannot be removed from
the bot). Admins added through the panel are ADMIN and cannot manage owners.
"""
from __future__ import annotations

from dataclasses import dataclass

from redis.asyncio import Redis

from app.core.config import settings
from app.core.constants import AdminRole
from app.models.admin import Admin
from app.repositories.admins import AdminRepository
from app.repositories.users import UserRepository

_IDS_KEY = "admins:ids"
_IDS_TTL = 300  # seconds


class AdminError(Exception):
    """Raised on an invalid admin-management action (with a user-facing message)."""


@dataclass
class AdminEntry:
    """A unified row for the management list (env owners + DB admins)."""

    user_id: int
    username: str | None
    first_name: str | None
    role: AdminRole
    removable: bool  # env owners can't be removed from the bot


class AdminService:
    def __init__(
        self,
        repo: AdminRepository,
        users: UserRepository,
        redis: Redis | None = None,
    ) -> None:
        self.repo = repo
        self.users = users
        self.redis = redis

    # ------------------------------ checks ------------------------------
    def is_owner(self, user_id: int) -> bool:
        """Owners are the bootstrap env ids (full access incl. admin management)."""
        return user_id in settings.admin_ids

    async def is_admin(self, user_id: int) -> bool:
        if user_id in settings.admin_ids:
            return True
        return user_id in await self._cached_ids()

    async def all_admin_ids(self) -> set[int]:
        """Telegram ids of every authorized admin (env owners + panel-added).

        Used by the additive new-order notification layer to fan a copy of the
        existing admin notification out to *all* admins, without touching the
        current single-admin send or the Pending-Orders flow.
        """
        return set(settings.admin_ids) | await self._cached_ids()

    async def get_role(self, user_id: int) -> AdminRole | None:
        if user_id in settings.admin_ids:
            return AdminRole.OWNER
        admin = await self.repo.get_by_user_id(user_id)
        return admin.role if admin else None

    async def _cached_ids(self) -> set[int]:
        if self.redis is not None:
            try:
                raw = await self.redis.get(_IDS_KEY)
                if raw:
                    return {int(p) for p in raw.split(",") if p}
            except Exception:  # noqa: BLE001 - cache must never block access checks
                pass
        ids = await self.repo.all_user_ids()
        if self.redis is not None:
            try:
                await self.redis.set(_IDS_KEY, ",".join(str(i) for i in ids), ex=_IDS_TTL)
            except Exception:  # noqa: BLE001
                pass
        return set(ids)

    async def _invalidate(self) -> None:
        if self.redis is not None:
            try:
                await self.redis.delete(_IDS_KEY)
            except Exception:  # noqa: BLE001
                pass

    # ------------------------------ listing ------------------------------
    async def list_admins(self) -> list[AdminEntry]:
        """Owners (from env) first, then panel-added admins."""
        entries: list[AdminEntry] = []
        seen: set[int] = set()
        for uid in settings.admin_ids:
            user = await self.users.get_by_telegram_id(uid)
            entries.append(
                AdminEntry(
                    user_id=uid,
                    username=user.username if user else None,
                    first_name=user.full_name if user else None,
                    role=AdminRole.OWNER,
                    removable=False,
                )
            )
            seen.add(uid)
        for admin in await self.repo.all_ordered():
            if admin.user_id in seen:
                continue
            entries.append(
                AdminEntry(
                    user_id=admin.user_id,
                    username=admin.username,
                    first_name=admin.first_name,
                    role=admin.role,
                    removable=True,
                )
            )
        return entries

    # ------------------------------ mutations ------------------------------
    async def add_admin(self, user_id: int, *, role: AdminRole = AdminRole.ADMIN) -> Admin:
        """Grant admin to ``user_id`` (must have started the bot). Effective at once.

        Mirrors ``User.is_admin = True`` so every existing access check applies
        immediately, and stores the role + captured profile in the roster.
        """
        if user_id in settings.admin_ids:
            raise AdminError("این کاربر از قبل مالک (OWNER) ربات است.")
        user = await self.users.get_by_telegram_id(user_id)
        if user is None:
            raise AdminError(
                "کاربری با این آیدی پیدا نشد. ابتدا باید ربات را استارت کرده باشد."
            )
        existing = await self.repo.get_by_user_id(user_id)
        if existing is not None:
            raise AdminError("این کاربر از قبل ادمین است.")
        admin = Admin(
            user_id=user_id,
            username=user.username,
            first_name=user.full_name,
            role=role,
        )
        await self.repo.add(admin)
        user.is_admin = True
        await self.repo.session.flush()
        await self._invalidate()
        return admin

    async def remove_admin(self, user_id: int) -> None:
        """Revoke a panel-added admin. Owners (env) cannot be removed here."""
        if user_id in settings.admin_ids:
            raise AdminError("مالک ربات (OWNER) قابل حذف نیست.")
        admin = await self.repo.get_by_user_id(user_id)
        if admin is None:
            raise AdminError("این کاربر ادمین نیست.")
        await self.repo.delete(admin)
        user = await self.users.get_by_telegram_id(user_id)
        if user is not None:
            user.is_admin = False
        await self.repo.session.flush()
        await self._invalidate()
