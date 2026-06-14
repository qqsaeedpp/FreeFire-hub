"""Admin: 💾 تنظیمات بکاپ — owner-only database backup configuration.

Owners pick where backups are delivered (a numeric user id or a private channel),
how often the automatic job runs (every 6h / 12h / daily / weekly), and can fire
a one-off backup on demand. The archive build + delivery run in the background
(:func:`app.scheduler.backup.run_backup`) so the bot is never blocked, and the
live APScheduler job is rescheduled in place whenever the cadence or enabled flag
changes (no restart needed).

Owner-only because a backup is a full export of every user / order / wallet —
consistent with «👮 مدیریت ادمین‌ها».
"""
from __future__ import annotations

import asyncio
import re

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.container import Services
from app.core.config import settings
from app.core.constants import (
    BACKUP_SCHEDULE_FA,
    BACKUP_TARGET_TYPE_FA,
    BackupScheduleType,
    BackupTargetType,
)
from app.filters.admin import IsAdmin
from app.keyboards.callbacks import AdminCB, BackupCB
from app.keyboards.inline import cancel_only
from app.scheduler.backup import run_backup
from app.states.admin_states import BackupTargetFlow
from app.utils.helpers import edit_or_answer

router = Router(name="admin_backup")

# Fire-and-forget tasks are kept referenced so the event loop can't GC them mid-run.
_BG_TASKS: set[asyncio.Task] = set()


def _spawn(coro) -> None:
    task = asyncio.create_task(coro)
    _BG_TASKS.add(task)
    task.add_done_callback(_BG_TASKS.discard)


def _require_owner(user_id: int) -> bool:
    return user_id in settings.admin_ids


def _parse_id(text: str) -> int | None:
    """Parse a Telegram id (Persian digits + a leading ``-`` for channels)."""
    translation = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")
    cleaned = re.sub(r"[,\s_]", "", text.translate(translation))
    neg = cleaned.startswith("-")
    digits = cleaned[1:] if neg else cleaned
    if not digits.isdigit():
        return None
    value = int(digits)
    return -value if neg else value


# --------------------------------- render ---------------------------------
def _status_text(setting) -> str:
    if setting.target_type and setting.target_id:
        target = (
            f"{BACKUP_TARGET_TYPE_FA[setting.target_type]}\n"
            f"🎯 مقصد: <code>{setting.target_id}</code>"
        )
    else:
        target = "⚠️ تنظیم نشده"
    schedule = BACKUP_SCHEDULE_FA[setting.schedule_type]
    enabled = "✅ فعال" if setting.is_enabled else "⛔️ غیرفعال"
    return (
        "💾 <b>تنظیمات بکاپ</b>\n\n"
        f"📤 مقصد ارسال:\n{target}\n\n"
        f"⏰ زمان‌بندی خودکار: {schedule}\n"
        f"🔁 بکاپ خودکار: {enabled}\n\n"
        "بکاپ شامل کل دیتابیس (کاربران، سفارش‌ها، کیف پول، تراکنش‌ها، "
        "زیرمجموعه‌ها، تنظیمات) به‌صورت یک فایل ZIP است."
    )


def _home_markup(setting) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📥 بکاپ دستی (ارسال فوری)", callback_data=BackupCB(action="manual"))
    kb.button(text="👤 مقصد: کاربر", callback_data=BackupCB(action="target_user"))
    kb.button(text="📢 مقصد: کانال", callback_data=BackupCB(action="target_channel"))
    kb.button(text="⏰ زمان‌بندی", callback_data=BackupCB(action="schedule"))
    toggle = "⛔️ غیرفعال‌سازی خودکار" if setting.is_enabled else "✅ فعال‌سازی خودکار"
    kb.button(text=toggle, callback_data=BackupCB(action="toggle"))
    kb.button(text="🔙 بازگشت", callback_data=AdminCB(action="back_home"))
    kb.adjust(1, 2, 1, 1, 1)
    return kb.as_markup()


def _schedule_markup(current: BackupScheduleType) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for st in BackupScheduleType:
        mark = "✅ " if st == current else ""
        kb.button(
            text=f"{mark}{BACKUP_SCHEDULE_FA[st]}",
            callback_data=BackupCB(action="set_schedule", value=st.value),
        )
    kb.button(text="🔙 بازگشت", callback_data=BackupCB(action="home"))
    kb.adjust(2, 2, 1)
    return kb.as_markup()


async def _show_home(message: Message, services: Services) -> None:
    setting = await services.backup.get()
    await edit_or_answer(message, _status_text(setting), reply_markup=_home_markup(setting))


# ---------------------------------- home ----------------------------------
@router.callback_query(AdminCB.filter(F.action == "backup"), IsAdmin())
async def backup_home(
    callback: CallbackQuery, services: Services, state: FSMContext
) -> None:
    if not _require_owner(callback.from_user.id):
        await callback.answer("فقط مالک ربات به این بخش دسترسی دارد.", show_alert=True)
        return
    await state.clear()
    await _show_home(callback.message, services)
    await callback.answer()


@router.callback_query(BackupCB.filter(F.action == "home"), IsAdmin())
async def backup_back_home(
    callback: CallbackQuery, services: Services, state: FSMContext
) -> None:
    if not _require_owner(callback.from_user.id):
        await callback.answer("فقط مالک ربات به این بخش دسترسی دارد.", show_alert=True)
        return
    await state.clear()
    await _show_home(callback.message, services)
    await callback.answer()


# ------------------------------ manual backup ------------------------------
@router.callback_query(BackupCB.filter(F.action == "manual"), IsAdmin())
async def backup_manual(callback: CallbackQuery, services: Services, bot) -> None:
    if not _require_owner(callback.from_user.id):
        await callback.answer("فقط مالک ربات به این بخش دسترسی دارد.", show_alert=True)
        return
    setting = await services.backup.get()
    if not (setting.target_type and setting.target_id):
        await callback.answer(
            "ابتدا مقصد ارسال بکاپ را تنظیم کنید.", show_alert=True
        )
        return
    # Run in the background so the dump/zip/send never blocks the event loop.
    _spawn(run_backup(bot))
    await callback.answer(
        "⏳ بکاپ شروع شد؛ پس از آماده‌سازی به مقصد ارسال می‌شود.", show_alert=True
    )


# ------------------------------- set target -------------------------------
@router.callback_query(BackupCB.filter(F.action == "target_user"), IsAdmin())
async def target_user_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not _require_owner(callback.from_user.id):
        await callback.answer("فقط مالک ربات به این بخش دسترسی دارد.", show_alert=True)
        return
    await state.set_state(BackupTargetFlow.entering_target_id)
    await state.update_data(target_kind="user")
    await edit_or_answer(
        callback.message,
        "👤 <b>مقصد: کاربر</b>\n\n"
        "آیدی عددی تلگرام مقصد را وارد کنید.\n"
        "⚠️ کاربر باید ربات را استارت کرده باشد.",
        reply_markup=cancel_only(),
    )
    await callback.answer()


@router.callback_query(BackupCB.filter(F.action == "target_channel"), IsAdmin())
async def target_channel_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not _require_owner(callback.from_user.id):
        await callback.answer("فقط مالک ربات به این بخش دسترسی دارد.", show_alert=True)
        return
    await state.set_state(BackupTargetFlow.entering_target_id)
    await state.update_data(target_kind="channel")
    await edit_or_answer(
        callback.message,
        "📢 <b>مقصد: کانال خصوصی</b>\n\n"
        "آیدی عددی کانال را وارد کنید. مثال:\n"
        "<code>-1001234567890</code>\n"
        "⚠️ ربات باید در کانال ادمین باشد.",
        reply_markup=cancel_only(),
    )
    await callback.answer()


@router.message(BackupTargetFlow.entering_target_id, F.text, IsAdmin())
async def target_save(
    message: Message, services: Services, state: FSMContext
) -> None:
    if not _require_owner(message.from_user.id):
        await state.clear()
        return
    data = await state.get_data()
    kind = data.get("target_kind", "user")
    target_id = _parse_id(message.text)
    if target_id is None:
        await message.answer("آیدی نامعتبر است. یک عدد معتبر وارد کنید.")
        return
    if kind == "user":
        if target_id <= 0:
            await message.answer("آیدی کاربر باید یک عدد مثبت باشد.")
            return
        target_type = BackupTargetType.USER
    else:
        if target_id >= 0:
            await message.answer(
                "آیدی کانال باید عددی منفی باشد (معمولاً با <code>-100</code> شروع می‌شود)."
            )
            return
        target_type = BackupTargetType.CHANNEL
    await services.backup.set_target(target_type, target_id)
    await services.commit()
    await state.clear()
    await message.answer("✅ مقصد بکاپ ذخیره شد.")
    await _show_home(message, services)


# -------------------------------- schedule --------------------------------
@router.callback_query(BackupCB.filter(F.action == "schedule"), IsAdmin())
async def schedule_view(callback: CallbackQuery, services: Services) -> None:
    if not _require_owner(callback.from_user.id):
        await callback.answer("فقط مالک ربات به این بخش دسترسی دارد.", show_alert=True)
        return
    setting = await services.backup.get()
    await edit_or_answer(
        callback.message,
        "⏰ <b>زمان‌بندی بکاپ خودکار</b>\n\n"
        "فاصله اجرای خودکار بکاپ را انتخاب کنید:",
        reply_markup=_schedule_markup(setting.schedule_type),
    )
    await callback.answer()


@router.callback_query(BackupCB.filter(F.action == "set_schedule"), IsAdmin())
async def schedule_set(
    callback: CallbackQuery, callback_data: BackupCB, services: Services, bot
) -> None:
    if not _require_owner(callback.from_user.id):
        await callback.answer("فقط مالک ربات به این بخش دسترسی دارد.", show_alert=True)
        return
    try:
        schedule_type = BackupScheduleType(callback_data.value)
    except ValueError:
        await callback.answer("مقدار نامعتبر.", show_alert=True)
        return
    setting = await services.backup.set_schedule(schedule_type)
    await services.commit()
    # Reapply the live job so the new cadence takes effect without a restart.
    services.backup.schedule_backup(setting.schedule_type, setting.is_enabled, bot)
    await callback.answer(f"زمان‌بندی: {BACKUP_SCHEDULE_FA[schedule_type]}")
    await _show_home(callback.message, services)


# --------------------------------- toggle ---------------------------------
@router.callback_query(BackupCB.filter(F.action == "toggle"), IsAdmin())
async def toggle_enabled(callback: CallbackQuery, services: Services, bot) -> None:
    if not _require_owner(callback.from_user.id):
        await callback.answer("فقط مالک ربات به این بخش دسترسی دارد.", show_alert=True)
        return
    setting = await services.backup.get()
    if not setting.is_enabled and not (setting.target_type and setting.target_id):
        await callback.answer(
            "ابتدا مقصد ارسال بکاپ را تنظیم کنید.", show_alert=True
        )
        return
    updated = await services.backup.set_enabled(not setting.is_enabled)
    await services.commit()
    services.backup.schedule_backup(updated.schedule_type, updated.is_enabled, bot)
    await callback.answer(
        "✅ بکاپ خودکار فعال شد." if updated.is_enabled else "⛔️ بکاپ خودکار غیرفعال شد."
    )
    await _show_home(callback.message, services)
