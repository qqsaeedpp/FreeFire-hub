"""Reply keyboards (main menus)."""
from __future__ import annotations

from typing import TYPE_CHECKING

from aiogram.types import ReplyKeyboardMarkup
from aiogram.utils.keyboard import ReplyKeyboardBuilder

from app.keyboards.style import style_kwargs
from app.services.button_service import (
    BTN_KEY_ADMIN,
    BTN_KEY_BUY_ACCOUNT,
    BTN_KEY_BUY_DIAMOND,
    BTN_KEY_CONTACT,
    BTN_KEY_MY_ORDERS,
    BTN_KEY_REFERRAL,
    BTN_KEY_SELL_ACCOUNT,
    BTN_KEY_WALLET,
    BUTTON_DEFAULTS,
    MAIN_MENU_KEYS,
    ButtonAppearance,
)

if TYPE_CHECKING:
    from app.container import Services

# Hardcoded button labels (fallbacks; the live labels come from the DB via
# ButtonService). Kept for back-compat and for non-service call sites.
BTN_BUY_DIAMOND = "💎 خرید جم"
BTN_BUY_ACCOUNT = "🛒 خرید اکانت"
BTN_SELL_ACCOUNT = "💰 فروش اکانت"
BTN_REQUEST_ACCOUNT = "📝 اکانت درخواستی"
BTN_WALLET = "👛 کیف پول"
BTN_REFERRAL = "🎁 زیرمجموعه‌گیری"
BTN_MY_ORDERS = "📦 سفارش‌های من"
BTN_SUPPORT = "🎧 پشتیبانی"
BTN_ADMIN = "🛠 پنل مدیریت"


BTN_MAIN = "🏠 منوی اصلی"
BTN_CANCEL = "❌ لغو"


def _default_label(key: str) -> str:
    emoji, text = BUTTON_DEFAULTS.get(key, ("", ""))
    return f"{emoji} {text}".strip()


# Static fallback set of main-menu labels (used when no Services is available,
# e.g. MenuResetMiddleware falls back to this). The live set is computed from
# the DB in build_main_menu / MenuResetMiddleware.
MAIN_MENU_TEXTS: frozenset[str] = frozenset(
    {_default_label(k) for k in MAIN_MENU_KEYS}
    | {_default_label(BTN_KEY_ADMIN), BTN_MAIN}
)


def main_menu(
    is_admin: bool = False, labels: dict[str, str] | None = None
) -> ReplyKeyboardMarkup:
    """Build the main reply keyboard from plain labels (fallback path).

    ``labels`` is a key→label mapping (DB overrides). Missing keys fall back to
    the hardcoded defaults so the keyboard always renders. Used when no
    ``Services`` is available; the rich path is :func:`build_main_menu`.

    Layout follows the design image: «خرید جم» alone on the top row, then the
    remaining buttons two-per-row, and the admin button alone at the bottom.
    """

    def lbl(key: str) -> str:
        if labels and labels.get(key):
            return labels[key]
        return _default_label(key)

    kb = ReplyKeyboardBuilder()
    kb.button(text=lbl(BTN_KEY_BUY_DIAMOND))
    kb.button(text=lbl(BTN_KEY_BUY_ACCOUNT))
    kb.button(text=lbl(BTN_KEY_SELL_ACCOUNT))
    kb.button(text=lbl(BTN_KEY_WALLET))
    kb.button(text=lbl(BTN_KEY_REFERRAL))
    kb.button(text=lbl(BTN_KEY_MY_ORDERS))
    kb.button(text=lbl(BTN_KEY_CONTACT))
    if is_admin:
        kb.button(text=lbl(BTN_KEY_ADMIN))
        kb.adjust(1, 2, 2, 2, 1)
    else:
        kb.adjust(1, 2, 2, 2)
    return kb.as_markup(resize_keyboard=True)


def _main_menu_from_appearances(
    appearances: dict[str, ButtonAppearance], is_admin: bool
) -> ReplyKeyboardMarkup:
    """Render the main menu honoring color, premium emoji and enabled flags.

    Disabled buttons are hidden. «خرید جم» (when enabled) headlines its own row;
    the rest flow two-per-row; «پنل مدیریت» sits alone at the bottom for admins.
    """
    kb = ReplyKeyboardBuilder()
    rows: list[int] = []

    diamond = appearances.get(BTN_KEY_BUY_DIAMOND)
    headline = diamond is not None and diamond.is_enabled
    if headline:
        kb.button(
            text=diamond.label,
            **style_kwargs(diamond.style, diamond.custom_emoji_id),
        )
        rows.append(1)

    rest = [
        appearances[k]
        for k in MAIN_MENU_KEYS
        if k != BTN_KEY_BUY_DIAMOND
        and k in appearances
        and appearances[k].is_enabled
    ]
    for ap in rest:
        kb.button(text=ap.label, **style_kwargs(ap.style, ap.custom_emoji_id))
    # Two-per-row for the remaining buttons (a trailing odd one gets its own row).
    for _ in range(len(rest) // 2):
        rows.append(2)
    if len(rest) % 2:
        rows.append(1)

    if is_admin:
        admin = appearances.get(BTN_KEY_ADMIN)
        if admin is not None and admin.is_enabled:
            kb.button(
                text=admin.label,
                **style_kwargs(admin.style, admin.custom_emoji_id),
            )
            rows.append(1)

    if rows:
        kb.adjust(*rows)
    return kb.as_markup(resize_keyboard=True)


async def build_main_menu(
    services: "Services", is_admin: bool = False
) -> ReplyKeyboardMarkup:
    """Async helper: render the main menu using DB-editable appearance."""
    appearances = await services.button.all_appearances()
    return _main_menu_from_appearances(appearances, is_admin)


def cancel_menu() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    kb.button(text="❌ لغو")
    return kb.as_markup(resize_keyboard=True)


BTN_SEND_CONTACT = "📱 ارسال شماره تلفن من"


def request_contact_menu() -> ReplyKeyboardMarkup:
    """Keyboard whose single button shares the sender's own phone number.

    ``request_contact`` is the only way to obtain a number Telegram itself
    vouches for (the resulting contact carries a ``user_id`` equal to the
    sender's). It is valid in private chats only, so callers must not offer it
    in groups.
    """
    kb = ReplyKeyboardBuilder()
    kb.button(text=BTN_SEND_CONTACT, request_contact=True)
    return kb.as_markup(resize_keyboard=True, one_time_keyboard=True)
