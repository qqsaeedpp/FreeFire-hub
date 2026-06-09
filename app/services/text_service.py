"""Managed bot texts with premium custom-emoji support.

Every user-facing static message has a stable ``key`` and a hardcoded default
(HTML-formatted). An admin can override any of them; overrides live in the
``bot_texts`` table together with the message entities the admin typed, so
premium (custom) emoji round-trip exactly.

Rendering contract — :meth:`render` returns ``(text, entities)``:

* ``entities is None`` → no admin override (or override has no entities): send
  with the bot's default ``parse_mode`` (HTML). The defaults use HTML tags.
* ``entities is not None`` → an admin override that carries entities: send with
  ``parse_mode=None`` and pass these entities (HTML and entities are mutually
  exclusive in the Bot API).
"""
from __future__ import annotations

import json

from aiogram.types import MessageEntity

from app.repositories.bot_texts import BotTextRepository

# Human-readable Persian labels for each editable text (shown in the admin list).
# Only standalone, fully-static messages are managed here; screens that interleave
# dynamic data (wallet balance, referral stats, ticket lists) keep their own logic.
TEXT_LABELS: dict[str, str] = {
    "welcome": "پیام خوش‌آمد",
    "diamond_guide": "راهنمای خرید جم",
    "contact": "راه‌های ارتباطی",
}

# Hardcoded HTML defaults used until an admin overrides them.
TEXT_DEFAULTS: dict[str, str] = {
    "welcome": (
        "🎮 <b>به فروشگاه FreeFire Hub خوش آمدید!</b>\n\n"
        "از منوی زیر می‌توانید جم بخرید، اکانت بخرید یا بفروشید، "
        "کیف پول خود را مدیریت کنید و زیرمجموعه بگیرید.\n\n"
        "برای شروع یکی از گزینه‌ها را انتخاب کنید 👇"
    ),
    "diamond_guide": "💎 <b>خرید جم</b>\nمقدار جم مورد نظر را انتخاب کنید:",
    "contact": (
        "📞 <b>راه‌های ارتباطی</b>\n\n"
        "برای ارتباط با ما از راه‌های زیر استفاده کنید:\n\n"
        "👤 ادمین: @your_admin\n"
        "📢 کانال: @your_channel\n"
        "💬 گروه پشتیبانی: @your_group\n"
        "🌐 وبسایت: https://example.com\n\n"
        "این متن از پنل مدیریت قابل ویرایش است."
    ),
}


class TextService:
    def __init__(self, texts: BotTextRepository) -> None:
        self.texts = texts

    def default(self, key: str) -> str:
        return TEXT_DEFAULTS.get(key, "")

    async def render(self, key: str) -> tuple[str, list[MessageEntity] | None]:
        """Return ``(text, entities)`` for a key — override if set, else default."""
        row = await self.texts.get_by_key(key)
        if row is None:
            return self.default(key), None
        entities = _deserialize_entities(row.entities_json)
        return row.content, entities

    async def get_content(self, key: str) -> str:
        """Return the current raw text (override if present, else default)."""
        row = await self.texts.get_by_key(key)
        return row.content if row else self.default(key)

    async def set(
        self, key: str, content: str, entities: list[MessageEntity] | None
    ) -> None:
        """Create or update the override for ``key``."""
        payload = _serialize_entities(entities)
        row = await self.texts.get_by_key(key)
        if row is None:
            from app.models.bot_text import BotText

            await self.texts.add(
                BotText(key=key, content=content, entities_json=payload)
            )
        else:
            row.content = content
            row.entities_json = payload


def _serialize_entities(entities: list[MessageEntity] | None) -> str | None:
    if not entities:
        return None
    return json.dumps(
        [e.model_dump(mode="json", exclude_none=True) for e in entities]
    )


def _deserialize_entities(raw: str | None) -> list[MessageEntity] | None:
    if not raw:
        return None
    data = json.loads(raw)
    if not data:
        return None
    return [MessageEntity.model_validate(d) for d in data]
