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
    try:
        await NotificationService(bot).send_error(
            context=type(event.exception).__name__, error=event.exception
        )
    except Exception:  # noqa: BLE001
        pass
    return True  # mark as handled so polling continues
