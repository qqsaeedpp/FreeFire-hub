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
from aiogram.types import InlineKeyboardMarkup, MessageEntity
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


def _parse_identifier(identifier: str) -> str | int:
    """Turn admin input into something ``getChat`` accepts.

    Handles ``@name``, ``https://t.me/name``, ``t.me/name`` and numeric ids.
    Private *invite* links (``t.me/+hash`` or ``/joinchat/hash``) are rejected
    with guidance: Telegram offers no way to resolve them to a chat id, so the
    admin must forward a post from the channel instead.
    """
    identifier = identifier.strip()
    if not identifier:
        raise ChannelAccessError("شناسه کانال خالی است.")

    if identifier.lstrip("-").isdigit():
        return int(identifier)

    tail = identifier
    if "t.me/" in identifier:
        tail = identifier.rstrip("/").split("t.me/", 1)[1]
    tail = tail.lstrip("@")

    if tail.startswith("+") or tail.startswith("joinchat/"):
        raise ChannelAccessError(
            "لینک دعوت خصوصی قابل بررسی نیست.\n\n"
            "برای افزودن کانال خصوصی، یک <b>پست از همان کانال</b> را برای ربات "
            "فوروارد کنید یا آیدی عددی کانال را بفرستید."
        )
    if not tail:
        raise ChannelAccessError("شناسه کانال خالی است.")
    return "@" + tail


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
        """Resolve ``identifier`` (numeric id, @username or public link) and store it.

        Raises ``ChannelAccessError`` if the channel can't be resolved or the
        bot isn't a member/admin there (so an unusable channel is never saved).
        """
        return await self._store(await self._resolve(bot, _parse_identifier(identifier)))

    async def add_channel_by_id(self, bot: Bot, chat_id: int) -> LockedChannel:
        """Store a channel whose numeric id is already known.

        This is the path for **private** channels: they have no @username, so the
        admin registers one by forwarding any post from it and the handler passes
        the origin chat id straight through.
        """
        return await self._store(await self._resolve(bot, chat_id))

    async def _store(self, resolved: ResolvedChannel) -> LockedChannel:
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

    async def _resolve(self, bot: Bot, key: str | int) -> ResolvedChannel:
        try:
            chat = await bot.get_chat(key)
        except Exception as exc:  # noqa: BLE001 - surface a friendly message
            raise ChannelAccessError(
                "کانال پیدا نشد یا ربات به آن دسترسی ندارد. مطمئن شوید ربات "
                "داخل کانال عضو/ادمین است و شناسه درست است.\n\n"
                "برای کانال خصوصی، یک پست از همان کانال را فوروارد کنید."
            ) from exc

        if not await self.check_bot_access(bot, chat.id):
            raise ChannelAccessError(
                "ربات داخل این کانال عضو/ادمین نیست. ابتدا ربات را در کانال "
                "ادمین کنید و دوباره تلاش کنید."
            )

        username = chat.username
        if username:
            # Public channel: the @username link always works and never expires.
            return ResolvedChannel(
                title=chat.title or username,
                chat_id=chat.id,
                username=username,
                invite_link=f"https://t.me/{username}",
            )

        # Private channel: an invite link is the ONLY way a user can join, so a
        # missing link makes the lock impossible to satisfy — refuse to save it
        # rather than showing users a channel they cannot reach.
        invite_link = await self._invite_link(bot, chat)
        if not invite_link:
            raise ChannelAccessError(
                "این کانال خصوصی است و ربات نتوانست لینک دعوت بسازد.\n\n"
                "ربات را در کانال <b>ادمین</b> کنید و دسترسی "
                "«<b>افزودن اعضا / Invite Users via Link</b>» را به آن بدهید، "
                "سپس دوباره تلاش کنید."
            )
        return ResolvedChannel(
            title=chat.title or str(chat.id),
            chat_id=chat.id,
            username=None,
            invite_link=invite_link,
        )

    @staticmethod
    async def _invite_link(bot: Bot, chat) -> str | None:
        """Best-effort invite link for a private chat.

        Prefers the channel's primary link (visible to admins via ``getChat``)
        and otherwise mints a fresh one, which needs the ``can_invite_users``
        admin right.
        """
        existing = getattr(chat, "invite_link", None)
        if existing:
            return existing
        try:
            created = await bot.create_chat_invite_link(chat.id)
            return created.invite_link
        except Exception:  # noqa: BLE001 - bot lacks the invite permission
            return None

    async def refresh_invite_link(self, bot: Bot, channel: LockedChannel) -> str | None:
        """Re-fetch the join link for a stored channel and persist it.

        Private-channel invite links can be revoked in the channel settings, which
        would silently leave users unable to satisfy the lock; this lets an admin
        mint a working link again without re-adding the channel.
        """
        try:
            chat = await bot.get_chat(channel.chat_id)
        except Exception:  # noqa: BLE001 - unreachable channel
            return None
        link = (
            f"https://t.me/{chat.username}"
            if chat.username
            else await self._invite_link(bot, chat)
        )
        if not link:
            return None
        channel.username = chat.username
        channel.invite_link = link
        channel.title = chat.title or channel.title
        await self.repo.session.flush()
        return link

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
        self,
        channels: list[LockedChannel],
        prompt: str,
        entities: list[MessageEntity] | None = None,
    ) -> tuple[str, list[MessageEntity] | None, InlineKeyboardMarkup]:
        """Build the forced-membership message from an admin-managed ``prompt``.

        ``prompt``/``entities`` come from :meth:`TextService.render` so the admin
        can edit the heading text (premium emoji included). Channels that have a
        join link become inline buttons; any without a link are appended to the
        body by name. Appending *after* the prompt keeps the entity offsets valid.
        """
        kb = InlineKeyboardBuilder()
        extra: list[str] = []
        for ch in channels:
            link = ch.invite_link or (
                f"https://t.me/{ch.username}" if ch.username else None
            )
            label = f"📢 {ch.title}"
            if link:
                kb.button(text=label, url=link)
            else:
                # No link available — still list the channel by name.
                extra.append(f"• {ch.title}")
        kb.button(
            text="✅ عضو شدم",
            callback_data=ChannelCB(action="check"),
        )
        kb.adjust(1)
        text = prompt if not extra else prompt + "\n\n" + "\n".join(extra)
        return text, entities, kb.as_markup()
