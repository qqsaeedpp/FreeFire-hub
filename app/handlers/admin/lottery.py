"""Admin: run a lottery among active users and announce the winners."""
from __future__ import annotations

import asyncio
import random

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.container import Services
from app.core.config import settings
from app.core.logger import get_logger
from app.filters.admin import IsAdmin
from app.keyboards.callbacks import AdminCB
from app.keyboards.inline import cancel_only
from app.services.notification_service import NotificationService
from app.states.admin_states import LotteryFlow
from app.utils.helpers import edit_or_answer, user_ref
from app.utils.validators import parse_price

router = Router(name="admin_lottery")
log = get_logger("admin.lottery")


@router.callback_query(AdminCB.filter(F.action == "lottery"), IsAdmin())
async def lottery_start(callback: CallbackQuery, services: Services, state: FSMContext) -> None:
    active = await services.users.count_active()
    await state.set_state(LotteryFlow.entering_winner_count)
    await edit_or_answer(
        callback.message,
        f"🎁 <b>قرعه‌کشی</b>\nتعداد کاربران فعال: {active}\n\n"
        "تعداد برندگان را وارد کنید:",
        reply_markup=cancel_only(),
    )
    await callback.answer()


@router.message(LotteryFlow.entering_winner_count, F.text, IsAdmin())
async def lottery_draw(
    message: Message, services: Services, state: FSMContext, bot
) -> None:
    count = parse_price(message.text)
    if count is None or count <= 0:
        await message.answer("❌ عدد نامعتبر است. تعداد برندگان را وارد کنید.")
        return
    await state.clear()

    users = await services.users.list_active()
    if not users:
        await message.answer("هیچ کاربر فعالی برای قرعه‌کشی وجود ندارد.")
        return

    winners = random.sample(users, k=min(count, len(users)))

    # Admin-facing result: numeric id + username + name (when present) per winner.
    admin_lines = [f"🎉 <b>برندگان قرعه‌کشی</b> ({len(winners)} نفر)\n"]
    for w in winners:
        handle = f"@{w.username}" if w.username else "بدون یوزرنیم"
        name = f" | {w.full_name}" if w.full_name else ""
        admin_lines.append(f"👤 کاربر: <code>{w.telegram_id}</code> | {handle}{name}")
    await message.answer("\n".join(admin_lines))

    # Announce in the channel.
    notifier = NotificationService(bot)
    channel_lines = ["🎁 <b>نتایج قرعه‌کشی</b>\n"]
    for i, w in enumerate(winners, 1):
        handle = f"@{w.username}" if w.username else f"کاربر {w.telegram_id}"
        channel_lines.append(f"{i}. {handle}")
    try:
        await bot.send_message(settings.lottery_channel_id, "\n".join(channel_lines))
    except Exception as exc:  # noqa: BLE001 - channel may be misconfigured
        log.warning("lottery_channel_send_failed", error=str(exc))

    # DM each winner.
    delivered = 0
    for w in winners:
        try:
            await bot.send_message(
                w.telegram_id,
                "🎉 تبریک! شما در قرعه‌کشی FreeFire Hub برنده شدید.\n"
                "برای دریافت جایزه با پشتیبانی در تماس باشید.",
            )
            delivered += 1
        except Exception:  # noqa: BLE001 - winner may have blocked the bot
            pass
        await asyncio.sleep(0.05)

    await notifier.log_event(
        "قرعه‌کشی",
        {
            "تعداد برندگان": str(len(winners)),
            "پیام خصوصی موفق": str(delivered),
            "برندگان": ", ".join(user_ref(w) for w in winners),
        },
    )
