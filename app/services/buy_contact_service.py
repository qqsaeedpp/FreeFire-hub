"""Who the green «✅ خرید» button under a new-listing announcement opens.

The owner picks one admin in «👮 مدیریت ادمین‌ها ← 🛒 ادمین دکمهٔ خرید». The
choice is stored durably in ``app_settings`` as that admin's Telegram id, and the
link is built from the admin's *current* @username when a listing goes out, so a
renamed admin keeps receiving buyers. With nothing chosen — or when the chosen
admin was removed or no longer has a username — the button falls back to
``LISTING_BUY_USERNAME`` (default ``@vasete_shah``).
"""
from __future__ import annotations

from dataclasses import dataclass

from app.core.config import settings
from app.repositories.users import UserRepository
from app.services.admin_service import AdminEntry, AdminService
from app.services.settings_service import KEY_LISTING_BUY_ADMIN, SettingsService


class BuyContactError(Exception):
    """Raised when an admin can't be picked (with a user-facing message)."""


@dataclass(frozen=True)
class BuyContact:
    username: str
    # The picked admin; ``None`` when the default username is in use.
    user_id: int | None = None

    @property
    def url(self) -> str:
        return f"https://t.me/{self.username}"

    @property
    def is_default(self) -> bool:
        return self.user_id is None


def default_username() -> str:
    return settings.listing_buy_username.strip().lstrip("@")


class BuyContactService:
    def __init__(
        self, store: SettingsService, admin: AdminService, users: UserRepository
    ) -> None:
        self.store = store
        self.admin = admin
        self.users = users

    async def selected_admin_id(self) -> int | None:
        raw = await self.store.get(KEY_LISTING_BUY_ADMIN)
        try:
            return int(raw) if raw else None
        except ValueError:
            return None

    async def candidates(self) -> list[AdminEntry]:
        """Every admin, with the @username they have *now*.

        The roster keeps the username captured when an admin was added; the users
        table is refreshed on every update, so it wins whenever the admin is known
        there (including a username they have since removed).
        """
        entries = await self.admin.list_admins()
        for entry in entries:
            user = await self.users.get_by_telegram_id(entry.user_id)
            if user is not None:
                entry.username = user.username
        return entries

    async def current(self) -> BuyContact:
        """The contact the button opens right now (picked admin or the default)."""
        admin_id = await self.selected_admin_id()
        if admin_id is not None:
            for entry in await self.candidates():
                if entry.user_id == admin_id and entry.username:
                    return BuyContact(entry.username, admin_id)
        return BuyContact(default_username())

    async def url(self) -> str:
        return (await self.current()).url

    async def select(self, admin_id: int, *, changed_by: int) -> BuyContact:
        """Point the button at ``admin_id`` (an admin with a @username).

        Audited through the settings store; the caller commits.
        """
        for entry in await self.candidates():
            if entry.user_id != admin_id:
                continue
            if not entry.username:
                raise BuyContactError(
                    "این ادمین یوزرنیم تلگرام ندارد و لینک پیوی برایش ساخته نمی‌شود. "
                    "ابتدا یک یوزرنیم برای حسابش بگذارد و ربات را یک بار استارت کند."
                )
            await self.store.set(KEY_LISTING_BUY_ADMIN, str(admin_id), changed_by=changed_by)
            return BuyContact(entry.username, admin_id)
        raise BuyContactError("این کاربر دیگر ادمین نیست.")

    async def reset(self, *, changed_by: int) -> BuyContact:
        """Go back to the default username (audited; the caller commits)."""
        await self.store.set(KEY_LISTING_BUY_ADMIN, "", changed_by=changed_by)
        return BuyContact(default_username())
