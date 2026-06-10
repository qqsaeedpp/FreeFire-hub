"""Notification service — sends event logs to the admin log channel & admin DM."""
from __future__ import annotations

from collections.abc import Iterable

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

    async def notify_admins(
        self,
        admin_ids: Iterable[int],
        text: str,
        reply_markup=None,
        *,
        photo: str | None = None,
        exclude: Iterable[int] = (),
    ) -> None:
        """Additive broadcast: send the same notification to every admin.

        This is a *new layer on top of* the existing single-admin send — it does
        not replace ``notify_admin`` or any current flow. Each recipient is
        independent; a per-admin failure (blocked bot, stale photo file_id) is
        swallowed so it never affects the user flow or the other admins. A photo
        that can't be sent degrades to a text message so the admin still gets the
        alert. ``exclude`` skips admins already notified by the legacy path
        (avoids a duplicate for ``settings.admin_id``).
        """
        seen = set(exclude)
        for aid in admin_ids:
            if aid in seen:
                continue
            seen.add(aid)
            try:
                if photo:
                    await self.bot.send_photo(
                        aid, photo, caption=text, reply_markup=reply_markup
                    )
                else:
                    await self.bot.send_message(aid, text, reply_markup=reply_markup)
            except TelegramAPIError:
                try:
                    await self.bot.send_message(aid, text, reply_markup=reply_markup)
                except TelegramAPIError as exc:
                    log.warning("admin_broadcast_failed", admin=aid, error=str(exc))

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
