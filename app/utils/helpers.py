"""Small reusable helpers."""
from __future__ import annotations

import secrets
import string

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import InlineKeyboardMarkup, Message


async def edit_or_answer(
    message: Message,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    """Edit the message in place (text or caption) instead of sending a new one.

    Keeps callback-driven navigation to a single, mutating message. Falls back to
    a fresh message only when the source can't be edited (e.g. media-only message
    or the «message is not modified» no-op).
    """
    try:
        if message.text is not None:
            await message.edit_text(text, reply_markup=reply_markup)
        elif message.caption is not None:
            await message.edit_caption(caption=text, reply_markup=reply_markup)
        else:
            await message.answer(text, reply_markup=reply_markup)
    except TelegramBadRequest:
        await message.answer(text, reply_markup=reply_markup)


def generate_referral_code(length: int = 8) -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


async def unique_referral_code(users_repo, length: int = 8) -> str:
    """Generate a referral code guaranteed unique against the users repository."""
    while True:
        code = generate_referral_code(length)
        if not await users_repo.get_by_referral_code(code):
            return code


def format_toman(amount: int) -> str:
    """Render an integer amount with thousands separators + Toman suffix."""
    return f"{amount:,} تومان"


def paginate_meta(total: int, page: int, page_size: int) -> tuple[int, int]:
    """Return (offset, total_pages) for 1-based page numbers."""
    total_pages = max(1, (total + page_size - 1) // page_size)
    page = max(1, min(page, total_pages))
    return (page - 1) * page_size, total_pages
