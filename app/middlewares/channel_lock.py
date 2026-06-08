"""Forced-membership gate.

Before any message/callback reaches a handler, verify the user is a member of
every *active* locked channel. Admins are exempt, and the «✅ عضو شدم» re-check
callback is always allowed through so a locked user can prove they joined.

If no active channels are configured the gate is transparent (everyone passes),
so the feature is opt-in and never blocks a bot that hasn't set it up.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject, Update
from aiogram.types import User as TgUser

from app.container import Services
from app.core.config import settings
from app.keyboards.callbacks import ChannelCB
from app.models.user import User

# Callback prefix that must always pass (the re-check button).
_CHECK_PREFIX = ChannelCB(action="check").pack()


class ChannelLockMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        inner = event.event if isinstance(event, Update) else event
        # Only gate direct user interactions.
        if not isinstance(inner, (Message, CallbackQuery)):
            return await handler(event, data)

        tg_user: TgUser | None = data.get("event_from_user")
        if tg_user is None or tg_user.is_bot:
            return await handler(event, data)

        # Admins are never locked.
        db_user: User | None = data.get("db_user")
        if tg_user.id in settings.admin_ids or bool(db_user and db_user.is_admin):
            return await handler(event, data)

        # Let the «عضو شدم» re-check callback through to its handler.
        if isinstance(inner, CallbackQuery) and (inner.data or "").startswith(
            _CHECK_PREFIX
        ):
            return await handler(event, data)

        services: Services | None = data.get("services")
        bot = data.get("bot")
        if services is None or bot is None:
            return await handler(event, data)

        if await services.channel.is_user_allowed(bot, tg_user.id):
            return await handler(event, data)

        # Blocked: show the lock message and stop processing this update.
        missing = await services.channel.get_missing_channels(bot, tg_user.id)
        text, markup = services.channel.build_lock_message(missing)
        if isinstance(inner, CallbackQuery):
            await inner.answer()
            if inner.message is not None:
                await inner.message.answer(text, reply_markup=markup)
        else:
            await inner.answer(text, reply_markup=markup)
        return None
