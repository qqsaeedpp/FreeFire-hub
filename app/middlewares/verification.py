"""Onboarding verification gate.

Runs after :class:`~app.middlewares.channel_lock.ChannelLockMiddleware`, so the
order a new user experiences is: join the required channels → prove their phone
→ solve the captcha → main menu.

The gate is purely a *router*: it decides whether an update may proceed and
re-shows the pending step otherwise. It never writes to the database, never
touches ``pending_referral_code``, never settles a referral and never opens the
main menu — all of that belongs to the handlers it protects.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject, Update
from aiogram.types import User as TgUser

from app.container import Services
from app.core.config import settings
from app.keyboards.callbacks import ChannelCB, VerificationCB
from app.models.user import User

# Callback prefixes that must always reach their handler, or onboarding would
# dead-end: the captcha buttons themselves, and the «✅ عضو شدم» channel re-check
# (which is what advances a channel-locked user into verification).
_VERIFY_PREFIX = VerificationCB.__prefix__ + VerificationCB.__separator__
_CHANNEL_CHECK_PREFIX = ChannelCB(action="check").pack()


def _is_start(message: Message) -> bool:
    """Whether this message is a ``/start`` (with or without a deep-link payload)."""
    text = message.text or ""
    if not text:
        return False
    return text.split(maxsplit=1)[0].split("@", 1)[0].lower() == "/start"


class VerificationMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        inner = event.event if isinstance(event, Update) else event
        if not isinstance(inner, (Message, CallbackQuery)):
            return await handler(event, data)

        tg_user: TgUser | None = data.get("event_from_user")
        if tg_user is None or tg_user.is_bot:
            return await handler(event, data)

        db_user: User | None = data.get("db_user")
        # Owners and DB admins are exempt from verification.
        if tg_user.id in settings.admin_ids or bool(db_user and db_user.is_admin):
            return await handler(event, data)

        services: Services | None = data.get("services")
        if services is None or db_user is None:
            return await handler(event, data)
        if services.verification.is_complete(db_user):
            return await handler(event, data)

        if isinstance(inner, CallbackQuery):
            payload = inner.data or ""
            if payload.startswith(_VERIFY_PREFIX) or payload.startswith(
                _CHANNEL_CHECK_PREFIX
            ):
                return await handler(event, data)
            # Always answer, or the client keeps spinning on the tapped button.
            await inner.answer()
            if inner.message is not None:
                await self._show_step(inner.message, services, db_user, data)
            return None

        # Messages: /start restarts onboarding, and a shared contact is the phone
        # step itself. Everything else is held back.
        if _is_start(inner) or inner.contact is not None:
            return await handler(event, data)
        await self._show_step(inner, services, db_user, data)
        return None

    @staticmethod
    async def _show_step(
        message: Message,
        services: Services,
        db_user: User,
        data: dict[str, Any],
    ) -> None:
        """Re-display the step the user still owes, reading it from MySQL."""
        # Imported lazily: the handlers package imports middlewares indirectly, so
        # a module-level import here would be circular.
        from app.handlers.user.common import prompt_captcha, prompt_phone
        from app.services.verification_service import OnboardingStep
        from app.states.user_states import VerificationFlow

        state = data.get("state")
        if services.verification.next_step(db_user) is OnboardingStep.PHONE:
            if state is not None:
                await state.set_state(VerificationFlow.waiting_phone)
            await prompt_phone(message)
        else:
            if state is not None:
                await state.set_state(VerificationFlow.waiting_captcha)
            await prompt_captcha(message, services, db_user.telegram_id)
