"""Anti-spam / rate-limiting middleware backed by Redis.

Allows at most one update per ``rate_limit_per_second`` window per user. Excess
updates are silently dropped (with a single warning to the user)."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from app.core.config import settings
from app.core.redis import redis_client


class ThrottlingMiddleware(BaseMiddleware):
    def __init__(self, rate: float | None = None) -> None:
        self.window = 1.0 / (rate or settings.rate_limit_per_second)

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user = data.get("event_from_user")
        if tg_user is None:
            return await handler(event, data)

        key = f"throttle:{tg_user.id}"
        # SET NX with px = window; if it already exists -> throttled.
        allowed = await redis_client.set(
            key, "1", nx=True, px=int(self.window * 1000)
        )
        if allowed:
            return await handler(event, data)

        if isinstance(event, CallbackQuery):
            await event.answer("لطفاً کمی آرام‌تر! 🐢", show_alert=False)
        elif isinstance(event, Message):
            # only warn occasionally to avoid being part of the spam
            if await redis_client.set(
                f"throttle:warn:{tg_user.id}", "1", nx=True, ex=3
            ):
                await event.answer("⏳ لطفاً کمی صبر کنید و دوباره تلاش کنید.")
        return None
