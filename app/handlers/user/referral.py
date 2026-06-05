"""Referral handlers — show code, link and stats."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.types import Message

from app.container import Services
from app.core.config import settings
from app.keyboards.reply import BTN_REFERRAL
from app.models.user import User
from app.utils.helpers import format_toman

router = Router(name="user_referral")


@router.message(F.text == BTN_REFERRAL)
async def referral_home(
    message: Message, services: Services, db_user: User, bot
) -> None:
    stats = await services.referral.stats(db_user)
    me = await bot.me()
    link = f"https://t.me/{me.username}?start={db_user.referral_code}"
    text = (
        "🎁 <b>زیرمجموعه‌گیری</b>\n\n"
        f"به‌ازای هر دوست که با لینک شما عضو شود و <b>اولین خرید موفق</b> را انجام دهد، "
        f"<b>{format_toman(settings.referral_reward)}</b> به کیف پول شما اضافه می‌شود.\n\n"
        f"🔗 لینک دعوت شما:\n{link}\n\n"
        f"🆔 کد معرف: <code>{db_user.referral_code}</code>\n\n"
        f"👥 تعداد دعوت‌شده‌ها: <b>{stats['invited']}</b>\n"
        f"💰 مجموع پاداش دریافتی: <b>{format_toman(stats['earned'])}</b>"
    )
    await message.answer(text)
