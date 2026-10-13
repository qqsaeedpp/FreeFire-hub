"""Admin: manage advertising channels («کانال‌های تبلیغ»).

Add / list / toggle / test / delete the channels every new-listing announcement
is mirrored into (see ``account_form._post_new_listing_to_channels``). Adding a
channel checks that the bot can post there first and refuses to save an unusable
one (see ``AdChannelService.add_channel``).
"""
from __future__ import annotations

from html import escape

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.container import Services
from app.filters.admin import IsAdmin
from app.handlers.admin.channel_lock import _forwarded_chat_id
from app.keyboards.callbacks import AdChannelCB, AdminCB
from app.keyboards.inline import cancel_only
from app.models.ad_channel import AdChannel
from app.services.channel_lock_service import ChannelAccessError
from app.states.admin_states import AdChannelFlow
from app.utils.helpers import edit_or_answer

router = Router(name="admin_ad_channels")

_ABOUT = (
    "هر آگهی «اکانت جدید برای فروش» که ثبت کنید، درجا در همهٔ کانال‌های فعال "
    "این لیست هم منتشر می‌شود."
)
_NEEDS_ADMIN = "⚠️ ربات باید در کانال ادمین باشد و اجازهٔ «ارسال پیام» داشته باشد."


def _list_markup(channels: list[AdChannel]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for ch in channels:
        mark = "🟢" if ch.is_active else "🔴"
        kb.button(
            text=f"{mark} {ch.title}",
            callback_data=AdChannelCB(action="view", channel_id=ch.id),
        )
    kb.button(text="➕ افزودن کانال", callback_data=AdChannelCB(action="add"))
    kb.button(text="🔙 بازگشت", callback_data=AdminCB(action="channels"))
    kb.adjust(1)
    return kb.as_markup()


def _detail_markup(channel: AdChannel) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    toggle_label = "🔴 غیرفعال کردن" if channel.is_active else "🟢 فعال کردن"
    kb.button(
        text=toggle_label,
        callback_data=AdChannelCB(action="toggle", channel_id=channel.id),
    )
    kb.button(
        text="🧪 تست دسترسی ربات",
        callback_data=AdChannelCB(action="test", channel_id=channel.id),
    )
    kb.button(
        text="🗑 حذف",
        callback_data=AdChannelCB(action="confirm_delete", channel_id=channel.id),
    )
    kb.button(text="🔙 بازگشت", callback_data=AdChannelCB(action="list"))
    kb.adjust(1)
    return kb.as_markup()


def _detail_text(channel: AdChannel) -> str:
    status = (
        "🟢 فعال — آگهی‌های جدید در این کانال منتشر می‌شوند"
        if channel.is_active
        else "🔴 غیرفعال — آگهی‌ای در این کانال منتشر نمی‌شود"
    )
    username = f"@{escape(channel.username)}" if channel.username else "-"
    return (
        f"📣 <b>{escape(channel.title)}</b>\n\n"
        f"وضعیت: {status}\n"
        f"آیدی عددی: <code>{channel.chat_id}</code>\n"
        f"یوزرنیم: {username}"
    )


async def _show_list(services: Services, message: Message, bot) -> None:
    # The channel carried over from the old LISTING_CHANNEL_ID setting starts
    # with its chat id as the title; swap in the real name once reachable.
    if await services.ad_channel.resolve_placeholder_titles(bot):
        await services.commit()
    channels = await services.ad_channel.list_all()
    if channels:
        active = sum(1 for c in channels if c.is_active)
        text = (
            "📣 <b>کانال‌های تبلیغ</b>\n\n"
            f"{_ABOUT}\n\n"
            f"تعداد کانال‌ها: {len(channels)} (فعال: {active})\n\n"
            "برای مدیریت هر کانال روی آن بزنید یا کانال جدید اضافه کنید.\n"
            "🟢 = فعال، 🔴 = غیرفعال"
        )
    else:
        text = (
            "📣 <b>کانال‌های تبلیغ</b>\n\n"
            "هیچ کانالی ثبت نشده است. با دکمه «➕ افزودن کانال» اولین کانال را "
            "اضافه کنید.\n\n"
            f"{_ABOUT}\n\n"
            f"{_NEEDS_ADMIN}"
        )
    await edit_or_answer(message, text, reply_markup=_list_markup(channels))


# --------------------------------- list ---------------------------------
@router.callback_query(AdminCB.filter(F.action == "ad_channels"), IsAdmin())
async def ad_channels_home(
    callback: CallbackQuery, services: Services, state: FSMContext, bot
) -> None:
    await state.clear()
    await _show_list(services, callback.message, bot)
    await callback.answer()


@router.callback_query(AdChannelCB.filter(F.action == "list"), IsAdmin())
async def ad_channel_list(
    callback: CallbackQuery, services: Services, state: FSMContext, bot
) -> None:
    await state.clear()
    await _show_list(services, callback.message, bot)
    await callback.answer()


# ---------------------------------- add ----------------------------------
@router.callback_query(AdChannelCB.filter(F.action == "add"), IsAdmin())
async def ad_channel_add_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdChannelFlow.entering_channel)
    await edit_or_answer(
        callback.message,
        "➕ <b>افزودن کانال تبلیغ</b>\n\n"
        "🔓 <b>کانال عمومی:</b> یوزرنیم (@channel)، لینک یا آیدی عددی را بفرستید.\n\n"
        "🔒 <b>کانال خصوصی:</b> یک <b>پست از همان کانال</b> را به اینجا "
        "<b>فوروارد</b> کنید یا آیدی عددی آن را بفرستید.\n\n"
        "⚠️ ربات باید در کانال <b>ادمین</b> باشد و دسترسی «<b>ارسال پیام</b>» "
        "داشته باشد.",
        reply_markup=cancel_only(),
    )
    await callback.answer()


@router.message(AdChannelFlow.entering_channel, IsAdmin())
async def ad_channel_add_save(
    message: Message, services: Services, state: FSMContext, bot
) -> None:
    """Register a channel from a forwarded post (private) or typed id (public)."""
    forwarded_id = _forwarded_chat_id(message)
    try:
        if forwarded_id is not None:
            channel = await services.ad_channel.add_channel_by_id(bot, forwarded_id)
        elif message.text:
            channel = await services.ad_channel.add_channel(bot, message.text)
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
    await message.answer(
        f"✅ کانال «{escape(channel.title)}» به کانال‌های تبلیغ اضافه شد.\n"
        "از این پس هر آگهی جدید در این کانال هم منتشر می‌شود."
    )
    await _show_list(services, message, bot)


# --------------------------------- view ---------------------------------
@router.callback_query(AdChannelCB.filter(F.action == "view"), IsAdmin())
async def ad_channel_view(
    callback: CallbackQuery, callback_data: AdChannelCB, services: Services, bot
) -> None:
    channel = await services.ad_channel.get(callback_data.channel_id)
    if channel is None:
        await callback.answer("کانال یافت نشد.", show_alert=True)
        await _show_list(services, callback.message, bot)
        return
    await edit_or_answer(
        callback.message, _detail_text(channel), reply_markup=_detail_markup(channel)
    )
    await callback.answer()


# -------------------------------- toggle --------------------------------
@router.callback_query(AdChannelCB.filter(F.action == "toggle"), IsAdmin())
async def ad_channel_toggle(
    callback: CallbackQuery, callback_data: AdChannelCB, services: Services
) -> None:
    channel = await services.ad_channel.get(callback_data.channel_id)
    if channel is None:
        await callback.answer("کانال یافت نشد.", show_alert=True)
        return
    now_active = await services.ad_channel.toggle_channel(channel)
    await services.commit()
    await callback.answer("فعال شد." if now_active else "غیرفعال شد.")
    await edit_or_answer(
        callback.message, _detail_text(channel), reply_markup=_detail_markup(channel)
    )


# --------------------------------- test ---------------------------------
@router.callback_query(AdChannelCB.filter(F.action == "test"), IsAdmin())
async def ad_channel_test(
    callback: CallbackQuery, callback_data: AdChannelCB, services: Services, bot
) -> None:
    channel = await services.ad_channel.get(callback_data.channel_id)
    if channel is None:
        await callback.answer("کانال یافت نشد.", show_alert=True)
        return
    ok = await services.ad_channel.check_and_refresh(bot, channel)
    await services.commit()
    if ok:
        await callback.answer(
            "✅ ربات اجازهٔ ارسال پیام در این کانال را دارد.", show_alert=True
        )
    else:
        await callback.answer(
            "❌ ربات نمی‌تواند در این کانال پیام بفرستد. ربات را در کانال ادمین "
            "کنید و دسترسی «ارسال پیام» را به آن بدهید.",
            show_alert=True,
        )
    await edit_or_answer(
        callback.message, _detail_text(channel), reply_markup=_detail_markup(channel)
    )


# -------------------------------- delete --------------------------------
@router.callback_query(AdChannelCB.filter(F.action == "confirm_delete"), IsAdmin())
async def ad_channel_confirm_delete(
    callback: CallbackQuery, callback_data: AdChannelCB, services: Services
) -> None:
    channel = await services.ad_channel.get(callback_data.channel_id)
    if channel is None:
        await callback.answer("کانال یافت نشد.", show_alert=True)
        return
    kb = InlineKeyboardBuilder()
    kb.button(
        text="✅ بله، حذف کن",
        callback_data=AdChannelCB(action="delete", channel_id=channel.id),
    )
    kb.button(
        text="🔙 انصراف",
        callback_data=AdChannelCB(action="view", channel_id=channel.id),
    )
    kb.adjust(1)
    await edit_or_answer(
        callback.message,
        f"⚠️ آیا از حذف کانال «{escape(channel.title)}» از کانال‌های تبلیغ "
        "مطمئن هستید؟\nپس از حذف، آگهی‌های جدید در این کانال منتشر نمی‌شوند.",
        reply_markup=kb.as_markup(),
    )
    await callback.answer()


@router.callback_query(AdChannelCB.filter(F.action == "delete"), IsAdmin())
async def ad_channel_delete(
    callback: CallbackQuery, callback_data: AdChannelCB, services: Services, bot
) -> None:
    channel = await services.ad_channel.get(callback_data.channel_id)
    if channel is None:
        await callback.answer("کانال یافت نشد.", show_alert=True)
    else:
        await services.ad_channel.remove_channel(channel)
        await services.commit()
        await callback.answer("کانال حذف شد.")
    await _show_list(services, callback.message, bot)
