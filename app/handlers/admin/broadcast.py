"""Admin broadcast — send a text, photo, or photo+caption message to all users.

The original text-only flow is preserved; photo and photo+caption are *added*
on top. A type chooser splits the three modes, each ending at the same preview →
confirm step. The actual send runs as a detached background task (so a large
broadcast never blocks the bot) and reports success/failure totals when done.
Photos are forwarded by their Telegram ``file_id`` — never re-downloaded.
"""
from __future__ import annotations

import asyncio

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.core.database import get_sessionmaker
from app.core.logger import get_logger
from app.filters.admin import IsAdmin
from app.keyboards.callbacks import AdminCB
from app.keyboards.inline import cancel_only
from app.states.admin_states import BroadcastFlow
from app.utils.helpers import edit_or_answer

router = Router(name="admin_broadcast")
log = get_logger("admin.broadcast")

# Telegram hard limit for a photo caption (text messages allow 4096).
_CAPTION_LIMIT = 1024
# How many recipients are pulled from the DB per page when snapshotting ids.
_FETCH_PAGE = 500
# Pause between sends to respect Telegram flood limits.
_SEND_DELAY = 0.05

# Detached send tasks are kept referenced so the event loop can't garbage-collect
# them mid-broadcast (same pattern as the backup handler).
_BG_TASKS: set[asyncio.Task] = set()


def _spawn(coro) -> None:
    task = asyncio.create_task(coro)
    _BG_TASKS.add(task)
    task.add_done_callback(_BG_TASKS.discard)


def _type_menu():
    kb = InlineKeyboardBuilder()
    kb.button(text="📝 متن", callback_data=AdminCB(action="broadcast_text"))
    kb.button(text="🖼 عکس", callback_data=AdminCB(action="broadcast_photo"))
    kb.button(text="🖼📝 عکس همراه متن", callback_data=AdminCB(action="broadcast_phototext"))
    kb.button(text="❌ لغو", callback_data=AdminCB(action="broadcast_cancel"))
    kb.adjust(1)
    return kb.as_markup()


def _confirm_menu():
    kb = InlineKeyboardBuilder()
    kb.button(
        text="✅ ارسال به همه کاربران",
        callback_data=AdminCB(action="broadcast_confirm"),
    )
    kb.button(text="❌ لغو", callback_data=AdminCB(action="broadcast_cancel"))
    kb.adjust(1)
    return kb.as_markup()


# --------------------------------- entry ---------------------------------
@router.callback_query(AdminCB.filter(F.action == "broadcast"), IsAdmin())
async def broadcast_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(BroadcastFlow.choosing_type)
    await state.update_data(mode=None, text=None, photo=None)
    await edit_or_answer(
        callback.message,
        "📣 <b>پیام همگانی</b>\nنوع پیام را انتخاب کنید:",
        reply_markup=_type_menu(),
    )
    await callback.answer()


# ----------------------------- type selection -----------------------------
@router.callback_query(AdminCB.filter(F.action == "broadcast_text"), IsAdmin())
async def broadcast_pick_text(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(mode="text")
    await state.set_state(BroadcastFlow.entering_message)
    await edit_or_answer(
        callback.message, "📝 متن پیام همگانی را ارسال کنید:", reply_markup=cancel_only()
    )
    await callback.answer()


@router.callback_query(AdminCB.filter(F.action == "broadcast_photo"), IsAdmin())
async def broadcast_pick_photo(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(mode="photo")
    await state.set_state(BroadcastFlow.entering_photo)
    await edit_or_answer(
        callback.message, "🖼 عکس پیام همگانی را ارسال کنید:", reply_markup=cancel_only()
    )
    await callback.answer()


@router.callback_query(AdminCB.filter(F.action == "broadcast_phototext"), IsAdmin())
async def broadcast_pick_phototext(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(mode="photo_text")
    await state.set_state(BroadcastFlow.entering_photo)
    await edit_or_answer(
        callback.message,
        "🖼 ابتدا عکس را ارسال کنید (سپس متن آن را وارد می‌کنید):",
        reply_markup=cancel_only(),
    )
    await callback.answer()


# ------------------------------- photo step -------------------------------
@router.message(BroadcastFlow.entering_photo, F.photo, IsAdmin())
async def broadcast_photo_received(message: Message, state: FSMContext) -> None:
    # Store the largest rendition's file_id; it's reused verbatim on send so
    # Telegram never re-downloads / re-uploads the image.
    await state.update_data(photo=message.photo[-1].file_id)
    data = await state.get_data()
    if data.get("mode") == "photo_text":
        await state.set_state(BroadcastFlow.entering_message)
        await message.answer("📝 حالا متن (کپشن) عکس را وارد کنید:", reply_markup=cancel_only())
    else:
        await _show_preview(message, state)


@router.message(BroadcastFlow.entering_photo, IsAdmin())
async def broadcast_photo_invalid(message: Message) -> None:
    await message.answer("لطفاً یک «عکس» ارسال کنید (یا روی «❌ لغو» بزنید).")


# -------------------------------- text step --------------------------------
@router.message(BroadcastFlow.entering_message, F.text, IsAdmin())
async def broadcast_text_received(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    text = message.html_text
    if data.get("mode") == "photo_text" and len(text) > _CAPTION_LIMIT:
        await message.answer(
            f"❌ متن کپشن عکس نباید بیش از {_CAPTION_LIMIT} کاراکتر باشد "
            f"(اکنون {len(text)}). متن کوتاه‌تری ارسال کنید:"
        )
        return
    await state.update_data(text=text)
    await _show_preview(message, state)


@router.message(BroadcastFlow.entering_message, IsAdmin())
async def broadcast_text_invalid(message: Message) -> None:
    await message.answer("لطفاً «متن» پیام را ارسال کنید (یا روی «❌ لغو» بزنید).")


async def _show_preview(message: Message, state: FSMContext) -> None:
    """Show the message exactly as users will receive it, then ask to confirm."""
    data = await state.get_data()
    await state.set_state(BroadcastFlow.confirming)
    text = data.get("text")
    photo = data.get("photo")
    if photo:
        # Preview the real photo+caption, then a separate confirm prompt (a long
        # caption can't also carry a preview label without risking the limit).
        await message.answer_photo(photo, caption=text or None)
        await message.answer(
            "🔎 پیش‌نمایش بالا نمایش داده شد.\nبه همه کاربران ارسال شود؟",
            reply_markup=_confirm_menu(),
        )
    else:
        await message.answer(
            f"🔎 <b>پیش‌نمایش پیام همگانی</b>\n\n{text}\n\nبه همه کاربران ارسال شود؟",
            reply_markup=_confirm_menu(),
        )


# ------------------------------ cancel / send ------------------------------
@router.callback_query(AdminCB.filter(F.action == "broadcast_cancel"), IsAdmin())
async def broadcast_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await edit_or_answer(callback.message, "پیام همگانی لغو شد.")
    await callback.answer()


@router.callback_query(
    BroadcastFlow.confirming, AdminCB.filter(F.action == "broadcast_confirm"), IsAdmin()
)
async def broadcast_send(callback: CallbackQuery, state: FSMContext, bot) -> None:
    data = await state.get_data()
    await state.clear()  # clearing first guards against a double-tap re-send
    mode = data.get("mode") or "text"
    text = data.get("text")
    photo = data.get("photo")
    if not photo and not text:
        await callback.answer("محتوایی برای ارسال وجود ندارد.", show_alert=True)
        return
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:  # noqa: BLE001 - keyboard may already be gone
        pass
    await callback.message.answer(
        "⏳ در حال ارسال پیام همگانی...\nگزارش نهایی پس از پایان ارسال می‌شود."
    )
    await callback.answer()
    # Detached: the bot stays responsive while the (possibly long) send drains.
    _spawn(_run_broadcast(bot, callback.message.chat.id, mode, text, photo))


async def _collect_recipient_ids() -> list[int]:
    """Snapshot every user's telegram id, then release the DB session.

    Runs in its own short-lived session so the long send loop afterwards never
    holds a database connection open (the loop touches Telegram only).
    """
    ids: list[int] = []
    from app.container import Services  # local import keeps the import graph acyclic

    async with get_sessionmaker()() as session:
        services = Services(session)
        offset = 0
        while True:
            batch = await services.users.list(offset=offset, limit=_FETCH_PAGE)
            if not batch:
                break
            ids.extend(u.telegram_id for u in batch)
            offset += _FETCH_PAGE
    return ids


async def _run_broadcast(
    bot, report_chat_id: int, mode: str, text: str | None, photo: str | None
) -> None:
    """Deliver the broadcast to every user, counting successes and failures.

    A per-user failure (blocked bot, deactivated account, stale id) is logged and
    skipped so one bad recipient never halts the run. The admin who started the
    broadcast receives a final report with the totals.
    """
    try:
        recipient_ids = await _collect_recipient_ids()
    except Exception as exc:  # noqa: BLE001 - DB hiccup must not crash the task
        log.error("broadcast_user_fetch_failed", error=str(exc))
        await _safe_send(bot, report_chat_id, f"🛑 خطا در دریافت لیست کاربران:\n{exc}")
        return

    sent = 0
    failed = 0
    for tg_id in recipient_ids:
        try:
            if photo:
                await bot.send_photo(tg_id, photo, caption=text or None)
            else:
                await bot.send_message(tg_id, text)
            sent += 1
        except Exception as exc:  # noqa: BLE001 - skip & log, keep broadcasting
            failed += 1
            log.warning("broadcast_user_failed", user=tg_id, error=str(exc))
        await asyncio.sleep(_SEND_DELAY)

    total = sent + failed
    await _safe_send(
        bot,
        report_chat_id,
        "📊 <b>گزارش ارسال</b>\n\n"
        f"✅ موفق: {sent}\n"
        f"❌ ناموفق: {failed}\n"
        f"👥 کل: {total}",
    )
    log.info("broadcast_done", mode=mode, sent=sent, failed=failed, total=total)


async def _safe_send(bot, chat_id: int, text: str) -> None:
    try:
        await bot.send_message(chat_id, text)
    except Exception as exc:  # noqa: BLE001 - never let the report crash the task
        log.warning("broadcast_report_failed", error=str(exc))
