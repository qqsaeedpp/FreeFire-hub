"""Reply keyboards (main menus)."""
from __future__ import annotations

from aiogram.types import ReplyKeyboardMarkup
from aiogram.utils.keyboard import ReplyKeyboardBuilder

# Button labels (also matched in handlers via text filters)
BTN_BUY_DIAMOND = "💎 خرید جم"
BTN_BUY_ACCOUNT = "🛒 خرید اکانت"
BTN_SELL_ACCOUNT = "💰 فروش اکانت"
BTN_REQUEST_ACCOUNT = "📝 اکانت درخواستی"
BTN_WALLET = "👛 کیف پول"
BTN_REFERRAL = "🎁 زیرمجموعه‌گیری"
BTN_MY_ORDERS = "📦 سفارش‌های من"
BTN_SUPPORT = "🎧 پشتیبانی"
BTN_ADMIN = "🛠 پنل مدیریت"


def main_menu(is_admin: bool = False) -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    kb.button(text=BTN_BUY_DIAMOND)
    kb.button(text=BTN_BUY_ACCOUNT)
    kb.button(text=BTN_SELL_ACCOUNT)
    kb.button(text=BTN_REQUEST_ACCOUNT)
    kb.button(text=BTN_WALLET)
    kb.button(text=BTN_REFERRAL)
    kb.button(text=BTN_MY_ORDERS)
    kb.button(text=BTN_SUPPORT)
    if is_admin:
        kb.button(text=BTN_ADMIN)
    kb.adjust(2, 2, 2, 1, 1)
    return kb.as_markup(resize_keyboard=True)


def cancel_menu() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    kb.button(text="❌ لغو")
    return kb.as_markup(resize_keyboard=True)
