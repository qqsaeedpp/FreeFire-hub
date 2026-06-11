"""DB-editable main-button appearance: text, emoji, color & premium emoji.

Each main reply-keyboard button has a stable ``key``. The label rendered (and
matched in handlers) is ``"{emoji} {text}"`` resolved from the DB override or the
hardcoded default. An admin can also set, per button:

* ``button_type`` — color: ``primary`` / ``success`` / ``danger`` (Bot API 9.4
  ``style``). ``None`` ⇒ the client's default button color.
* ``is_enabled`` — when ``False`` the button is hidden from the main menu.
* ``custom_emoji_id`` (+ ``emoji_text`` placeholder) — a premium (custom) emoji
  shown before the label (Bot API 9.4 ``icon_custom_emoji_id``).

This lets an admin restyle the menu without any code change.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.keyboards.style import VALID_STYLES
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
BTN_KEY_CONTACT = "contact"
BTN_KEY_ADMIN = "admin"

# Order of the main menu (admin appended only for admins, handled by the keyboard).
# Note: «🎧 پشتیبانی» (BTN_KEY_SUPPORT) is intentionally absent — the button is
# removed from the user menu. Its handler (app.handlers.support.tickets) and the
# BUTTON_DEFAULTS entry are kept so the support flow itself stays intact.
MAIN_MENU_KEYS: tuple[str, ...] = (
    BTN_KEY_BUY_DIAMOND,
    BTN_KEY_BUY_ACCOUNT,
    BTN_KEY_SELL_ACCOUNT,
    BTN_KEY_WALLET,
    BTN_KEY_REFERRAL,
    BTN_KEY_MY_ORDERS,
    BTN_KEY_CONTACT,
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
    BTN_KEY_CONTACT: ("📞", "راه‌های ارتباطی"),
    BTN_KEY_ADMIN: ("🛠", "پنل مدیریت"),
}

# Persian display names for the admin button-management section. «پشتیبانی» is
# omitted so the removed support button can't be re-styled/re-enabled from here.
BUTTON_LABELS: dict[str, str] = {
    BTN_KEY_BUY_DIAMOND: "خرید جم",
    BTN_KEY_BUY_ACCOUNT: "خرید اکانت",
    BTN_KEY_SELL_ACCOUNT: "فروش اکانت",
    BTN_KEY_WALLET: "کیف پول",
    BTN_KEY_REFERRAL: "زیرمجموعه‌گیری",
    BTN_KEY_MY_ORDERS: "سفارش‌های من",
    BTN_KEY_CONTACT: "راه‌های ارتباطی",
    BTN_KEY_ADMIN: "پنل مدیریت",
}


def _compose(emoji: str | None, text: str | None, key: str) -> str:
    d_emoji, d_text = BUTTON_DEFAULTS.get(key, ("", ""))
    e = emoji if emoji is not None else d_emoji
    t = text if text else d_text
    return f"{e} {t}".strip()


@dataclass(frozen=True)
class ButtonAppearance:
    """Resolved appearance for one main button (DB override merged on defaults)."""

    key: str
    label: str
    text: str
    emoji: str
    style: str | None
    custom_emoji_id: str | None
    emoji_text: str | None
    is_enabled: bool


def _appearance_from_row(key: str, row: ButtonSettings | None) -> ButtonAppearance:
    d_emoji, d_text = BUTTON_DEFAULTS.get(key, ("", ""))
    if row is None:
        return ButtonAppearance(
            key=key,
            label=f"{d_emoji} {d_text}".strip(),
            text=d_text,
            emoji=d_emoji,
            style=None,
            custom_emoji_id=None,
            emoji_text=None,
            is_enabled=True,
        )
    emoji = row.emoji if row.emoji is not None else d_emoji
    text = row.text if row.text else d_text
    style = row.button_type if row.button_type in VALID_STYLES else None
    return ButtonAppearance(
        key=key,
        label=f"{emoji} {text}".strip(),
        text=text,
        emoji=emoji,
        style=style,
        custom_emoji_id=row.custom_emoji_id or None,
        emoji_text=row.emoji_text or None,
        is_enabled=bool(row.is_enabled),
    )


class ButtonService:
    def __init__(self, repo: ButtonSettingsRepository) -> None:
        self.repo = repo
        self._cache: dict[str, ButtonAppearance] | None = None  # per-update cache

    def default_label(self, key: str) -> str:
        emoji, text = BUTTON_DEFAULTS.get(key, ("", ""))
        return f"{emoji} {text}".strip()

    async def all_appearances(self) -> dict[str, ButtonAppearance]:
        """key → resolved appearance for every known button (DB merged on default)."""
        if self._cache is None:
            rows = {r.key: r for r in await self.repo.all()}
            self._cache = {
                key: _appearance_from_row(key, rows.get(key))
                for key in BUTTON_DEFAULTS
            }
        return self._cache

    async def appearance(self, key: str) -> ButtonAppearance:
        return (await self.all_appearances()).get(
            key, _appearance_from_row(key, None)
        )

    async def all_labels(self) -> dict[str, str]:
        """key → full label for every known button (back-compat helper)."""
        return {k: a.label for k, a in (await self.all_appearances()).items()}

    async def label(self, key: str) -> str:
        return (await self.appearance(key)).label

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
        self._cache = None  # invalidate

    async def set_emoji(self, key: str, emoji: str) -> None:
        row = await self._ensure(key)
        row.emoji = emoji
        self._cache = None

    async def set_color(self, key: str, style: str | None) -> None:
        """Set the button color (``primary``/``success``/``danger`` or ``None``)."""
        row = await self._ensure(key)
        row.button_type = style if style in VALID_STYLES else None
        self._cache = None

    async def set_enabled(self, key: str, enabled: bool) -> None:
        row = await self._ensure(key)
        row.is_enabled = enabled
        self._cache = None

    async def set_premium_emoji(
        self, key: str, custom_emoji_id: str, emoji_text: str | None
    ) -> None:
        row = await self._ensure(key)
        row.custom_emoji_id = custom_emoji_id
        row.emoji_text = emoji_text
        self._cache = None

    async def clear_premium_emoji(self, key: str) -> None:
        row = await self.repo.get_by_key(key)
        if row is not None:
            row.custom_emoji_id = None
            row.emoji_text = None
            self._cache = None

    async def reset(self, key: str) -> bool:
        row = await self.repo.get_by_key(key)
        if row is None:
            return False
        await self.repo.delete(row)
        self._cache = None
        return True
