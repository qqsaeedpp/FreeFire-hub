"""Referral handlers — show code, link and stats."""
from __future__ import annotations

from aiogram import Router
from aiogram.types import Message

from app.container import Services
from app.filters.buttons import MainBtn
from app.services.button_service import BTN_KEY_REFERRAL
from app.models.user import User
from app.utils.helpers import format_toman

router = Router(name="user_referral")


@router.message(MainBtn(BTN_KEY_REFERRAL))
async def referral_home(
    message: Message, services: Services, db_user: User, bot
) -> None:
    stats = await services.referral.stats(db_user)
    reward = await services.referral.get_reward()
    me = await bot.me()
    link = f"https://t.me/{me.username}?start={db_user.referral_code}"
    text = (
        "🎁 <b>زیرمجموعه‌گیری</b>\n\n"
        f"به‌ازای هر دوست جدید که با لینک شما در ربات عضو شود، "
        f"<b>{format_toman(reward)}</b> به کیف پول شما اضافه می‌شود.\n\n"
        f"🔗 لینک دعوت شما:\n{link}\n\n"
        f"🆔 کد معرف: <code>{db_user.referral_code}</code>\n\n"
        f"👥 تعداد دعوت‌شده‌ها: <b>{stats['invited']}</b>\n"
        f"💰 مجموع پاداش دریافتی: <b>{format_toman(stats['earned'])}</b>"
    )
    await message.answer(text)
