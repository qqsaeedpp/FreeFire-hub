"""Blocks banned users from interacting with the bot.

The gate reads the ``User.is_banned`` fast-path flag (already loaded onto
``db_user`` by the DB middleware, so no extra query). Owners (env ``ADMIN_ID``)
and admins are exempt as defense-in-depth — :class:`~app.services.ban_service.BanService`
already refuses to ban them, so this only matters if a flag was set by hand.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject, Update

from app.core.config import settings
from app.models.user import User

_BAN_MESSAGE = (
    "🚫 حساب شما توسط مدیریت مسدود شده است.\n\n"
    "در صورت نیاز با مدیریت مجموعه تماس بگیرید."
)


class BanMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user: User | None = data.get("db_user")
        if not (user and user.is_banned):
            return await handler(event, data)

        # Owners/admins are never blocked (defensive — they can't be banned).
        if user.telegram_id in settings.admin_ids or user.is_admin:
            return await handler(event, data)

        inner = event.event if isinstance(event, Update) else event
        if isinstance(inner, CallbackQuery):
            await inner.answer(_BAN_MESSAGE, show_alert=True)
        elif isinstance(inner, Message):
            await inner.answer(_BAN_MESSAGE)
        return None
