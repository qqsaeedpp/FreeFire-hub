"""Clears a stale FSM state when the user taps a main-menu (reply) button or
sends a global navigation command (/start, /menu, /admin, /cancel).

Without this, a broad ``@router.message(SomeFlow.state, F.text)`` handler in an
earlier-included router swallows the input (e.g. tapping «کیف پول» — or sending
«/start» — while a half-finished «فروش اکانت» flow is still active would be
parsed as a price, replying «قیمت نامعتبر است»). Running before message-handler
resolution, this drops the leftover state so the input reaches its real handler.

Flow-internal commands such as «/done» are deliberately NOT reset, so an active
flow that expects them keeps working.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, TelegramObject

from app.keyboards.reply import BTN_MAIN, MAIN_MENU_TEXTS

# Global navigation commands that must always escape any in-progress flow.
_RESET_COMMANDS = {"/start", "/menu", "/admin", "/cancel"}


class MenuResetMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if isinstance(event, Message) and event.text:
            services = data.get("services")
            if services is not None:
                labels = await services.button.all_labels()
                menu_texts = set(labels.values()) | {BTN_MAIN}
            else:
                menu_texts = MAIN_MENU_TEXTS
            # First token, without any «@botname» suffix and deep-link args, so
            # «/start ref123» and «/start@MyBot» still count as «/start».
            command = event.text.split(maxsplit=1)[0].split("@", 1)[0].lower()
            if event.text in menu_texts or command in _RESET_COMMANDS:
                state: FSMContext | None = data.get("state")
                if state is not None and await state.get_state() is not None:
                    await state.clear()
        return await handler(event, data)
