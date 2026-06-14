"""Admin: 💾 مدیریت بکاپ — owner-only database backup & restore.

Owners can take a one-off backup on demand (delivered to the configured target
*and* to themselves at that moment), pick where automatic/manual backups are sent
(a numeric user id or a private channel — validated before saving), choose the
auto cadence (every 6h / 12h / daily / weekly) and toggle it, and **restore** the
database from an uploaded backup ZIP.

The archive build, delivery and restore all run in the background
(:func:`app.scheduler.backup.run_backup` / :func:`_do_restore`) so the bot is
never blocked, and the live APScheduler job is rescheduled in place whenever the
cadence or enabled flag changes (no restart needed).

Owner-only because a backup is a full export of every user / order / wallet, and a
restore overwrites the whole database — consistent with «👮 مدیریت ادمین‌ها».
"""
from __future__ import annotations

import asyncio
import re
from datetime import datetime
from pathlib import Path

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
from app.core.logger import get_logger
from app.filters.admin import IsAdmin
from app.keyboards.callbacks import AdminCB, BackupCB
from app.keyboards.inline import cancel_only
from app.scheduler.backup import run_backup
from app.services.backup_service import (
    BACKUP_DIR,
    MAX_RESTORE_BYTES,
    BackupError,
    BackupService,
)
from app.services.notification_service import NotificationService
from app.states.admin_states import BackupRestoreFlow, BackupTargetFlow
from app.utils.helpers import edit_or_answer

router = Router(name="admin_backup")
log = get_logger("backup")

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
        "💾 <b>مدیریت بکاپ</b>\n\n"
        f"📤 مقصد ارسال:\n{target}\n\n"
        f"⏰ زمان‌بندی خودکار: {schedule}\n"
        f"🔁 بکاپ خودکار: {enabled}\n\n"
        "بکاپ شامل کل دیتابیس (کاربران، سفارش‌ها، کیف پول، تراکنش‌ها، "
        "زیرمجموعه‌ها، تنظیمات) به‌صورت یک فایل ZIP است."
    )


def _home_markup() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📥 گرفتن بکاپ دستی", callback_data=BackupCB(action="manual"))
    kb.button(text="⚙️ تنظیم مقصد بکاپ", callback_data=BackupCB(action="target_menu"))
    kb.button(text="♻️ ریستور بکاپ", callback_data=BackupCB(action="restore"))
    kb.button(text="⏰ تنظیم بکاپ خودکار", callback_data=BackupCB(action="auto_menu"))
    kb.button(text="🔙 بازگشت", callback_data=AdminCB(action="back_home"))
    kb.adjust(1, 2, 1, 1)
    return kb.as_markup()


def _target_markup() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="👤 مقصد: کاربر", callback_data=BackupCB(action="target_user"))
    kb.button(text="📢 مقصد: کانال", callback_data=BackupCB(action="target_channel"))
    kb.button(text="🔙 بازگشت", callback_data=BackupCB(action="home"))
    kb.adjust(2, 1)
    return kb.as_markup()


def _auto_markup(setting) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for st in BackupScheduleType:
        mark = "✅ " if st == setting.schedule_type else ""
        kb.button(
            text=f"{mark}{BACKUP_SCHEDULE_FA[st]}",
            callback_data=BackupCB(action="set_schedule", value=st.value),
        )
    toggle = "⛔️ غیرفعال‌سازی خودکار" if setting.is_enabled else "✅ فعال‌سازی خودکار"
    kb.button(text=toggle, callback_data=BackupCB(action="toggle"))
    kb.button(text="🔙 بازگشت", callback_data=BackupCB(action="home"))
    kb.adjust(2, 2, 1, 1)
    return kb.as_markup()


def _restore_confirm_markup() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ تایید ریستور", callback_data=BackupCB(action="restore_confirm"))
    kb.button(text="❌ لغو", callback_data=BackupCB(action="restore_cancel"))
    kb.adjust(1)
    return kb.as_markup()


def _restore_info(metadata: dict) -> str:
    if metadata:
        info = "\n".join(
            [
                "📦 <b>اطلاعات بکاپ دریافتی</b>",
                f"🕒 زمان تهیه: {metadata.get('backup_time', '—')}",
                f"🤖 نسخه ربات: {metadata.get('bot_version', '—')}",
                f"🗄 دیتابیس: {metadata.get('database_name', '—')}",
                f"👥 کاربران: {metadata.get('users_count', '—')}",
                f"🧾 سفارش‌ها: {metadata.get('orders_count', '—')}",
            ]
        )
    else:
        info = "📦 فایل ZIP معتبر است (فاقد metadata.json)."
    return (
        f"{info}\n\n"
        "⚠️ <b>هشدار:</b> ریستور، دیتابیس فعلی را به‌طور کامل جایگزین می‌کند.\n"
        "ابتدا یک بکاپ اضطراری از وضعیت فعلی گرفته و برای شما ارسال می‌شود، "
        "سپس ریستور انجام می‌گردد.\n\n"
        "آیا از ادامه مطمئن هستید؟"
    )


async def _show_home(message: Message, services: Services) -> None:
    setting = await services.backup.get()
    await edit_or_answer(message, _status_text(setting), reply_markup=_home_markup())


async def _show_auto(message: Message, services: Services) -> None:
    setting = await services.backup.get()
    await edit_or_answer(
        message,
        "⏰ <b>بکاپ خودکار</b>\n\n"
        "فاصله اجرای خودکار را انتخاب کنید و وضعیت فعال/غیرفعال را تنظیم کنید:",
        reply_markup=_auto_markup(setting),
    )


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
async def backup_manual(callback: CallbackQuery, bot) -> None:
    if not _require_owner(callback.from_user.id):
        await callback.answer("فقط مالک ربات به این بخش دسترسی دارد.", show_alert=True)
        return
    # Run in the background so the dump/zip/send never blocks the event loop. The
    # requester always receives a copy, alongside the configured target (if any).
    _spawn(run_backup(bot, requester_id=callback.from_user.id))
    await callback.answer(
        "⏳ بکاپ شروع شد؛ پس از آماده‌سازی برای شما و مقصد تنظیم‌شده ارسال می‌شود.",
        show_alert=True,
    )


# ------------------------------- set target -------------------------------
@router.callback_query(BackupCB.filter(F.action == "target_menu"), IsAdmin())
async def target_menu(callback: CallbackQuery, state: FSMContext) -> None:
    if not _require_owner(callback.from_user.id):
        await callback.answer("فقط مالک ربات به این بخش دسترسی دارد.", show_alert=True)
        return
    await state.clear()
    await edit_or_answer(
        callback.message,
        "⚙️ <b>تنظیم مقصد بکاپ</b>\n\n"
        "بکاپ می‌تواند به یک کاربر (آیدی عددی) یا یک کانال خصوصی ارسال شود. "
        "مقصد را انتخاب کنید:",
        reply_markup=_target_markup(),
    )
    await callback.answer()


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
    message: Message, services: Services, state: FSMContext, bot
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

    # Verify the bot can actually deliver there *before* persisting the target.
    ok, info = await services.backup.validate_backup_target(bot, target_type, target_id)
    if not ok:
        await message.answer(f"❌ {info}\nمقصد ذخیره نشد؛ پس از رفع مشکل دوباره تلاش کنید.")
        return
    await services.backup.set_target(target_type, target_id)
    await services.commit()
    await state.clear()
    await message.answer(f"✅ مقصد بکاپ ذخیره شد.\n{info}")
    await _show_home(message, services)


# ------------------------------- auto backup ------------------------------
@router.callback_query(BackupCB.filter(F.action == "auto_menu"), IsAdmin())
async def auto_menu(callback: CallbackQuery, services: Services) -> None:
    if not _require_owner(callback.from_user.id):
        await callback.answer("فقط مالک ربات به این بخش دسترسی دارد.", show_alert=True)
        return
    await _show_auto(callback.message, services)
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
    await _show_auto(callback.message, services)


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
    await _show_auto(callback.message, services)


# --------------------------------- restore --------------------------------
@router.callback_query(BackupCB.filter(F.action == "restore"), IsAdmin())
async def restore_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not _require_owner(callback.from_user.id):
        await callback.answer(
            "فقط مالک ربات می‌تواند ریستور انجام دهد.", show_alert=True
        )
        return
    await state.set_state(BackupRestoreFlow.awaiting_file)
    await edit_or_answer(
        callback.message,
        "♻️ <b>ریستور بکاپ</b>\n\n"
        "⚠️ ریستور، دیتابیس فعلی را به‌طور کامل جایگزین می‌کند.\n"
        "پیش از اجرا، یک بکاپ اضطراری از وضعیت فعلی گرفته و برای شما ارسال می‌شود.\n\n"
        "📎 فایل ZIP بکاپ را همین‌جا به‌صورت «فایل» ارسال کنید (حداکثر ۲۰ مگابایت).",
        reply_markup=cancel_only(),
    )
    await callback.answer()


@router.message(BackupRestoreFlow.awaiting_file, F.document, IsAdmin())
async def restore_receive(message: Message, state: FSMContext, bot) -> None:
    if not _require_owner(message.from_user.id):
        await state.clear()
        return
    doc = message.document
    if doc.file_size and doc.file_size > MAX_RESTORE_BYTES:
        await message.answer(
            f"❌ حجم فایل ({doc.file_size // 1024 // 1024}MB) از حد مجاز دانلود ربات "
            "(۲۰ مگابایت) بیشتر است. برای فایل‌های بزرگ‌تر، ریستور را دستی روی سرور "
            "انجام دهید."
        )
        return
    BACKUP_DIR.mkdir(exist_ok=True)
    dest = BACKUP_DIR / f"restore_upload_{datetime.now():%Y%m%d_%H%M%S}.zip"
    try:
        await bot.download(doc, destination=dest)
    except Exception as exc:  # noqa: BLE001 - surface any download failure clearly
        await message.answer(f"❌ دانلود فایل ناموفق بود: <code>{exc}</code>")
        return
    backup = BackupService()
    try:
        metadata = backup.validate_zip(dest)
    except BackupError as exc:
        backup.cleanup_temp_files(dest)
        await message.answer(f"❌ {exc}")
        return
    await state.update_data(zip_path=str(dest), metadata=metadata)
    await state.set_state(BackupRestoreFlow.confirming)
    await message.answer(_restore_info(metadata), reply_markup=_restore_confirm_markup())


@router.message(BackupRestoreFlow.awaiting_file, IsAdmin())
async def restore_receive_other(message: Message) -> None:
    if not _require_owner(message.from_user.id):
        return
    await message.answer(
        "لطفاً فایل ZIP بکاپ را به‌صورت «فایل/سند» ارسال کنید (نه متن یا عکس)."
    )


@router.callback_query(
    BackupCB.filter(F.action == "restore_confirm"),
    BackupRestoreFlow.confirming,
    IsAdmin(),
)
async def restore_confirm(
    callback: CallbackQuery, state: FSMContext, bot
) -> None:
    if not _require_owner(callback.from_user.id):
        await callback.answer(
            "فقط مالک ربات می‌تواند ریستور انجام دهد.", show_alert=True
        )
        return
    data = await state.get_data()
    zip_str = data.get("zip_path")
    await state.clear()
    if not zip_str or not Path(zip_str).exists():
        await callback.answer(
            "فایل بکاپ یافت نشد؛ لطفاً دوباره ارسال کنید.", show_alert=True
        )
        return
    await edit_or_answer(
        callback.message,
        "⏳ در حال تهیه بکاپ اضطراری و سپس ریستور دیتابیس...\n"
        "نتیجه پس از اتمام برای شما ارسال می‌شود.",
    )
    _spawn(_do_restore(bot, callback.from_user.id, Path(zip_str)))
    await callback.answer("شروع شد.")


@router.callback_query(BackupCB.filter(F.action == "restore_cancel"), IsAdmin())
async def restore_cancel(
    callback: CallbackQuery, services: Services, state: FSMContext
) -> None:
    if not _require_owner(callback.from_user.id):
        await callback.answer("فقط مالک ربات به این بخش دسترسی دارد.", show_alert=True)
        return
    data = await state.get_data()
    zip_str = data.get("zip_path")
    if zip_str:
        BackupService.cleanup_temp_files(Path(zip_str))
    await state.clear()
    await _show_home(callback.message, services)
    await callback.answer("لغو شد.")


async def _do_restore(bot, owner_id: int, zip_path: Path) -> None:
    """Take an emergency backup, deliver it to owners, then restore the ZIP.

    Runs in the background. If the emergency backup can't be produced the restore
    is aborted (so a recoverable copy of the current data always exists first).
    The result is reported to the initiating owner.
    """
    backup = BackupService()
    notifier = NotificationService(bot)
    # 1) Emergency backup of the CURRENT database, before anything is overwritten.
    try:
        emergency = await backup.create_emergency_backup()
    except Exception as exc:  # noqa: BLE001 - never restore without a safety net
        backup.cleanup_temp_files(zip_path)
        await notifier.notify_user(
            owner_id,
            "🛑 ریستور لغو شد: تهیه بکاپ اضطراری از وضعیت فعلی ناموفق بود "
            "(برای جلوگیری از حذف داده‌ها).\n"
            f"<code>{exc}</code>",
        )
        log.warning("restore_aborted_no_emergency", error=str(exc))
        return
    try:
        for oid in settings.admin_ids:
            try:
                await backup.send_backup(
                    bot, emergency, oid, caption="🛟 بکاپ اضطراری پیش از ریستور"
                )
            except BackupError as exc:
                log.warning("emergency_send_failed", owner=oid, error=str(exc))
    finally:
        backup.cleanup_temp_files(emergency)

    # 2) Restore from the uploaded ZIP.
    try:
        metadata = await backup.restore_from_zip(zip_path)
        await notifier.notify_user(
            owner_id, "✅ ریستور با موفقیت انجام شد و دیتابیس بازگردانی شد."
        )
        await notifier.log_event(
            "ریستور دیتابیس انجام شد",
            {
                "نسخه بکاپ": metadata.get("bot_version", "—"),
                "زمان بکاپ": metadata.get("backup_time", "—"),
                "توسط": f"<code>{owner_id}</code>",
            },
        )
        log.info("restore_done", owner=owner_id)
    except BackupError as exc:
        await notifier.notify_user(
            owner_id,
            f"🛑 ریستور ناموفق بود:\n<code>{exc}</code>\n\n"
            "بکاپ اضطراری برای شما ارسال شده است؛ داده‌ها در امان هستند.",
        )
        log.warning("restore_failed", error=str(exc))
    except Exception as exc:  # noqa: BLE001 - a background job must never crash
        await notifier.notify_user(
            owner_id, f"🛑 خطای غیرمنتظره در ریستور:\n<code>{exc}</code>"
        )
        log.error("restore_unexpected_error", error=str(exc))
    finally:
        backup.cleanup_temp_files(zip_path)
