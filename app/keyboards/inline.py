"""Inline keyboards used across flows."""
from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.keyboards.callbacks import (
    AccountCB,
    AdminAccountCB,
    AdminCB,
    AdminOrderCB,
    AdminRequestedCB,
    AdminSaleCB,
    DiamondCB,
    DiscountCB,
    NavCB,
    PayMethodCB,
    TicketCB,
    TutorialCB,
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


def backup_code_menu(tutorial_key: str) -> InlineKeyboardMarkup:
    """Backup-code prompt keyboard: a tutorial-video button above cancel."""
    kb = InlineKeyboardBuilder()
    kb.button(
        text="🎥 آموزش گرفتن Backup Code گوگل",
        callback_data=TutorialCB(action="watch", key=tutorial_key),
    )
    kb.button(text="❌ لغو", callback_data=NavCB(action="cancel"))
    kb.adjust(1)
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
    kb.button(text="⬅️ بازگشت", callback_data=NavCB(action="back", target="diamond_method"))
    kb.button(text="❌ لغو", callback_data=NavCB(action="cancel"))
    kb.adjust(1)
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


def discount_prompt_menu() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🎟 بله، کد دارم", callback_data=DiscountCB(action="have"))
    kb.button(text="ادامه بدون کد ➡️", callback_data=DiscountCB(action="skip"))
    kb.button(text="❌ لغو", callback_data=NavCB(action="cancel"))
    kb.adjust(1)
    return kb.as_markup()


def payment_method_menu(*, can_use_wallet: bool = False) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="💳 پرداخت آنلاین", callback_data=PayMethodCB(method="online"))
    kb.button(text="🏦 کارت به کارت", callback_data=PayMethodCB(method="card_to_card"))
    if can_use_wallet:
        kb.button(text="👛 پرداخت از کیف پول", callback_data=PayMethodCB(method="wallet"))
    kb.button(text="❌ لغو", callback_data=NavCB(action="cancel"))
    kb.adjust(1)
    return kb.as_markup()


def admin_sale_review(account_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ خرید اکانت", callback_data=AdminSaleCB(action="buy", account_id=account_id))
    kb.button(
        text="📋 افزودن به لیست فروش",
        callback_data=AdminSaleCB(action="list", account_id=account_id),
    )
    kb.adjust(1)
    return kb.as_markup()


def manage_accounts_menu(accounts, page: int, total_pages: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for acc in accounts:
        kb.button(
            text=f"#{acc.id} | {format_toman(acc.price)}",
            callback_data=AdminAccountCB(action="view", account_id=acc.id, page=page),
        )
    kb.adjust(1)

    nav = InlineKeyboardBuilder()
    if page > 1:
        nav.button(text="⬅️ قبلی", callback_data=AdminAccountCB(action="page", page=page - 1))
    nav.button(text=f"{page}/{total_pages}", callback_data=NavCB(action="noop"))
    if page < total_pages:
        nav.button(text="بعدی ➡️", callback_data=AdminAccountCB(action="page", page=page + 1))
    kb.attach(nav)

    tail = InlineKeyboardBuilder()
    tail.button(text="⬅️ بازگشت به پنل", callback_data=AdminCB(action="back_home"))
    kb.attach(tail)
    return kb.as_markup()


def manage_account_detail_menu(account_id: int, page: int, is_hidden: bool) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="💵 ویرایش قیمت", callback_data=AdminAccountCB(action="edit_price", account_id=account_id, page=page))
    kb.button(text="✏️ ویرایش عنوان", callback_data=AdminAccountCB(action="edit_title", account_id=account_id, page=page))
    if is_hidden:
        kb.button(text="👁 نمایش در فروشگاه", callback_data=AdminAccountCB(action="unhide", account_id=account_id, page=page))
    else:
        kb.button(text="🙈 مخفی‌کردن", callback_data=AdminAccountCB(action="hide", account_id=account_id, page=page))
    kb.button(text="🗑 حذف", callback_data=AdminAccountCB(action="delete", account_id=account_id, page=page))
    kb.button(text="⬅️ بازگشت به لیست", callback_data=AdminAccountCB(action="page", page=page))
    kb.adjust(2, 1, 1, 1)
    return kb.as_markup()


def manage_account_delete_confirm(account_id: int, page: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(
        text="✅ بله، حذف شود",
        callback_data=AdminAccountCB(action="confirm_delete", account_id=account_id, page=page),
    )
    kb.button(
        text="❌ انصراف",
        callback_data=AdminAccountCB(action="view", account_id=account_id, page=page),
    )
    kb.adjust(1)
    return kb.as_markup()


def admin_order_review(order_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ تایید", callback_data=AdminOrderCB(action="approve", order_id=order_id))
    kb.button(text="❌ رد", callback_data=AdminOrderCB(action="reject", order_id=order_id))
    kb.button(
        text="🏁 تکمیل سفارش", callback_data=AdminOrderCB(action="complete", order_id=order_id)
    )
    kb.button(
        text="👁 جزئیات سفارش", callback_data=AdminOrderCB(action="details", order_id=order_id)
    )
    kb.adjust(2, 1, 1)
    return kb.as_markup()


def pending_orders_menu(orders, page: int, total_pages: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for o in orders:
        kb.button(
            text=f"#{o.id} | {format_toman(o.amount)}",
            callback_data=AdminOrderCB(action="open", order_id=o.id, page=page),
        )
    kb.adjust(1)

    nav = InlineKeyboardBuilder()
    if page > 1:
        nav.button(text="⬅️ قبلی", callback_data=AdminOrderCB(action="page", page=page - 1))
    nav.button(text=f"{page}/{total_pages}", callback_data=NavCB(action="noop"))
    if page < total_pages:
        nav.button(text="بعدی ➡️", callback_data=AdminOrderCB(action="page", page=page + 1))
    kb.attach(nav)

    tail = InlineKeyboardBuilder()
    tail.button(text="⬅️ بازگشت به پنل", callback_data=AdminCB(action="back_home"))
    kb.attach(tail)
    return kb.as_markup()


def pending_order_actions(order_id: int, page: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ تایید", callback_data=AdminOrderCB(action="approve", order_id=order_id, page=page))
    kb.button(text="❌ رد", callback_data=AdminOrderCB(action="reject", order_id=order_id, page=page))
    kb.button(text="🏁 تکمیل سفارش", callback_data=AdminOrderCB(action="complete", order_id=order_id, page=page))
    kb.button(text="👁 جزئیات", callback_data=AdminOrderCB(action="details", order_id=order_id, page=page))
    kb.button(text="⬅️ بازگشت به لیست", callback_data=AdminOrderCB(action="page", page=page))
    kb.adjust(2, 1, 1, 1)
    return kb.as_markup()


def requested_deposit_review(req_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(
        text="✅ تایید بیعانه",
        callback_data=AdminRequestedCB(action="approve_deposit", req_id=req_id),
    )
    kb.button(
        text="❌ رد بیعانه",
        callback_data=AdminRequestedCB(action="reject_deposit", req_id=req_id),
    )
    kb.adjust(2)
    return kb.as_markup()


def requested_accounts_menu(items, page: int, total_pages: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for req in items:
        kb.button(
            text=f"#{req.id} | {format_toman(req.target_price)}",
            callback_data=AdminRequestedCB(action="view", req_id=req.id, page=page),
        )
    kb.adjust(1)

    nav = InlineKeyboardBuilder()
    if page > 1:
        nav.button(text="⬅️ قبلی", callback_data=AdminRequestedCB(action="page", page=page - 1))
    nav.button(text=f"{page}/{total_pages}", callback_data=NavCB(action="noop"))
    if page < total_pages:
        nav.button(text="بعدی ➡️", callback_data=AdminRequestedCB(action="page", page=page + 1))
    kb.attach(nav)

    tail = InlineKeyboardBuilder()
    tail.button(text="⬅️ بازگشت به پنل", callback_data=AdminCB(action="back_home"))
    kb.attach(tail)
    return kb.as_markup()


def requested_account_detail_menu(req_id: int, page: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🗑 حذف", callback_data=AdminRequestedCB(action="delete", req_id=req_id, page=page))
    kb.button(text="⬅️ بازگشت به لیست", callback_data=AdminRequestedCB(action="page", page=page))
    kb.adjust(1)
    return kb.as_markup()


def requested_account_delete_confirm(req_id: int, page: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(
        text="✅ بله، حذف شود",
        callback_data=AdminRequestedCB(action="confirm_delete", req_id=req_id, page=page),
    )
    kb.button(
        text="❌ انصراف",
        callback_data=AdminRequestedCB(action="view", req_id=req_id, page=page),
    )
    kb.adjust(1)
    return kb.as_markup()


def ticket_actions(ticket_id: int, is_admin: bool) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="💬 پاسخ", callback_data=TicketCB(action="reply", ticket_id=ticket_id))
    kb.button(text="🔒 بستن تیکت", callback_data=TicketCB(action="close", ticket_id=ticket_id))
    kb.adjust(2)
    return kb.as_markup()
