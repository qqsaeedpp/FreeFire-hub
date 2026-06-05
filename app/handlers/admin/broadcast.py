"""Admin broadcast — send a message to all users."""
from __future__ import annotations

import asyncio

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.container import Services
from app.core.logger import get_logger
from app.filters.admin import IsAdmin
from app.keyboards.callbacks import AdminCB
from app.keyboards.inline import cancel_only
from app.states.admin_states import BroadcastFlow
from app.utils.helpers import edit_or_answer

router = Router(name="admin_broadcast")
log = get_logger("admin.broadcast")


@router.callback_query(AdminCB.filter(F.action == "broadcast"), IsAdmin())
async def broadcast_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(BroadcastFlow.entering_message)
    await edit_or_answer(
        callback.message,
        "📣 پیام همگانی را ارسال کنید (متن دلخواه):",
        reply_markup=cancel_only(),
    )
    await callback.answer()


@router.message(BroadcastFlow.entering_message, F.text, IsAdmin())
async def broadcast_preview(message: Message, state: FSMContext) -> None:
    await state.update_data(text=message.html_text)
    await state.set_state(BroadcastFlow.confirming)
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ ارسال", callback_data=AdminCB(action="broadcast_confirm"))
    kb.button(text="❌ لغو", callback_data=AdminCB(action="broadcast_cancel"))
    await message.answer(
        f"پیش‌نمایش:\n\n{message.html_text}\n\nارسال شود؟",
        reply_markup=kb.as_markup(),
    )


@router.callback_query(AdminCB.filter(F.action == "broadcast_cancel"), IsAdmin())
async def broadcast_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("پیام همگانی لغو شد.")
    await callback.answer()


@router.callback_query(
    BroadcastFlow.confirming, AdminCB.filter(F.action == "broadcast_confirm"), IsAdmin()
)
async def broadcast_send(
    callback: CallbackQuery, services: Services, state: FSMContext, bot
) -> None:
    data = await state.get_data()
    text = data["text"]
    await state.clear()
    await callback.message.edit_text("⏳ در حال ارسال پیام همگانی...")
    await callback.answer()

    sent, failed = 0, 0
    offset = 0
    while True:
        users = await services.users.list(offset=offset, limit=100)
        if not users:
            break
        for user in users:
            try:
                await bot.send_message(user.telegram_id, text)
                sent += 1
            except Exception:  # noqa: BLE001 - skip blocked/invalid users
                failed += 1
            await asyncio.sleep(0.05)  # respect Telegram flood limits
        offset += 100

    await callback.message.answer(
        f"✅ ارسال پایان یافت.\nموفق: {sent} | ناموفق: {failed}"
    )
    log.info("broadcast_done", sent=sent, failed=failed)
