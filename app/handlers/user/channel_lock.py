"""User: «✅ عضو شدم» re-check for forced-membership channels.

This callback is allowed through the lock gate (see ``ChannelLockMiddleware``)
so a blocked user can re-verify after joining. On success the membership cache
is cleared and the main menu is shown; otherwise the channel list reappears.
"""
from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from app.container import Services
from app.handlers.user.common import continue_onboarding
from app.keyboards.callbacks import ChannelCB
from app.models.user import User
from app.utils.helpers import answer_managed

router = Router(name="user_channel_lock")


@router.callback_query(ChannelCB.filter(F.action == "check"))
async def recheck_membership(
    callback: CallbackQuery,
    services: Services,
    db_user: User,
    state: FSMContext,
    bot,
) -> None:
    missing = await services.channel.get_missing_channels(bot, callback.from_user.id)
    if not missing:
        # Joined everything — unlock and hand over to onboarding, which decides
        # whether the user still owes a phone/captcha step or is already verified
        # (in which case it settles the referral captured at the first /start).
        # Nothing is paid out here: the welcome screen and any reward are gated
        # behind completed verification, and repeated taps are idempotent.
        await services.channel.clear_cache(callback.from_user.id)
        await state.clear()
        await callback.answer("✅ عضویت تایید شد.")
        await continue_onboarding(
            callback.message, services, db_user, state, bot
        )
        return

    await callback.answer(
        "❌ هنوز عضو همه کانال‌ها نشده‌اید.", show_alert=True
    )
    prompt, prompt_entities = await services.text.render("channel_lock")
    text, entities, markup = services.channel.build_lock_message(
        missing, prompt, prompt_entities
    )
    await callback.message.answer(
        "❌ هنوز عضو همه کانال‌ها نشده‌اید.\n"
        "لطفاً ابتدا در کانال‌های زیر عضو شوید و دوباره روی «عضو شدم» بزنید.",
    )
    await answer_managed(callback.message, (text, entities), reply_markup=markup)
