"""Channel-lock service — forced-membership enforcement.

Admins register channels users must join before using the bot. Membership is
verified through ``getChatMember``; the bot must itself be a member/admin of
each channel for the check to work.

A short-lived Redis cache records when a user last passed *all* active channels,
so the common case (already-a-member) doesn't hit the Telegram API on every
single update. Negative results are never cached, so a user is unlocked the
instant they join and re-check.
"""
from __future__ import annotations

from dataclasses import dataclass

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from redis.asyncio import Redis

from app.keyboards.callbacks import ChannelCB
from app.models.locked_channel import LockedChannel
from app.repositories.locked_channels import LockedChannelRepository

# Telegram member statuses that count as "joined".
_ALLOWED_STATUSES = {"member", "administrator", "creator"}
# Bot statuses that allow it to query other members.
_BOT_OK_STATUSES = {"member", "administrator", "creator"}

# Redis key + TTL for the "user passed all channels" cache.
_PASS_KEY = "chlock:pass:{uid}"
_PASS_TTL = 60  # seconds


class ChannelAccessError(Exception):
    """Raised when a channel can't be resolved or the bot lacks access to it."""


@dataclass
class ResolvedChannel:
    title: str
    chat_id: int
    username: str | None
    invite_link: str | None


class ChannelLockService:
    def __init__(self, repo: LockedChannelRepository, redis: Redis | None = None) -> None:
        self.repo = repo
        self.redis = redis

    # ----------------------------- admin CRUD -----------------------------
    async def list_all(self) -> list[LockedChannel]:
        return await self.repo.all_ordered()

    async def list_active_channels(self) -> list[LockedChannel]:
        return await self.repo.active()

    async def get(self, channel_id: int) -> LockedChannel | None:
        return await self.repo.get(channel_id)

    async def remove_channel(self, channel: LockedChannel) -> None:
        await self.repo.delete(channel)

    async def toggle_channel(self, channel: LockedChannel) -> bool:
        channel.is_active = not channel.is_active
        await self.repo.session.flush()
        return channel.is_active

    async def add_channel(self, bot: Bot, identifier: str) -> LockedChannel:
        """Resolve ``identifier`` (numeric id or @username) and store it.

        Raises ``ChannelAccessError`` if the channel can't be resolved or the
        bot isn't a member/admin there (so an unusable channel is never saved).
        """
        resolved = await self._resolve(bot, identifier)
        existing = await self.repo.get_by_chat_id(resolved.chat_id)
        if existing is not None:
            # Re-activate / refresh an already-known channel instead of duplicating.
            existing.title = resolved.title
            existing.username = resolved.username
            existing.invite_link = resolved.invite_link
            existing.is_active = True
            await self.repo.session.flush()
            return existing
        channel = LockedChannel(
            title=resolved.title,
            chat_id=resolved.chat_id,
            username=resolved.username,
            invite_link=resolved.invite_link,
            is_active=True,
        )
        return await self.repo.add(channel)

    async def _resolve(self, bot: Bot, identifier: str) -> ResolvedChannel:
        identifier = identifier.strip()
        if not identifier:
            raise ChannelAccessError("شناسه کانال خالی است.")
        # Accept "@name", "https://t.me/name", "t.me/name" or a numeric id.
        key: str | int = identifier
        if identifier.startswith("http"):
            identifier = identifier.rstrip("/").split("/")[-1]
            key = "@" + identifier.lstrip("@")
        elif identifier.startswith("@"):
            key = identifier
        elif identifier.lstrip("-").isdigit():
            key = int(identifier)
        else:
            key = "@" + identifier

        try:
            chat = await bot.get_chat(key)
        except Exception as exc:  # noqa: BLE001 - surface a friendly message
            raise ChannelAccessError(
                "کانال پیدا نشد یا ربات به آن دسترسی ندارد. مطمئن شوید ربات "
                "داخل کانال عضو/ادمین است و شناسه درست است."
            ) from exc

        if not await self.check_bot_access(bot, chat.id):
            raise ChannelAccessError(
                "ربات داخل این کانال عضو/ادمین نیست. ابتدا ربات را در کانال "
                "ادمین کنید و دوباره تلاش کنید."
            )

        username = chat.username
        invite_link: str | None = None
        if username:
            invite_link = f"https://t.me/{username}"
        else:
            invite_link = getattr(chat, "invite_link", None)
            if not invite_link:
                try:
                    created = await bot.create_chat_invite_link(chat.id)
                    invite_link = created.invite_link
                except Exception:  # noqa: BLE001 - link is optional
                    invite_link = None
        return ResolvedChannel(
            title=chat.title or username or str(chat.id),
            chat_id=chat.id,
            username=username,
            invite_link=invite_link,
        )

    # --------------------------- access checks ---------------------------
    async def check_bot_access(self, bot: Bot, chat_id: int) -> bool:
        try:
            me = await bot.me()
            member = await bot.get_chat_member(chat_id, me.id)
        except Exception:  # noqa: BLE001
            return False
        return member.status in _BOT_OK_STATUSES

    async def check_user_membership(self, bot: Bot, chat_id: int, user_id: int) -> bool:
        try:
            member = await bot.get_chat_member(chat_id, user_id)
        except Exception:  # noqa: BLE001 - treat unverifiable as "not a member"
            return False
        if member.status in _ALLOWED_STATUSES:
            return True
        # "restricted" still counts only if the user remains a member.
        if member.status == "restricted":
            return bool(getattr(member, "is_member", False))
        return False

    async def get_missing_channels(self, bot: Bot, user_id: int) -> list[LockedChannel]:
        missing: list[LockedChannel] = []
        for channel in await self.list_active_channels():
            if not await self.check_user_membership(bot, channel.chat_id, user_id):
                missing.append(channel)
        return missing

    async def is_user_allowed(self, bot: Bot, user_id: int) -> bool:
        """True if the user may use the bot (member of every active channel).

        Uses a short Redis cache for the positive case to avoid per-update API
        calls; if no active channels exist, everyone is allowed.
        """
        if self.redis is not None:
            try:
                if await self.redis.get(_PASS_KEY.format(uid=user_id)):
                    return True
            except Exception:  # noqa: BLE001 - cache must never block the bot
                pass

        active = await self.list_active_channels()
        if not active:
            return True

        for channel in active:
            if not await self.check_user_membership(bot, channel.chat_id, user_id):
                return False

        if self.redis is not None:
            try:
                await self.redis.set(_PASS_KEY.format(uid=user_id), "1", ex=_PASS_TTL)
            except Exception:  # noqa: BLE001
                pass
        return True

    async def clear_cache(self, user_id: int) -> None:
        if self.redis is not None:
            try:
                await self.redis.delete(_PASS_KEY.format(uid=user_id))
            except Exception:  # noqa: BLE001
                pass

    # --------------------------- lock message ---------------------------
    def build_lock_message(
        self, channels: list[LockedChannel]
    ) -> tuple[str, InlineKeyboardMarkup]:
        lines = [
            "🔒 <b>عضویت اجباری</b>\n",
            "برای استفاده از ربات، ابتدا در کانال‌های زیر عضو شوید و سپس روی "
            "«✅ عضو شدم» بزنید:\n",
        ]
        kb = InlineKeyboardBuilder()
        for ch in channels:
            link = ch.invite_link or (
                f"https://t.me/{ch.username}" if ch.username else None
            )
            label = f"📢 {ch.title}"
            if link:
                kb.button(text=label, url=link)
            else:
                # No link available — still list the channel by name.
                lines.append(f"• {ch.title}")
        kb.button(
            text="✅ عضو شدم",
            callback_data=ChannelCB(action="check"),
        )
        kb.adjust(1)
        return "\n".join(lines), kb.as_markup()
