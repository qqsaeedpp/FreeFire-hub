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
    kb.button(
        text="🗑 حذف",
        callback_data=ChannelCB(action="confirm_delete", channel_id=channel.id),
    )
    kb.button(text="🔙 بازگشت", callback_data=ChannelCB(action="list"))
    kb.adjust(1)
    return kb.as_markup()


def _detail_text(channel: LockedChannel) -> str:
    status = "🟢 فعال" if channel.is_active else "🔴 غیرفعال"
    username = f"@{channel.username}" if channel.username else "-"
    link = channel.invite_link or "-"
    return (
        f"📢 <b>{channel.title}</b>\n\n"
        f"وضعیت: {status}\n"
        f"آیدی عددی: <code>{channel.chat_id}</code>\n"
        f"یوزرنیم: {username}\n"
        f"لینک عضویت: {link}"
    )


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
        "آیدی عددی، یوزرنیم (@channel) یا لینک کانال را ارسال کنید.\n\n"
        "⚠️ ربات باید قبلاً داخل کانال عضو/ادمین شده باشد.",
        reply_markup=cancel_only(),
    )
    await callback.answer()


@router.message(ChannelLockFlow.entering_channel, F.text, IsAdmin())
async def channel_add_save(
    message: Message, services: Services, state: FSMContext, bot
) -> None:
    try:
        channel = await services.channel.add_channel(bot, message.text)
    except ChannelAccessError as exc:
        await message.answer(f"❌ {exc}", reply_markup=cancel_only())
        return
    await services.commit()
    await state.clear()
    await message.answer(f"✅ کانال «{channel.title}» با موفقیت ثبت شد.")
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
