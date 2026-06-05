"""Filter that passes only for the configured admin(s)."""
from __future__ import annotations

from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, Message

from app.core.config import settings
from app.models.user import User


class IsAdmin(BaseFilter):
    async def __call__(
        self, event: Message | CallbackQuery, db_user: User | None = None
    ) -> bool:
        uid = event.from_user.id if event.from_user else None
        if uid == settings.admin_id:
            return True
        return bool(db_user and db_user.is_admin)
