"""Inline keyboards used across flows."""
from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.core.constants import LoginMethod
from app.keyboards.callbacks import (
    AccountCB,
    AdminOrderCB,
    DiamondCB,
    LoginMethodCB,
    NavCB,
    TicketCB,
)
from app.services.diamond_service import DiamondPlan
from app.utils.helpers import format_toman


def back_cancel(target: str = "main") -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ بازگشت", callback_data=NavCB(action="back", target=target))
    kb.button(text="❌ لغو", callback_data=NavCB(action="cancel"))
    kb.adjust(2)
    return kb.as_markup()


def cancel_only() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="❌ لغو", callback_data=NavCB(action="cancel"))
    return kb.as_markup()


def diamond_method_menu() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🆔 خرید با UID", callback_data=DiamondCB(action="method", value="uid"))
    kb.button(
        text="🔐 خرید با اطلاعات اکانت",
        callback_data=DiamondCB(action="method", value="account"),
    )
    kb.button(text="❌ لغو", callback_data=NavCB(action="cancel"))
    kb.adjust(1)
    return kb.as_markup()


def diamond_plans_menu(plans: list[DiamondPlan]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for plan in plans:
        kb.button(
            text=f"{plan.name} — {format_toman(plan.price)}",
            callback_data=DiamondCB(action="plan", value=plan.code),
        )
    kb.button(text="❌ لغو", callback_data=NavCB(action="cancel"))
    kb.adjust(1)
    return kb.as_markup()


def login_method_menu() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    labels = {
        LoginMethod.GUEST: "👤 مهمان",
        LoginMethod.FACEBOOK: "📘 فیسبوک",
        LoginMethod.GOOGLE: "🔴 گوگل",
        LoginMethod.VK: "🔵 VK",
        LoginMethod.TWITTER: "🐦 توییتر",
        LoginMethod.APPLE: "🍎 اپل",
    }
    for method, label in labels.items():
        kb.button(text=label, callback_data=LoginMethodCB(method=method.value))
    kb.button(text="❌ لغو", callback_data=NavCB(action="cancel"))
    kb.adjust(2)
    return kb.as_markup()


def accounts_list_menu(accounts, page: int, total_pages: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for acc in accounts:
        kb.button(
            text=f"#{acc.id} | لول {acc.level} | {format_toman(acc.price)}",
            callback_data=AccountCB(action="view", account_id=acc.id, page=page),
        )
    kb.adjust(1)

    nav = InlineKeyboardBuilder()
    if page > 1:
        nav.button(text="⬅️ قبلی", callback_data=AccountCB(action="page", page=page - 1))
    nav.button(text=f"{page}/{total_pages}", callback_data=NavCB(action="noop"))
    if page < total_pages:
        nav.button(text="بعدی ➡️", callback_data=AccountCB(action="page", page=page + 1))
    kb.attach(nav)

    tail = InlineKeyboardBuilder()
    tail.button(text="❌ بستن", callback_data=NavCB(action="cancel"))
    kb.attach(tail)
    return kb.as_markup()


def account_detail_menu(account_id: int, page: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(
        text="✅ خرید این اکانت",
        callback_data=AccountCB(action="buy", account_id=account_id),
    )
    kb.button(
        text="⬅️ بازگشت به لیست",
        callback_data=AccountCB(action="page", page=page),
    )
    kb.adjust(1)
    return kb.as_markup()


def pay_options(order_id: int, can_use_wallet: bool) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🧾 پرداخت کارت‌به‌کارت", callback_data=NavCB(action="pay_card"))
    if can_use_wallet:
        kb.button(text="👛 پرداخت از کیف پول", callback_data=NavCB(action="pay_wallet"))
    kb.button(text="❌ لغو", callback_data=NavCB(action="cancel"))
    kb.adjust(1)
    return kb.as_markup()


def admin_order_review(order_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ تایید", callback_data=AdminOrderCB(action="approve", order_id=order_id))
    kb.button(text="❌ رد", callback_data=AdminOrderCB(action="reject", order_id=order_id))
    kb.button(
        text="🏁 تکمیل سفارش", callback_data=AdminOrderCB(action="complete", order_id=order_id)
    )
    kb.adjust(2, 1)
    return kb.as_markup()


def ticket_actions(ticket_id: int, is_admin: bool) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="💬 پاسخ", callback_data=TicketCB(action="reply", ticket_id=ticket_id))
    kb.button(text="🔒 بستن تیکت", callback_data=TicketCB(action="close", ticket_id=ticket_id))
    kb.adjust(2)
    return kb.as_markup()
