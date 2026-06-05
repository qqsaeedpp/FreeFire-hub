"""Blocks banned users from interacting with the bot."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject, Update

from app.models.user import User


class BanMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user: User | None = data.get("db_user")
        if user and user.is_banned:
            text = "⛔️ دسترسی شما به ربات مسدود شده است."
            inner = event.event if isinstance(event, Update) else event
            if isinstance(inner, CallbackQuery):
                await inner.answer(text, show_alert=True)
            elif isinstance(inner, Message):
                await inner.answer(text)
            return None
        return await handler(event, data)
