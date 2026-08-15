"""Restrict the bot to private chats.

This is a storefront bot: every flow (orders, wallet, onboarding, admin panel)
belongs in a one-to-one chat, and it never needs to read or answer anything in a
group, supergroup or channel.

Without this gate the bot talks in groups uninvited — the channel-lock and
verification gates reply to *any* message they see, so a member who simply chats
in a group the bot was added to gets the «join our channels» or «send your phone
number» prompt posted publicly. Dropping non-private updates at the very top of
the chain also stops the database middleware from creating a ``User`` row for
every stranger who happens to speak in such a group.

Registered as the FIRST update middleware so nothing downstream — throttling,
database, ban, channel lock, verification, handlers — ever observes the update.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.enums import ChatType
from aiogram.types import TelegramObject


class PrivateOnlyMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        # ``event_chat`` is resolved by aiogram's built-in UserContextMiddleware,
        # which runs before any user-registered middleware, and covers every
        # chat-bound update type (message, callback, chat member, …).
        chat = data.get("event_chat")
        if chat is not None and chat.type != ChatType.PRIVATE:
            # Silently ignore: no reply, no callback answer, no reaction — the
            # bot should be invisible outside private chats.
            return None
        return await handler(event, data)
