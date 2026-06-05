"""Notification service — sends event logs to the admin log channel & admin DM."""
from __future__ import annotations

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from app.core.config import settings
from app.core.logger import get_logger

log = get_logger("notification")


class NotificationService:
    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    async def log_event(self, title: str, lines: dict[str, str] | None = None) -> None:
        """Send a formatted event to the log channel. Never raises."""
        text = f"📋 <b>{title}</b>"
        if lines:
            body = "\n".join(f"• <b>{k}:</b> {v}" for k, v in lines.items())
            text += "\n" + body
        try:
            await self.bot.send_message(settings.log_chat_id, text)
        except TelegramAPIError as exc:
            log.warning("log_channel_send_failed", error=str(exc))

    async def notify_admin(self, text: str, reply_markup=None) -> None:
        try:
            await self.bot.send_message(
                settings.admin_id, text, reply_markup=reply_markup
            )
        except TelegramAPIError as exc:
            log.warning("admin_notify_failed", error=str(exc))

    async def notify_user(self, telegram_id: int, text: str, reply_markup=None) -> None:
        try:
            await self.bot.send_message(telegram_id, text, reply_markup=reply_markup)
        except TelegramAPIError as exc:
            log.warning("user_notify_failed", user=telegram_id, error=str(exc))

    async def send_error(self, context: str, error: Exception) -> None:
        try:
            await self.bot.send_message(
                settings.log_chat_id,
                f"🛑 <b>خطای سیستم</b>\n<b>محل:</b> {context}\n<code>{error}</code>",
            )
        except TelegramAPIError:
            log.error("error_report_failed", context=context)
