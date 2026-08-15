"""Admin: manage forced-membership («کانال قفل») channels.

Add / list / toggle / test-access / delete the channels a user must join before
using the bot. Adding a channel validates bot access first and refuses to save
an unusable one (see ``ChannelLockService.add_channel``).
"""
from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.container import Services
from app.filters.admin import IsAdmin
from app.keyboards.callbacks import AdminCB, ChannelCB
from app.keyboards.inline import cancel_only
from app.models.locked_channel import LockedChannel
from app.services.channel_lock_service import ChannelAccessError
from app.states.admin_states import ChannelLockFlow
from app.utils.helpers import edit_or_answer

router = Router(name="admin_channel_lock")


def _list_markup(channels: list[LockedChannel]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for ch in channels:
        mark = "🟢" if ch.is_active else "🔴"
        kb.button(
            text=f"{mark} {ch.title}",
            callback_data=ChannelCB(action="view", channel_id=ch.id),
        )
    kb.button(text="➕ افزودن کانال", callback_data=ChannelCB(action="add"))
    kb.button(text="🔙 بازگشت", callback_data=AdminCB(action="back_home"))
    kb.adjust(1)
    return kb.as_markup()


def _detail_markup(channel: LockedChannel) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    toggle_label = "🔴 غیرفعال کردن" if channel.is_active else "🟢 فعال کردن"
    kb.button(
        text=toggle_label,
        callback_data=ChannelCB(action="toggle", channel_id=channel.id),
    )
    kb.button(
        text="🧪 تست دسترسی ربات",
        callback_data=ChannelCB(action="test", channel_id=channel.id),
    )
    if not channel.username:
        # Private channels join via an invite link, which an admin can revoke in
        # the channel settings — this mints a working one again.
        kb.button(
            text="🔄 تازه‌سازی لینک عضویت",
            callback_data=ChannelCB(action="refresh", channel_id=channel.id),
        )
    kb.button(
        text="🗑 حذف",
        callback_data=ChannelCB(action="confirm_delete", channel_id=channel.id),
    )
    kb.button(text="🔙 بازگشت", callback_data=ChannelCB(action="list"))
    kb.adjust(1)
    return kb.as_markup()


def _detail_text(channel: LockedChannel) -> str:
    status = "🟢 فعال" if channel.is_active else "🔴 غیرفعال"
    kind = "🔓 عمومی" if channel.username else "🔒 خصوصی"
    username = f"@{channel.username}" if channel.username else "-"
    link = channel.invite_link or "❌ ندارد"
    text = (
        f"📢 <b>{channel.title}</b>\n\n"
        f"وضعیت: {status}\n"
        f"نوع کانال: {kind}\n"
        f"آیدی عددی: <code>{channel.chat_id}</code>\n"
        f"یوزرنیم: {username}\n"
        f"لینک عضویت: {link}"
    )
    if not channel.invite_link:
        text += (
            "\n\n⚠️ بدون لینک عضویت، کاربران نمی‌توانند عضو شوند. "
            "با دکمه «تازه‌سازی لینک عضویت» دوباره تلاش کنید."
        )
    return text


async def _show_list(services: Services, message: Message) -> None:
    channels = await services.channel.list_all()
    if channels:
        active = sum(1 for c in channels if c.is_active)
        text = (
            "🔒 <b>تنظیم کانال قفل</b>\n\n"
            f"تعداد کانال‌ها: {len(channels)} (فعال: {active})\n\n"
            "برای مدیریت هر کانال روی آن بزنید یا کانال جدید اضافه کنید.\n"
            "🟢 = فعال، 🔴 = غیرفعال"
        )
    else:
        text = (
            "🔒 <b>تنظیم کانال قفل</b>\n\n"
            "هیچ کانالی ثبت نشده است. با دکمه «➕ افزودن کانال» اولین کانال را "
            "اضافه کنید.\n\n"
            "⚠️ توجه: ربات باید داخل کانال عضو/ادمین باشد تا عضویت کاربران بررسی شود."
        )
    await edit_or_answer(message, text, reply_markup=_list_markup(channels))


# --------------------------------- list ---------------------------------
@router.callback_query(AdminCB.filter(F.action == "channel_lock"), IsAdmin())
async def channel_lock_home(
    callback: CallbackQuery, services: Services, state: FSMContext
) -> None:
    await state.clear()
    await _show_list(services, callback.message)
    await callback.answer()


@router.callback_query(ChannelCB.filter(F.action == "list"), IsAdmin())
async def channel_lock_list(
    callback: CallbackQuery, services: Services, state: FSMContext
) -> None:
    await state.clear()
    await _show_list(services, callback.message)
    await callback.answer()


# ---------------------------------- add ----------------------------------
@router.callback_query(ChannelCB.filter(F.action == "add"), IsAdmin())
async def channel_add_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ChannelLockFlow.entering_channel)
    await edit_or_answer(
        callback.message,
        "➕ <b>افزودن کانال قفل</b>\n\n"
        "🔓 <b>کانال عمومی:</b> یوزرنیم (@channel)، لینک یا آیدی عددی را بفرستید.\n\n"
        "🔒 <b>کانال خصوصی:</b> یک <b>پست از همان کانال</b> را به اینجا "
        "<b>فوروارد</b> کنید.\n"
        "(لینک دعوت <code>t.me/+...</code> کار نمی‌کند؛ تلگرام اجازه بررسی آن را نمی‌دهد.)\n\n"
        "⚠️ ربات باید در کانال <b>ادمین</b> باشد. برای کانال خصوصی، دسترسی "
        "«افزودن اعضا» هم لازم است تا ربات بتواند لینک عضویت بسازد.",
        reply_markup=cancel_only(),
    )
    await callback.answer()


def _forwarded_chat_id(message: Message) -> int | None:
    """Origin chat id of a forwarded channel post, or ``None``.

    Reads the modern ``forward_origin`` (Bot API 7+) and falls back to the legacy
    ``forward_from_chat`` field. Returns ``None`` when the origin is hidden — the
    channel forbids forwarding attribution — so the caller can explain the
    numeric-id alternative.
    """
    origin = message.forward_origin
    chat = getattr(origin, "chat", None) if origin is not None else None
    if chat is None:
        chat = message.forward_from_chat
    return chat.id if chat is not None else None


@router.message(ChannelLockFlow.entering_channel, IsAdmin())
async def channel_add_save(
    message: Message, services: Services, state: FSMContext, bot
) -> None:
    """Register a channel from a forwarded post (private) or typed id (public)."""
    forwarded_id = _forwarded_chat_id(message)
    try:
        if forwarded_id is not None:
            channel = await services.channel.add_channel_by_id(bot, forwarded_id)
        elif message.text:
            channel = await services.channel.add_channel(bot, message.text)
        else:
            await message.answer(
                "❌ ورودی نامعتبر است.\n\n"
                "یوزرنیم/لینک/آیدی عددی کانال را بفرستید، یا یک پست از کانال "
                "خصوصی را فوروارد کنید.\n"
                "اگر فوروارد کردید و این پیام را می‌بینید، کانال «فوروارد با ذکر "
                "منبع» را بسته است؛ در این حالت آیدی عددی کانال را بفرستید.",
                reply_markup=cancel_only(),
            )
            return
    except ChannelAccessError as exc:
        await message.answer(f"❌ {exc}", reply_markup=cancel_only())
        return
    await services.commit()
    await state.clear()
    kind = "عمومی" if channel.username else "خصوصی"
    await message.answer(
        f"✅ کانال «{channel.title}» ({kind}) با موفقیت ثبت شد."
    )
    await _show_list(services, message)


# --------------------------------- view ---------------------------------
@router.callback_query(ChannelCB.filter(F.action == "view"), IsAdmin())
async def channel_view(
    callback: CallbackQuery, callback_data: ChannelCB, services: Services
) -> None:
    channel = await services.channel.get(callback_data.channel_id)
    if channel is None:
        await callback.answer("کانال یافت نشد.", show_alert=True)
        await _show_list(services, callback.message)
        return
    await edit_or_answer(
        callback.message, _detail_text(channel), reply_markup=_detail_markup(channel)
    )
    await callback.answer()


# -------------------------------- toggle --------------------------------
@router.callback_query(ChannelCB.filter(F.action == "toggle"), IsAdmin())
async def channel_toggle(
    callback: CallbackQuery, callback_data: ChannelCB, services: Services
) -> None:
    channel = await services.channel.get(callback_data.channel_id)
    if channel is None:
        await callback.answer("کانال یافت نشد.", show_alert=True)
        return
    now_active = await services.channel.toggle_channel(channel)
    await services.commit()
    await callback.answer("فعال شد." if now_active else "غیرفعال شد.")
    await edit_or_answer(
        callback.message, _detail_text(channel), reply_markup=_detail_markup(channel)
    )


# --------------------------------- test ---------------------------------
@router.callback_query(ChannelCB.filter(F.action == "test"), IsAdmin())
async def channel_test(
    callback: CallbackQuery, callback_data: ChannelCB, services: Services, bot
) -> None:
    channel = await services.channel.get(callback_data.channel_id)
    if channel is None:
        await callback.answer("کانال یافت نشد.", show_alert=True)
        return
    ok = await services.channel.check_bot_access(bot, channel.chat_id)
    if ok:
        await callback.answer("✅ ربات به این کانال دسترسی دارد.", show_alert=True)
    else:
        await callback.answer(
            "❌ ربات داخل این کانال عضو/ادمین نیست. ابتدا ربات را در کانال ادمین کنید.",
            show_alert=True,
        )


# ----------------------------- refresh link -----------------------------
@router.callback_query(ChannelCB.filter(F.action == "refresh"), IsAdmin())
async def channel_refresh_link(
    callback: CallbackQuery, callback_data: ChannelCB, services: Services, bot
) -> None:
    """Mint a fresh invite link for a private channel and save it."""
    channel = await services.channel.get(callback_data.channel_id)
    if channel is None:
        await callback.answer("کانال یافت نشد.", show_alert=True)
        return
    link = await services.channel.refresh_invite_link(bot, channel)
    if link is None:
        await callback.answer(
            "❌ ساخت لینک ممکن نشد. ربات را در کانال ادمین کنید و دسترسی "
            "«افزودن اعضا» را به آن بدهید.",
            show_alert=True,
        )
        return
    await services.commit()
    await callback.answer("✅ لینک عضویت به‌روزرسانی شد.")
    await edit_or_answer(
        callback.message, _detail_text(channel), reply_markup=_detail_markup(channel)
    )


# -------------------------------- delete --------------------------------
@router.callback_query(ChannelCB.filter(F.action == "confirm_delete"), IsAdmin())
async def channel_confirm_delete(
    callback: CallbackQuery, callback_data: ChannelCB, services: Services
) -> None:
    channel = await services.channel.get(callback_data.channel_id)
    if channel is None:
        await callback.answer("کانال یافت نشد.", show_alert=True)
        return
    kb = InlineKeyboardBuilder()
    kb.button(
        text="✅ بله، حذف کن",
        callback_data=ChannelCB(action="delete", channel_id=channel.id),
    )
    kb.button(
        text="🔙 انصراف",
        callback_data=ChannelCB(action="view", channel_id=channel.id),
    )
    kb.adjust(1)
    await edit_or_answer(
        callback.message,
        f"⚠️ آیا از حذف کانال «{channel.title}» مطمئن هستید؟",
        reply_markup=kb.as_markup(),
    )
    await callback.answer()


@router.callback_query(ChannelCB.filter(F.action == "delete"), IsAdmin())
async def channel_delete(
    callback: CallbackQuery, callback_data: ChannelCB, services: Services
) -> None:
    channel = await services.channel.get(callback_data.channel_id)
    if channel is None:
        await callback.answer("کانال یافت نشد.", show_alert=True)
    else:
        await services.channel.remove_channel(channel)
        await services.commit()
        await callback.answer("کانال حذف شد.")
    await _show_list(services, callback.message)
