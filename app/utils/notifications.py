"""Global error handler — reports unhandled exceptions to the log channel."""
from __future__ import annotations

from aiogram import Bot, Router
from aiogram.types import ErrorEvent

from app.core.logger import get_logger
from app.services.notification_service import NotificationService

router = Router(name="errors")
log = get_logger("errors")


@router.errors()
async def on_error(event: ErrorEvent, bot: Bot) -> bool:
    log.error("unhandled_exception", exc_info=event.exception)
    # Surface the failure to whoever pressed the button. Without this a callback
    # handler that raises leaves the inline button spinning then silent — it
    # looks like the button "does nothing". The full report still goes to the
    # log channel below.
    callback = event.update.callback_query
    if callback is not None:
        try:
            await callback.answer(
                f"⚠️ خطا: {type(event.exception).__name__}\n{event.exception}"[:200],
                show_alert=True,
            )
        except Exception:  # noqa: BLE001 - callback too old / already answered
            pass
    try:
        await NotificationService(bot).send_error(
            context=type(event.exception).__name__, error=event.exception
        )
    except Exception:  # noqa: BLE001
        pass
    return True  # mark as handled so polling continues
