"""DB-editable main-button text/emoji, with hardcoded fallbacks.

Each main reply-keyboard button has a stable ``key``. The label rendered (and
matched in handlers) is ``"{emoji} {text}"`` resolved from the DB override or
the hardcoded default. This lets an admin rename buttons without code changes.

``button_type`` (PRIMARY/SUCCESS/DANGER), ``is_enabled`` and ``custom_emoji_id``
are persisted for the future appearance system but do not affect rendering yet —
Telegram buttons can't show colors or custom emoji on the label itself.
"""
from __future__ import annotations

from app.models.button_settings import ButtonSettings
from app.repositories.button_settings import ButtonSettingsRepository

# Stable keys for the main reply-keyboard buttons.
BTN_KEY_BUY_DIAMOND = "buy_diamond"
BTN_KEY_BUY_ACCOUNT = "buy_account"
BTN_KEY_SELL_ACCOUNT = "sell_account"
BTN_KEY_WALLET = "wallet"
BTN_KEY_REFERRAL = "referral"
BTN_KEY_MY_ORDERS = "my_orders"
BTN_KEY_SUPPORT = "support"
BTN_KEY_ADMIN = "admin"

# Order of the main menu (admin appended only for admins, handled by the keyboard).
MAIN_MENU_KEYS: tuple[str, ...] = (
    BTN_KEY_BUY_DIAMOND,
    BTN_KEY_BUY_ACCOUNT,
    BTN_KEY_SELL_ACCOUNT,
    BTN_KEY_WALLET,
    BTN_KEY_REFERRAL,
    BTN_KEY_MY_ORDERS,
    BTN_KEY_SUPPORT,
)

# Hardcoded (emoji, text) defaults — must reproduce the historical labels exactly.
BUTTON_DEFAULTS: dict[str, tuple[str, str]] = {
    BTN_KEY_BUY_DIAMOND: ("💎", "خرید جم"),
    BTN_KEY_BUY_ACCOUNT: ("🛒", "خرید اکانت"),
    BTN_KEY_SELL_ACCOUNT: ("💰", "فروش اکانت"),
    BTN_KEY_WALLET: ("👛", "کیف پول"),
    BTN_KEY_REFERRAL: ("🎁", "زیرمجموعه‌گیری"),
    BTN_KEY_MY_ORDERS: ("📦", "سفارش‌های من"),
    BTN_KEY_SUPPORT: ("🎧", "پشتیبانی"),
    BTN_KEY_ADMIN: ("🛠", "پنل مدیریت"),
}

# Persian display names for the admin button-management section.
BUTTON_LABELS: dict[str, str] = {
    BTN_KEY_BUY_DIAMOND: "خرید جم",
    BTN_KEY_BUY_ACCOUNT: "خرید اکانت",
    BTN_KEY_SELL_ACCOUNT: "فروش اکانت",
    BTN_KEY_WALLET: "کیف پول",
    BTN_KEY_REFERRAL: "زیرمجموعه‌گیری",
    BTN_KEY_MY_ORDERS: "سفارش‌های من",
    BTN_KEY_SUPPORT: "پشتیبانی",
    BTN_KEY_ADMIN: "پنل مدیریت",
}


def _compose(emoji: str | None, text: str | None, key: str) -> str:
    d_emoji, d_text = BUTTON_DEFAULTS.get(key, ("", ""))
    e = emoji if emoji is not None else d_emoji
    t = text if text else d_text
    return f"{e} {t}".strip()


class ButtonService:
    def __init__(self, repo: ButtonSettingsRepository) -> None:
        self.repo = repo
        self._labels_cache: dict[str, str] | None = None  # per-update cache

    def default_label(self, key: str) -> str:
        emoji, text = BUTTON_DEFAULTS.get(key, ("", ""))
        return f"{emoji} {text}".strip()

    async def all_labels(self) -> dict[str, str]:
        """key → full label for every known button (DB override or default)."""
        if self._labels_cache is None:
            rows = {r.key: r for r in await self.repo.all()}
            self._labels_cache = {
                key: (
                    _compose(rows[key].emoji, rows[key].text, key)
                    if key in rows
                    else self.default_label(key)
                )
                for key in BUTTON_DEFAULTS
            }
        return self._labels_cache

    async def label(self, key: str) -> str:
        return (await self.all_labels()).get(key, self.default_label(key))

    async def get(self, key: str) -> ButtonSettings | None:
        return await self.repo.get_by_key(key)

    async def _ensure(self, key: str) -> ButtonSettings:
        row = await self.repo.get_by_key(key)
        if row is None:
            row = await self.repo.add(ButtonSettings(key=key))
        return row

    async def set_text(self, key: str, text: str) -> None:
        row = await self._ensure(key)
        row.text = text
        self._labels_cache = None  # invalidate

    async def set_emoji(self, key: str, emoji: str) -> None:
        row = await self._ensure(key)
        row.emoji = emoji
        self._labels_cache = None

    async def reset(self, key: str) -> bool:
        row = await self.repo.get_by_key(key)
        if row is None:
            return False
        await self.repo.delete(row)
        self._labels_cache = None
        return True
