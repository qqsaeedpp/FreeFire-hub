"""Reply keyboards (main menus)."""
from __future__ import annotations

from typing import TYPE_CHECKING

from aiogram.types import ReplyKeyboardMarkup
from aiogram.utils.keyboard import ReplyKeyboardBuilder

from app.services.button_service import (
    BTN_KEY_ADMIN,
    BTN_KEY_BUY_ACCOUNT,
    BTN_KEY_BUY_DIAMOND,
    BTN_KEY_MY_ORDERS,
    BTN_KEY_REFERRAL,
    BTN_KEY_SELL_ACCOUNT,
    BTN_KEY_SUPPORT,
    BTN_KEY_WALLET,
    BUTTON_DEFAULTS,
    MAIN_MENU_KEYS,
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
    """Build the main reply keyboard.

    ``labels`` is a key→label mapping (DB overrides). Missing keys fall back to
    the hardcoded defaults so the keyboard always renders.
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
    kb.button(text=lbl(BTN_KEY_SUPPORT))
    if is_admin:
        kb.button(text=lbl(BTN_KEY_ADMIN))
    kb.adjust(2, 2, 2, 1)
    return kb.as_markup(resize_keyboard=True)


async def build_main_menu(
    services: "Services", is_admin: bool = False
) -> ReplyKeyboardMarkup:
    """Async helper: render the main menu using DB-editable labels."""
    labels = await services.button.all_labels()
    return main_menu(is_admin=is_admin, labels=labels)


def cancel_menu() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    kb.button(text="❌ لغو")
    return kb.as_markup(resize_keyboard=True)
