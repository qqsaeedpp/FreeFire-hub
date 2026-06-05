"""Anti-spam / rate-limiting middleware backed by Redis.

Allows at most one update per ``rate_limit_per_second`` window per user. Excess
updates are silently dropped (with a single warning to the user)."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject, Update

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
        # Registered on dp.update, so ``event`` is the Update wrapper; the actual
        # message/callback lives on ``Update.event``.
        inner = event.event if isinstance(event, Update) else event
        tg_user = data.get("event_from_user")

        # Inline-button callbacks must stay snappy: menu navigation fires several
        # callbacks in quick succession and throttling them makes buttons feel
        # dead. Telegram already rate-limits callbacks, so we don't.
        if tg_user is None or isinstance(inner, CallbackQuery):
            return await handler(event, data)

        key = f"throttle:{tg_user.id}"
        # SET NX with px = window; if it already exists -> throttled.
        allowed = await redis_client.set(
            key, "1", nx=True, px=int(self.window * 1000)
        )
        if allowed:
            return await handler(event, data)

        if isinstance(inner, Message):
            # only warn occasionally to avoid being part of the spam
            if await redis_client.set(
                f"throttle:warn:{tg_user.id}", "1", nx=True, ex=3
            ):
                await inner.answer("⏳ لطفاً کمی صبر کنید و دوباره تلاش کنید.")
        return None
