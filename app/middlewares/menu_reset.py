"""Clears a stale FSM state when the user taps a main-menu (reply) button.

Without this, a broad ``@router.message(SomeFlow.state, F.text)`` handler in an
earlier-included router swallows the menu-button press (e.g. tapping «کیف پول»
while a half-finished «فروش اکانت» flow is still active would be parsed as a
price). Running before message-handler resolution, this drops the leftover
state so the press reaches its real handler.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, TelegramObject

from app.keyboards.reply import MAIN_MENU_TEXTS


class MenuResetMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if isinstance(event, Message) and event.text in MAIN_MENU_TEXTS:
            state: FSMContext | None = data.get("state")
            if state is not None and await state.get_state() is not None:
                await state.clear()
        return await handler(event, data)
