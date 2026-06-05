"""Middleware that opens a DB session + Services container per update.

It commits on success and rolls back on any exception, then injects the
``Services`` instance and the current ``User`` row into the handler data.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User as TgUser

from app.container import Services
from app.core.database import get_sessionmaker


class DatabaseMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        async with get_sessionmaker()() as session:
            services = Services(session)
            data["services"] = services

            tg_user: TgUser | None = data.get("event_from_user")
            if tg_user and not tg_user.is_bot:
                user, created = await services.user.get_or_create(
                    tg_user.id,
                    username=tg_user.username,
                    full_name=tg_user.full_name,
                )
                await session.flush()
                data["db_user"] = user
                data["db_user_created"] = created

            try:
                result = await handler(event, data)
                await session.commit()
                return result
            except Exception:
                await session.rollback()
                raise
