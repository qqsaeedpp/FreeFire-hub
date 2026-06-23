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
    *,
    entities: list[MessageEntity] | None = None,
) -> None:
    """Edit the message in place (text or caption) instead of sending a new one.

    Keeps callback-driven navigation to a single, mutating message. Falls back to
    a fresh message only when the source can't be edited (e.g. media-only message
    or the «message is not modified» no-op).

    When ``entities`` are supplied (premium-emoji text), they're sent verbatim with
    ``parse_mode=None`` — entities and HTML are mutually exclusive. Omitting them
    keeps the default HTML parse mode, so every existing caller is unaffected.
    """
    extra = {"entities": entities, "parse_mode": None} if entities else {}
    try:
        if message.text is not None:
            await message.edit_text(text, reply_markup=reply_markup, **extra)
        elif message.caption is not None:
            caption_extra = (
                {"caption_entities": entities, "parse_mode": None} if entities else {}
            )
            await message.edit_caption(
                caption=text, reply_markup=reply_markup, **caption_extra
            )
        else:
            await message.answer(text, reply_markup=reply_markup, **extra)
    except TelegramBadRequest:
        await message.answer(text, reply_markup=reply_markup, **extra)


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


def user_profile_link(telegram_id, name) -> str:
    """A tappable Telegram profile mention for *name* (HTML ``tg://user`` link).

    Uses the official ``tg://user?id=`` deep link so a user *without* a @username
    is still clickable — tapping the name opens their Telegram profile. Returns an
    empty string when *name* is blank. The name is HTML-escaped because messages
    render with HTML parse mode.
    """
    from html import escape

    safe = escape(str(name or "").strip())
    if not safe:
        return ""
    return f'<a href="tg://user?id={telegram_id}">{safe}</a>'


def format_user_display(user) -> str:
    """Render a user as ``<code>telegram_id</code> | <handle>`` for display.

    The single shared formatter used everywhere a user is shown (diamond/account
    orders, sell & requested accounts, wallet, referrals, admin notifications,
    pending/approved lists, the log channel, …):

    * has a @username        → ``<code>id</code> | @username`` (unchanged)
    * no username but a name  → ``<code>id</code> | <tappable name>`` — the name
      links to the user's profile via ``tg://user?id=`` so they're still reachable
    * neither                → ``<code>id</code> | بدون یوزرنیم``
    * missing user object     → ``?``

    Accepts any object exposing ``username``/``full_name`` plus either
    ``telegram_id`` or ``user_id`` (so a ban-entry row formats identically).
    """
    if user is None:
        return "?"
    tg_id = getattr(user, "telegram_id", None)
    if tg_id is None:
        tg_id = getattr(user, "user_id", None)
    if getattr(user, "username", None):
        handle = f"@{user.username}"
    else:
        handle = user_profile_link(tg_id, getattr(user, "full_name", None)) or "بدون یوزرنیم"
    return f"<code>{tg_id}</code> | {handle}"


# Backward-compatible alias: existing call sites import ``user_ref`` by name and
# now transparently get the richer (linked-name) rendering for usernameless users.
user_ref = format_user_display


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
    caption_entities: list[MessageEntity] | None = None,
) -> bool:
    """Send photos as a single ordered media group (album).

    One photo → a normal photo with caption. Many → an album whose caption sits
    on the first image. Order is preserved and nothing is dropped. Media groups
    cannot carry inline keyboards, so callers send buttons in a follow-up message.

    When ``caption_entities`` are supplied (premium-emoji caption), they ride along
    with ``parse_mode=None`` (entities and HTML are mutually exclusive); omitting
    them keeps the default HTML parse mode, so existing callers are unaffected.

    Returns ``True`` if the photos were sent, ``False`` if there were none to send
    or Telegram rejected them (e.g. a stale/invalid ``file_id``). A bad image must
    never break the surrounding flow, so callers can fall back to a text-only view.
    """
    ids = [f for f in file_ids if f]
    if not ids:
        return False
    extra = {"caption_entities": caption_entities, "parse_mode": None} if caption_entities else {}
    try:
        if len(ids) == 1:
            await bot.send_photo(chat_id, ids[0], caption=caption, **extra)
        else:
            builder = MediaGroupBuilder(caption=caption, caption_entities=caption_entities)
            for fid in ids:
                builder.add_photo(media=fid)
            await bot.send_media_group(chat_id, media=builder.build())
    except TelegramBadRequest:
        # Invalid/expired file identifier or HTTP URL — skip the gallery.
        return False
    return True


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


def fmt_dt(value) -> str:
    """Format a timestamp as ``YYYY-MM-DD - HH:MM``; tolerate missing values."""
    if value is None:
        return "-"
    try:
        return value.strftime("%Y-%m-%d - %H:%M")
    except Exception:  # noqa: BLE001 - unexpected type → fall back to str
        return str(value)


async def send_listing_card(bot, chat_id, *, caption, images, keyboard) -> None:
    """Send a sale-listing card *with its images* followed by the decision buttons.

    Telegram media groups can't carry an inline keyboard, so when there are images
    the gallery (album) is sent first with the full caption, then a short follow-up
    message carries the buttons. With no images (or a stale file_id), the caption
    and buttons are sent together as one text message. Used both for the instant
    admin notification and the in-panel review detail so they look identical.
    """
    if images and await send_album(bot, chat_id, images, caption=caption):
        await bot.send_message(
            chat_id, "👇 یک تصمیم برای این اکانت بگیرید:", reply_markup=keyboard
        )
    else:
        await bot.send_message(chat_id, caption, reply_markup=keyboard)


def sale_request_caption(account, seller) -> str:
    """Instant new-listing notification body (shared by card + list detail).

    Renders the «🔔 درخواست جدید فروش اکانت» layout. User-supplied text is HTML
    escaped because messages are sent with HTML parse mode.
    """
    from html import escape

    lines = [
        "🔔 <b>درخواست جدید فروش اکانت</b>",
        "",
        "👤 <b>کاربر:</b>",
        user_ref(seller),
        "",
        "💰 <b>قیمت پیشنهادی:</b>",
        format_toman(account.price),
        "",
        "📅 <b>زمان ثبت:</b>",
        fmt_dt(account.created_at),
    ]
    if account.description:
        lines += ["", f"📝 <b>توضیحات:</b> {escape(account.description)}"]
    return "\n".join(lines)


def _wallet_topup_core(req, user) -> list[str]:
    """Shared middle rows for the top-up notification + detail (so they never drift)."""
    from app.core.constants import PAYMENT_METHOD_FA

    method_fa = PAYMENT_METHOD_FA.get(req.payment_method, "-")
    return [
        f"🧾 شماره درخواست: #{req.id}",
        "👤 کاربر:",
        user_ref(user),
        f"💰 مبلغ شارژ: {format_toman(req.amount)}",
        f"💳 روش پرداخت: {method_fa}",
    ]


def wallet_topup_notify_text(req, user) -> str:
    """Instant «🔔 درخواست شارژ کیف پول جدید» card sent to admins (caption of the receipt)."""
    lines = ["🔔 <b>درخواست شارژ کیف پول جدید</b>", ""]
    lines += _wallet_topup_core(req, user)
    lines.append(f"📅 زمان ثبت: {fmt_dt(req.created_at)}")
    return "\n".join(lines)


def wallet_topup_detail_text(req, user) -> str:
    """Full in-panel detail for one top-up request (receipt is sent as a separate photo)."""
    from app.core.constants import WALLET_TOPUP_STATUS_FA

    lines = ["💰 <b>درخواست شارژ کیف پول</b>", ""]
    lines += _wallet_topup_core(req, user)
    receipt = "✅ ضمیمه شده (در پیام جدا)" if req.receipt_file_id else "—"
    lines += [
        f"📷 رسید پرداخت: {receipt}",
        f"📅 زمان ثبت: {fmt_dt(req.created_at)}",
        f"📊 وضعیت: {WALLET_TOPUP_STATUS_FA.get(req.status, req.status)}",
    ]
    return "\n".join(lines)
