"""Small reusable helpers."""
from __future__ import annotations

import secrets
import string
from collections.abc import Sequence

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import InlineKeyboardMarkup, Message
from aiogram.utils.media_group import MediaGroupBuilder


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


def user_ref(user) -> str:
    """Render a user as ``<code>telegram_id</code> | @username`` for display.

    Falls back to «بدون یوزرنیم» when the user has no username and «?» when the
    user object itself is missing.
    """
    if user is None:
        return "?"
    handle = f"@{user.username}" if getattr(user, "username", None) else "بدون یوزرنیم"
    return f"<code>{user.telegram_id}</code> | {handle}"


def parse_images(csv: str | None) -> list[str]:
    """Split a stored CSV of file_ids back into an ordered, non-empty list."""
    if not csv:
        return []
    return [i for i in csv.split(",") if i]


async def send_album(
    bot: Bot,
    chat_id: int,
    file_ids: Sequence[str],
    *,
    caption: str | None = None,
) -> None:
    """Send photos as a single ordered media group (album).

    One photo → a normal photo with caption. Many → an album whose caption sits
    on the first image. Order is preserved and nothing is dropped. Media groups
    cannot carry inline keyboards, so callers send buttons in a follow-up message.
    """
    ids = [f for f in file_ids if f]
    if not ids:
        return
    if len(ids) == 1:
        await bot.send_photo(chat_id, ids[0], caption=caption)
        return
    builder = MediaGroupBuilder(caption=caption)
    for fid in ids:
        builder.add_photo(media=fid)
    await bot.send_media_group(chat_id, media=builder.build())


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
