"""Advertising-channel service — where new-listing announcements are mirrored.

Admins register channels from «📢 مدیریت کانال‌ها → 📣 کانال‌های تبلیغ»; every
active one receives each new-listing announcement. A channel is saved only when
the bot can actually post there (admin with «Post Messages» in a channel, member
in a group), so an unusable channel never silently swallows listings.

Identifier parsing (``@name`` / ``t.me/name`` / numeric id, private invite links
rejected with guidance) is shared with the lock-channel service.
"""
from __future__ import annotations

from dataclasses import dataclass

from aiogram import Bot

from app.models.ad_channel import AdChannel
from app.repositories.ad_channels import AdChannelRepository
from app.services.channel_lock_service import ChannelAccessError, _parse_identifier

# Statuses that may send to a group/supergroup without further rights.
_GROUP_POSTER_STATUSES = {"creator", "administrator", "member"}


def member_can_post(chat_type: str, member) -> bool:
    """Whether a ``ChatMember`` (the bot's) may post in a chat of ``chat_type``.

    In a channel only admins with ``can_post_messages`` (or the creator) can post;
    in a group any member can, unless restricted from sending messages.
    """
    status = getattr(member, "status", None)
    if chat_type == "channel":
        if status == "creator":
            return True
        return status == "administrator" and bool(getattr(member, "can_post_messages", False))
    if status in _GROUP_POSTER_STATUSES:
        return True
    if status == "restricted":
        return bool(getattr(member, "is_member", False)) and bool(
            getattr(member, "can_send_messages", False)
        )
    return False


@dataclass
class ResolvedAdChannel:
    title: str
    chat_id: int
    username: str | None


class AdChannelService:
    def __init__(self, repo: AdChannelRepository) -> None:
        self.repo = repo

    # ----------------------------- admin CRUD -----------------------------
    async def list_all(self) -> list[AdChannel]:
        return await self.repo.all_ordered()

    async def list_active(self) -> list[AdChannel]:
        return await self.repo.active()

    async def get(self, channel_id: int) -> AdChannel | None:
        return await self.repo.get(channel_id)

    async def remove_channel(self, channel: AdChannel) -> None:
        await self.repo.delete(channel)

    async def toggle_channel(self, channel: AdChannel) -> bool:
        channel.is_active = not channel.is_active
        await self.repo.session.flush()
        return channel.is_active

    async def add_channel(self, bot: Bot, identifier: str) -> AdChannel:
        """Resolve ``identifier`` (numeric id, @username or public link) and store it.

        Raises ``ChannelAccessError`` if the chat can't be resolved or the bot
        can't post there, so an unusable channel is never saved.
        """
        return await self._store(await self._resolve(bot, _parse_identifier(identifier)))

    async def add_channel_by_id(self, bot: Bot, chat_id: int) -> AdChannel:
        """Store a channel whose numeric id is already known (forwarded post)."""
        return await self._store(await self._resolve(bot, chat_id))

    async def _store(self, resolved: ResolvedAdChannel) -> AdChannel:
        existing = await self.repo.get_by_chat_id(resolved.chat_id)
        if existing is not None:
            # Re-activate / refresh an already-known channel instead of duplicating.
            existing.title = resolved.title
            existing.username = resolved.username
            existing.is_active = True
            await self.repo.session.flush()
            return existing
        return await self.repo.add(
            AdChannel(
                title=resolved.title,
                chat_id=resolved.chat_id,
                username=resolved.username,
                is_active=True,
            )
        )

    async def _resolve(self, bot: Bot, key: str | int) -> ResolvedAdChannel:
        try:
            chat = await bot.get_chat(key)
        except Exception as exc:  # noqa: BLE001 - surface a friendly message
            raise ChannelAccessError(
                "کانال پیدا نشد یا ربات به آن دسترسی ندارد. مطمئن شوید ربات "
                "داخل کانال ادمین است و شناسه درست است.\n\n"
                "برای کانال خصوصی، یک پست از همان کانال را فوروارد کنید."
            ) from exc
        if not await self._bot_can_post(bot, chat):
            raise ChannelAccessError(
                "ربات اجازهٔ ارسال پیام در این کانال را ندارد.\n\n"
                "ربات را در کانال <b>ادمین</b> کنید و دسترسی "
                "«<b>ارسال پیام / Post Messages</b>» را به آن بدهید، سپس دوباره تلاش کنید."
            )
        return ResolvedAdChannel(
            title=chat.title or chat.username or str(chat.id),
            chat_id=chat.id,
            username=chat.username,
        )

    # --------------------------- access checks ---------------------------
    @staticmethod
    async def _bot_can_post(bot: Bot, chat) -> bool:
        try:
            me = await bot.me()
            member = await bot.get_chat_member(chat.id, me.id)
        except Exception:  # noqa: BLE001 - not a member / unreachable
            return False
        return member_can_post(chat.type, member)

    async def check_and_refresh(self, bot: Bot, channel: AdChannel) -> bool:
        """Re-check that the bot can still post to ``channel``.

        Also refreshes the stored title/username from Telegram while at it (the
        caller commits). Returns ``False`` when the chat is unreachable or the
        bot lost its posting right.
        """
        try:
            chat = await bot.get_chat(channel.chat_id)
        except Exception:  # noqa: BLE001 - unreachable channel
            return False
        channel.title = chat.title or chat.username or channel.title
        channel.username = chat.username
        await self.repo.session.flush()
        return await self._bot_can_post(bot, chat)

    async def resolve_placeholder_titles(self, bot: Bot) -> bool:
        """Fill in real titles for rows still showing their chat id.

        Only the channel carried over from the old ``LISTING_CHANNEL_ID`` setting
        starts that way (the migration can't reach Telegram). Best-effort: an
        unreachable chat keeps its placeholder and is retried next time. Returns
        ``True`` when something changed (the caller commits).
        """
        changed = False
        for channel in await self.repo.all_ordered():
            if not channel.title_unresolved:
                continue
            try:
                chat = await bot.get_chat(channel.chat_id)
            except Exception:  # noqa: BLE001 - keep the placeholder, retry later
                continue
            title = chat.title or chat.username
            if title:
                channel.title = title
                channel.username = chat.username
                changed = True
        if changed:
            await self.repo.session.flush()
        return changed
