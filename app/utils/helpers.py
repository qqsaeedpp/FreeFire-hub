"""Small reusable helpers."""
from __future__ import annotations

import secrets
import string
from collections.abc import Sequence

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import (
    InlineKeyboardMarkup,
    Message,
    MessageEntity,
    ReplyKeyboardMarkup,
)
from aiogram.utils.media_group import MediaGroupBuilder


def strip_custom_emoji(markup):
    """Return a copy of a keyboard markup with every button's premium emoji removed.

    ``icon_custom_emoji_id`` only renders when the bot is allowed to use custom
    emoji (owner has Telegram Premium / Fragment username). If it isn't, Telegram
    may reject the whole keyboard — this produces a safe fallback that keeps the
    button text/color but drops the premium icon, so the menu always shows.
    Works for both reply and inline keyboards; other markup types pass through.
    """
    if isinstance(markup, InlineKeyboardMarkup):
        rows = [
            [btn.model_copy(update={"icon_custom_emoji_id": None}) for btn in row]
            for row in markup.inline_keyboard
        ]
        return markup.model_copy(update={"inline_keyboard": rows})
    if isinstance(markup, ReplyKeyboardMarkup):
        rows = [
            [btn.model_copy(update={"icon_custom_emoji_id": None}) for btn in row]
            for row in markup.keyboard
        ]
        return markup.model_copy(update={"keyboard": rows})
    return markup


async def safe_answer(
    message: Message,
    text: str,
    reply_markup=None,
    **kwargs,
):
    """``message.answer`` that never crashes on an unavailable premium emoji.

    On :class:`TelegramBadRequest` it retries once with the premium emoji stripped
    from the keyboard (see :func:`strip_custom_emoji`), guaranteeing the menu is
    delivered even if the bot can't render the custom emoji.
    """
    try:
        return await message.answer(text, reply_markup=reply_markup, **kwargs)
    except TelegramBadRequest:
        if reply_markup is None:
            raise
        return await message.answer(
            text, reply_markup=strip_custom_emoji(reply_markup), **kwargs
        )


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


async def answer_managed(
    message: Message,
    rendered: tuple[str, list[MessageEntity] | None],
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    """Send a managed (admin-editable) text rendered by ``TextService.render``.

    When the text carries custom-emoji entities, send them verbatim with
    ``parse_mode=None`` (entities and HTML are mutually exclusive). Otherwise the
    default HTML parse mode applies, since the built-in defaults use HTML tags.
    """
    text, entities = rendered
    if entities:
        await message.answer(
            text, entities=entities, parse_mode=None, reply_markup=reply_markup
        )
    else:
        await message.answer(text, reply_markup=reply_markup)


def is_admin_user(message: Message, db_user) -> bool:
    """Whether the sender is an admin — true if their Telegram id is in the
    configured allowlist OR their DB record carries the admin flag. Used so the
    «پنل مدیریت» button never disappears for an admin, regardless of DB state.
    """
    from app.core.config import settings

    tg_id = message.from_user.id if message.from_user else None
    return (tg_id in settings.admin_ids) or bool(db_user and db_user.is_admin)


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
