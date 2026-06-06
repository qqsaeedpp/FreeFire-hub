"""Filter matching a main-menu reply button by its stable key.

The rendered label is DB-editable (see ButtonService), so handlers can't match
on a hardcoded string. ``MainBtn(key)`` resolves the live label for ``key`` from
the injected ``services`` and compares it to the incoming message text.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from aiogram.filters import BaseFilter
from aiogram.types import Message

from app.services.button_service import BUTTON_DEFAULTS

if TYPE_CHECKING:
    from app.container import Services


def _default_label(key: str) -> str:
    emoji, text = BUTTON_DEFAULTS.get(key, ("", ""))
    return f"{emoji} {text}".strip()


class MainBtn(BaseFilter):
    def __init__(self, key: str) -> None:
        self.key = key

    async def __call__(
        self, message: Message, services: "Services | None" = None
    ) -> bool:
        text = message.text
        if not text:
            return False
        if services is not None:
            return text == await services.button.label(self.key)
        # Fallback: compare against the hardcoded default label.
        return text == _default_label(self.key)
