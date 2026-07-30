"""User onboarding: prove phone ownership, then solve a math captcha.

Only these two handlers (plus /start and the channel re-check) run for an
unverified account — everything else is held back by
:class:`~app.middlewares.verification.VerificationMiddleware`.

The referral payout lives entirely in the captcha step's finalization, so no
reward can exist before both stages are done.
"""
from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove

from app.container import Services
from app.core.logger import get_logger
from app.handlers.user.common import (
    PHONE_OK_TEXT,
    VERIFIED_TEXT,
    _is_admin,
    _send_welcome,
    announce_referral,
    prompt_captcha,
    prompt_phone,
)
from app.keyboards.callbacks import VerificationCB
from app.models.user import User
from app.services.verification_service import (
    CaptchaOutcome,
    ContactOwnershipError,
    PhoneAlreadyUsedError,
    PhoneNotIranianMobileError,
    PhoneVerificationError,
)
from app.states.user_states import VerificationFlow
from app.utils.helpers import safe_answer

router = Router(name="user_verification")
log = get_logger("user.verification")

BAD_CONTACT_TEXT = (
    "❌ این شماره متعلق به حساب تلگرام شما تشخیص داده نشد.\n\n"
    "لطفاً فقط از دکمه «ارسال شماره تلفن من» استفاده کنید."
)
NOT_IRANIAN_TEXT = "❌ فقط شماره موبایل معتبر ایران با پیش‌شماره +98 پذیرفته می‌شود."
DUPLICATE_TEXT = (
    "❌ این شماره قبلاً برای حساب دیگری ثبت شده است.\n\n"
    "در صورت تصور اشتباه، با مدیریت مجموعه تماس بگیرید."
)
CAPTCHA_EXPIRED_TEXT = "⌛ این کپچا منقضی شده است. یک سؤال جدید برای شما ساخته شد."
CAPTCHA_WRONG_TEXT = "❌ پاسخ صحیح نبود. لطفاً سؤال جدید را حل کنید."
CAPTCHA_LOCKED_TEXT = (
    "⛔️ تعداد پاسخ‌های نادرست زیاد بود.\n"
    "لطفاً کمی صبر کنید و سپس دوباره تلاش کنید."
)


@router.message(F.contact)
async def receive_contact(
    message: Message,
    services: Services,
    db_user: User,
    state: FSMContext,
    bot,
) -> None:
    """Accept a shared contact, bind the number, then move on to the captcha.

    Registered on *any* contact message rather than on the FSM state, so a user
    whose state was cleared (restart, /menu, MenuResetMiddleware) can still
    complete the step. Already-verified users are ignored, so a stray contact
    later in the session does nothing.
    """
    if services.verification.is_complete(db_user):
        return

    try:
        phone = services.verification.extract_owned_phone(message)
    except ContactOwnershipError:
        await safe_answer(message, BAD_CONTACT_TEXT)
        await prompt_phone(message)
        return
    except PhoneNotIranianMobileError:
        await safe_answer(message, NOT_IRANIAN_TEXT)
        await prompt_phone(message)
        return

    try:
        await services.verification.claim_phone(db_user, phone)
    except PhoneAlreadyUsedError:
        # The pending referral code is untouched, so a later retry with the
        # user's own number can still earn the referrer their reward.
        await safe_answer(message, DUPLICATE_TEXT)
        return

    await services.commit()

    # Drop the one-off contact keyboard before switching to inline buttons.
    await safe_answer(message, PHONE_OK_TEXT, reply_markup=ReplyKeyboardRemove())
    await state.set_state(VerificationFlow.waiting_captcha)
    await prompt_captcha(message, services, db_user.telegram_id)


@router.callback_query(VerificationCB.filter(F.action == "answer"))
async def answer_captcha(
    callback: CallbackQuery,
    callback_data: VerificationCB,
    services: Services,
    db_user: User,
    state: FSMContext,
    bot,
) -> None:
    """Consume the challenge and, on success, finalize verification + referral."""
    message = callback.message
    if services.verification.is_complete(db_user):
        # Second click of an already-winning answer: acknowledge, never re-pay.
        await callback.answer()
        await state.clear()
        if message is not None:
            await _send_welcome(
                message, services, _is_admin(db_user, callback.from_user.id)
            )
        return

    outcome = await services.verification.submit_captcha(
        callback.from_user.id, callback_data.nonce, callback_data.choice
    )

    if outcome is CaptchaOutcome.STALE:
        # An old message's button — the live challenge must stay untouched.
        await callback.answer(CAPTCHA_EXPIRED_TEXT, show_alert=True)
        return
    if outcome is CaptchaOutcome.LOCKED:
        await callback.answer(CAPTCHA_LOCKED_TEXT, show_alert=True)
        return
    if outcome in (CaptchaOutcome.EXPIRED, CaptchaOutcome.WRONG):
        text = (
            CAPTCHA_EXPIRED_TEXT
            if outcome is CaptchaOutcome.EXPIRED
            else CAPTCHA_WRONG_TEXT
        )
        await callback.answer()
        if message is not None:
            await message.answer(text)
            await prompt_captcha(message, services, db_user.telegram_id)
        return

    try:
        result = await services.verification.finalize(db_user)
    except PhoneVerificationError:
        # Captcha solved without a proven phone (only reachable if the phone row
        # was cleared mid-flow) — restart onboarding at the phone step.
        await callback.answer()
        if message is not None:
            await state.set_state(VerificationFlow.waiting_phone)
            await prompt_phone(message)
        return

    await services.commit()
    await callback.answer("✅ تایید شد.")
    await state.clear()

    if message is not None:
        await message.answer(VERIFIED_TEXT)
        await _send_welcome(
            message, services, _is_admin(db_user, callback.from_user.id)
        )
    # Strictly after the commit: a failed send must not undo the payout.
    await announce_referral(services, bot, db_user, result.referral)
