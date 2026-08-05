"""Inline keyboards used across flows.

Layout conventions (item 3 — glass-button redesign):
* primary call-to-action buttons use the 🔵 ``primary`` color;
* confirm/approve use 🟢 ``success``; reject/delete use 🔴 ``danger``;
* approve & reject sit side-by-side; pagination gets its own row;
* the back / cancel button is always last (bottom).

Colors come from Bot API 9.4's ``style`` field (see ``app.keyboards.style``).
"""
from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.keyboards.callbacks import (
    AccountCB,
    AdminAccountCB,
    AdminCB,
    AdminOrderCB,
    AdminReferrerCB,
    AdminRequestedCB,
    AdminSaleCB,
    DiamondCB,
    DiscountCB,
    NavCB,
    PayMethodCB,
    TicketCB,
    TutorialCB,
    VerificationCB,
    WalletTopUpCB,
)
from app.keyboards.style import (
    STYLE_DANGER,
    STYLE_PRIMARY,
    STYLE_SUCCESS,
    style_kwargs,
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


def captcha_menu(nonce: str, options) -> InlineKeyboardMarkup:
    """The four answer buttons for one math captcha, on a single row.

    Only the challenge ``nonce`` and the tapped number travel in the callback —
    the correct answer stays server-side in Redis, so it cannot be read off the
    button payload.
    """
    kb = InlineKeyboardBuilder()
    for option in options:
        kb.button(
            text=str(option),
            callback_data=VerificationCB(
                action="answer", nonce=nonce, choice=option
            ),
        )
    kb.adjust(4)
    return kb.as_markup()


def backup_code_menu(tutorial_key: str) -> InlineKeyboardMarkup:
    """Backup-code prompt keyboard: a tutorial-video button above cancel."""
    kb = InlineKeyboardBuilder()
    kb.button(
        text="🎥 آموزش گرفتن Backup Code گوگل",
        callback_data=TutorialCB(action="watch", key=tutorial_key),
        **style_kwargs(STYLE_PRIMARY),
    )
    kb.button(text="❌ لغو", callback_data=NavCB(action="cancel"))
    kb.adjust(1)
    return kb.as_markup()


def diamond_method_menu() -> InlineKeyboardMarkup:
    """Step 1 of buying diamonds: choose the purchase method (UID vs account)."""
    kb = InlineKeyboardBuilder()
    kb.button(
        text="🆔 خرید با UID",
        callback_data=DiamondCB(action="method", value="uid"),
        **style_kwargs(STYLE_PRIMARY),
    )
    kb.button(
        text="🔐 خرید با اطلاعات اکانت",
        callback_data=DiamondCB(action="method", value="account"),
        **style_kwargs(STYLE_PRIMARY),
    )
    kb.adjust(1)
    tail = InlineKeyboardBuilder()
    tail.button(text="❌ لغو", callback_data=NavCB(action="cancel"))
    kb.attach(tail)
    return kb.as_markup()


def diamond_save_type_menu() -> InlineKeyboardMarkup:
    """Account-credentials flow: pick the game save service before email."""
    kb = InlineKeyboardBuilder()
    kb.button(
        text="📘 فیسبوک",
        callback_data=DiamondCB(action="save_type", value="facebook"),
        **style_kwargs(STYLE_PRIMARY),
    )
    kb.button(
        text="🟣 ویکی / VK",
        callback_data=DiamondCB(action="save_type", value="vk"),
        **style_kwargs(STYLE_PRIMARY),
    )
    kb.button(
        text="🟢 جیمیل",
        callback_data=DiamondCB(action="save_type", value="google"),
        **style_kwargs(STYLE_PRIMARY),
    )
    kb.adjust(1)
    tail = InlineKeyboardBuilder()
    tail.button(text="❌ لغو", callback_data=NavCB(action="cancel"))
    kb.attach(tail)
    return kb.as_markup()


def diamond_category_menu() -> InlineKeyboardMarkup:
    """Step 2 (UID only): choose between buying gems or a level-up offer."""
    kb = InlineKeyboardBuilder()
    kb.button(
        text="💎 خرید جم",
        callback_data=DiamondCB(action="category", value="diamond"),
        **style_kwargs(STYLE_PRIMARY),
    )
    kb.button(
        text="💫 لول اپ",
        callback_data=DiamondCB(action="category", value="levelup"),
        **style_kwargs(STYLE_PRIMARY),
    )
    kb.adjust(1)
    tail = InlineKeyboardBuilder()
    tail.button(text="⬅️ بازگشت", callback_data=NavCB(action="back", target="diamond_method"))
    tail.button(text="❌ لغو", callback_data=NavCB(action="cancel"))
    tail.adjust(2)
    kb.attach(tail)
    return kb.as_markup()


def _short_toman(amount: int) -> str:
    """Compact money label for tight button rows: ``850,000 ت``."""
    return f"{amount:,} ت"


def diamond_plan_menu(
    plans: list[DiamondPlan],
    *,
    back_target: str,
    emoji: str = "💎",
    sizes: tuple[int, ...] | None = None,
    short_price: bool = False,
) -> InlineKeyboardMarkup:
    """Final step: pick a concrete plan from the given category.

    ``sizes`` controls the row layout (buttons-per-row). Pass ``(2,)`` for a
    responsive two-column grid, or an explicit tuple like ``(2, 1, 2, 2, 2)`` to
    pin a precise arrangement. Defaults to one plan per row.

    ``short_price`` renders the price with the compact ``ت`` suffix instead of
    the full ``تومان`` — useful for the dense two-column account grid.
    """
    money = _short_toman if short_price else format_toman
    kb = InlineKeyboardBuilder()
    for plan in plans:
        kb.button(
            text=f"{emoji} {plan.name} — {money(plan.price)}",
            callback_data=DiamondCB(action="plan", value=plan.code),
            **style_kwargs(STYLE_PRIMARY),
        )
    if sizes:
        kb.adjust(*sizes)
    else:
        kb.adjust(1)
    tail = InlineKeyboardBuilder()
    tail.button(text="⬅️ بازگشت", callback_data=NavCB(action="back", target=back_target))
    tail.button(text="❌ لغو", callback_data=NavCB(action="cancel"))
    tail.adjust(2)
    kb.attach(tail)
    return kb.as_markup()


def diamond_levelup_menu(
    plans: list[DiamondPlan],
    selected: set[str],
    *,
    all_price: int,
    back_target: str,
) -> InlineKeyboardMarkup:
    """Level-Up multi-select: tap to toggle each offer, then confirm or buy-all.

    Selected offers are prefixed with ✅; the running total of the current
    selection is shown on the confirm button. A separate "buy all" button picks
    the whole catalog at the admin-configured bundle price.
    """
    kb = InlineKeyboardBuilder()
    for plan in plans:
        mark = "✅" if plan.code in selected else "▫️"
        kb.button(
            text=f"{mark} {plan.name} — {format_toman(plan.price)}",
            callback_data=DiamondCB(action="lvl_toggle", value=plan.code),
            **style_kwargs(STYLE_PRIMARY if plan.code in selected else None),
        )
    kb.adjust(2)

    actions = InlineKeyboardBuilder()
    total = sum(p.price for p in plans if p.code in selected)
    if selected:
        actions.button(
            text=f"💳 خرید انتخاب‌شده‌ها ({format_toman(total)})",
            callback_data=DiamondCB(action="lvl_done"),
            **style_kwargs(STYLE_SUCCESS),
        )
    actions.button(
        text=f"🛒 خرید همه ({format_toman(all_price)})",
        callback_data=DiamondCB(action="lvl_all"),
        **style_kwargs(STYLE_SUCCESS),
    )
    actions.adjust(1)
    kb.attach(actions)

    tail = InlineKeyboardBuilder()
    tail.button(text="⬅️ بازگشت", callback_data=NavCB(action="back", target=back_target))
    tail.button(text="❌ لغو", callback_data=NavCB(action="cancel"))
    tail.adjust(2)
    kb.attach(tail)
    return kb.as_markup()


def buy_account_menu() -> InlineKeyboardMarkup:
    """Buy-account submenu: ready-made shop list vs. a requested (wanted) account."""
    kb = InlineKeyboardBuilder()
    kb.button(
        text="📦 لیست اکانت‌های آماده",
        callback_data=AccountCB(action="ready"),
        **style_kwargs(STYLE_PRIMARY),
    )
    kb.button(
        text="🎯 اکانت درخواستی",
        callback_data=AccountCB(action="requested"),
        **style_kwargs(STYLE_PRIMARY),
    )
    kb.adjust(1)
    tail = InlineKeyboardBuilder()
    tail.button(text="❌ بستن", callback_data=NavCB(action="cancel"))
    kb.attach(tail)
    return kb.as_markup()


def new_listing_announce_menu() -> InlineKeyboardMarkup:
    """Glass CTA under a public «اکانت جدید» broadcast → opens the ready-made shop
    list (the same ``AccountCB(action="ready")`` the buy-account submenu uses)."""
    kb = InlineKeyboardBuilder()
    kb.button(
        text="🛒 مشاهده اکانت‌ها",
        callback_data=AccountCB(action="ready"),
        **style_kwargs(STYLE_PRIMARY),
    )
    return kb.as_markup()


def _pagination_row(cb_factory, action: str, page: int, total_pages: int):
    """Build a one-row pagination builder: «قبلی  |  page/total  |  بعدی»."""
    nav = InlineKeyboardBuilder()
    if page > 1:
        nav.button(text="⬅️ قبلی", callback_data=cb_factory(action=action, page=page - 1))
    nav.button(text=f"{page}/{total_pages}", callback_data=NavCB(action="noop"))
    if page < total_pages:
        nav.button(text="بعدی ➡️", callback_data=cb_factory(action=action, page=page + 1))
    return nav


def _pagination_row_kind(cb_factory, action: str, page: int, total_pages: int, kind, group=None):
    """Like :func:`_pagination_row`, but threads ``kind`` + ``group`` through."""
    nav = InlineKeyboardBuilder()
    if page > 1:
        nav.button(text="⬅️ قبلی", callback_data=cb_factory(action=action, page=page - 1, kind=kind, group=group))
    nav.button(text=f"{page}/{total_pages}", callback_data=NavCB(action="noop"))
    if page < total_pages:
        nav.button(text="بعدی ➡️", callback_data=cb_factory(action=action, page=page + 1, kind=kind, group=group))
    return nav


def accounts_list_menu(accounts, page: int, total_pages: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for acc in accounts:
        kb.button(
            text=f"#{acc.id} | {acc.title} | {format_toman(acc.price)}",
            callback_data=AccountCB(action="view", account_id=acc.id, page=page),
        )
    kb.adjust(1)
    kb.attach(_pagination_row(AccountCB, "page", page, total_pages))

    tail = InlineKeyboardBuilder()
    tail.button(text="❌ بستن", callback_data=NavCB(action="cancel"))
    kb.attach(tail)
    return kb.as_markup()


def account_detail_menu(account_id: int, page: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(
        text="✅ خرید این اکانت",
        callback_data=AccountCB(action="buy", account_id=account_id),
        **style_kwargs(STYLE_SUCCESS),
    )
    kb.button(
        text="⬅️ بازگشت به لیست",
        callback_data=AccountCB(action="page", page=page),
    )
    kb.adjust(1)
    return kb.as_markup()


def pay_options(order_id: int, can_use_wallet: bool) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(
        text="🧾 پرداخت کارت‌به‌کارت",
        callback_data=NavCB(action="pay_card"),
        **style_kwargs(STYLE_PRIMARY),
    )
    if can_use_wallet:
        kb.button(
            text="👛 پرداخت از کیف پول",
            callback_data=NavCB(action="pay_wallet"),
            **style_kwargs(STYLE_SUCCESS),
        )
    kb.button(text="❌ لغو", callback_data=NavCB(action="cancel"))
    kb.adjust(1)
    return kb.as_markup()


def discount_prompt_menu() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(
        text="🎟 بله، کد دارم",
        callback_data=DiscountCB(action="have"),
        **style_kwargs(STYLE_PRIMARY),
    )
    kb.button(text="ادامه بدون کد ➡️", callback_data=DiscountCB(action="skip"))
    kb.button(text="❌ لغو", callback_data=NavCB(action="cancel"))
    kb.adjust(1)
    return kb.as_markup()


def payment_method_menu(*, can_use_wallet: bool = False) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(
        text="💳 پرداخت آنلاین",
        callback_data=PayMethodCB(method="online"),
        **style_kwargs(STYLE_PRIMARY),
    )
    kb.button(
        text="🏦 کارت به کارت",
        callback_data=PayMethodCB(method="card_to_card"),
        **style_kwargs(STYLE_PRIMARY),
    )
    if can_use_wallet:
        kb.button(
            text="👛 پرداخت از کیف پول",
            callback_data=PayMethodCB(method="wallet"),
            **style_kwargs(STYLE_SUCCESS),
        )
    kb.button(text="❌ لغو", callback_data=NavCB(action="cancel"))
    kb.adjust(1)
    return kb.as_markup()


def _sale_action_buttons(kb: InlineKeyboardBuilder, account_id: int, page: int) -> None:
    """The three shared sale-decision buttons (notification card + list detail).

    ``page=0`` marks the instant-notification card; ``page>=1`` carries the list
    page so the handler can refresh «📦 سفارشات فروش اکانت کاربران» in place.
    """
    kb.button(
        text="📋 افزودن به لیست فروش",
        callback_data=AdminSaleCB(action="list", account_id=account_id, page=page),
        **style_kwargs(STYLE_PRIMARY),
    )
    kb.button(
        text="💰 خرید اکانت توسط ادمین",
        callback_data=AdminSaleCB(action="buy", account_id=account_id, page=page),
        **style_kwargs(STYLE_SUCCESS),
    )
    kb.button(
        text="❌ رد درخواست",
        callback_data=AdminSaleCB(action="reject", account_id=account_id, page=page),
        **style_kwargs(STYLE_DANGER),
    )


def admin_sale_review(account_id: int) -> InlineKeyboardMarkup:
    """Buttons under the instant new-listing notification (page=0 sentinel)."""
    kb = InlineKeyboardBuilder()
    _sale_action_buttons(kb, account_id, page=0)
    kb.adjust(1)
    return kb.as_markup()


def pending_sales_menu(accounts, page: int, total_pages: int) -> InlineKeyboardMarkup:
    """List of user listings awaiting review — «📦 سفارشات فروش اکانت کاربران»."""
    kb = InlineKeyboardBuilder()
    for acc in accounts:
        kb.button(
            text=f"#{acc.id} | {acc.title} | {format_toman(acc.price)}",
            callback_data=AdminSaleCB(action="open", account_id=acc.id, page=page),
        )
    kb.adjust(1)
    kb.attach(_pagination_row(AdminSaleCB, "page", page, total_pages))

    tail = InlineKeyboardBuilder()
    tail.button(text="⬅️ بازگشت به پنل", callback_data=AdminCB(action="back_home"))
    kb.attach(tail)
    return kb.as_markup()


def pending_sale_actions(account_id: int, page: int) -> InlineKeyboardMarkup:
    """Decision buttons for a single listing opened from the review list."""
    kb = InlineKeyboardBuilder()
    _sale_action_buttons(kb, account_id, page=max(1, page))
    kb.button(
        text="⬅️ بازگشت به لیست",
        callback_data=AdminSaleCB(action="page", page=max(1, page)),
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
    kb.attach(_pagination_row(AdminAccountCB, "page", page, total_pages))

    tail = InlineKeyboardBuilder()
    tail.button(text="⬅️ بازگشت به پنل", callback_data=AdminCB(action="back_home"))
    kb.attach(tail)
    return kb.as_markup()


def manage_account_detail_menu(account_id: int, page: int, is_hidden: bool) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="💵 ویرایش قیمت", callback_data=AdminAccountCB(action="edit_price", account_id=account_id, page=page), **style_kwargs(STYLE_PRIMARY))
    kb.button(text="✏️ ویرایش عنوان", callback_data=AdminAccountCB(action="edit_title", account_id=account_id, page=page), **style_kwargs(STYLE_PRIMARY))
    if is_hidden:
        kb.button(text="👁 نمایش در فروشگاه", callback_data=AdminAccountCB(action="unhide", account_id=account_id, page=page), **style_kwargs(STYLE_SUCCESS))
    else:
        kb.button(text="🙈 مخفی‌کردن", callback_data=AdminAccountCB(action="hide", account_id=account_id, page=page))
    kb.button(text="🗑 حذف", callback_data=AdminAccountCB(action="delete", account_id=account_id, page=page), **style_kwargs(STYLE_DANGER))
    kb.button(text="⬅️ بازگشت به لیست", callback_data=AdminAccountCB(action="page", page=page))
    kb.adjust(2, 1, 1, 1)
    return kb.as_markup()


def manage_account_delete_confirm(account_id: int, page: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(
        text="🗑 بله، حذف شود",
        callback_data=AdminAccountCB(action="confirm_delete", account_id=account_id, page=page),
        **style_kwargs(STYLE_DANGER),
    )
    kb.button(
        text="↩️ انصراف",
        callback_data=AdminAccountCB(action="view", account_id=account_id, page=page),
    )
    kb.adjust(2)
    return kb.as_markup()


def admin_order_review(order_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ تایید", callback_data=AdminOrderCB(action="approve", order_id=order_id), **style_kwargs(STYLE_SUCCESS))
    kb.button(text="❌ رد", callback_data=AdminOrderCB(action="reject", order_id=order_id), **style_kwargs(STYLE_DANGER))
    kb.button(text="🏁 تکمیل سفارش", callback_data=AdminOrderCB(action="complete", order_id=order_id), **style_kwargs(STYLE_PRIMARY))
    kb.button(text="👁 جزئیات سفارش", callback_data=AdminOrderCB(action="details", order_id=order_id))
    kb.button(text="💬 ارسال پیام به کاربر", callback_data=AdminOrderCB(action="msg", order_id=order_id))
    kb.adjust(2, 1, 1, 1)
    return kb.as_markup()


def pending_kind_menu() -> InlineKeyboardMarkup:
    """Chooser: which pending list to open — diamond orders or account orders."""
    kb = InlineKeyboardBuilder()
    kb.button(
        text="💎 سفارش‌های در انتظار خرید جم",
        callback_data=AdminCB(action="pending_orders", value="diamond"),
        **style_kwargs(STYLE_PRIMARY),
    )
    kb.button(
        text="🛒 سفارش‌های درحال انتظار خرید اکانت",
        callback_data=AdminCB(action="pending_orders", value="account"),
        **style_kwargs(STYLE_PRIMARY),
    )
    kb.button(
        text="💰 سفارش‌های کیف پول",
        callback_data=AdminCB(action="wallet_requests"),
        **style_kwargs(STYLE_SUCCESS),
    )
    kb.button(text="⬅️ بازگشت به پنل", callback_data=AdminCB(action="back_home"))
    kb.adjust(1)
    return kb.as_markup()


def pending_status_menu(kind: str) -> InlineKeyboardMarkup:
    """Chooser shown after picking a kind: review-queue vs. approved orders."""
    kb = InlineKeyboardBuilder()
    kb.button(
        text="🟡 سفارشات نیاز به بررسی",
        callback_data=AdminOrderCB(action="page", page=1, kind=kind, group="review"),
        **style_kwargs(STYLE_PRIMARY),
    )
    kb.button(
        text="🟢 سفارشات تایید شده",
        callback_data=AdminOrderCB(action="page", page=1, kind=kind, group="approved"),
        **style_kwargs(STYLE_SUCCESS),
    )
    kb.button(text="⬅️ بازگشت", callback_data=AdminCB(action="pending_orders"))
    kb.adjust(1)
    return kb.as_markup()


def pending_orders_menu(
    orders, page: int, total_pages: int, kind: str | None = None, group: str | None = None
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for o in orders:
        kb.button(
            text=f"#{o.id} | {format_toman(o.amount)}",
            callback_data=AdminOrderCB(action="open", order_id=o.id, page=page, kind=kind, group=group),
        )
    kb.adjust(1)
    kb.attach(_pagination_row_kind(AdminOrderCB, "page", page, total_pages, kind, group))

    tail = InlineKeyboardBuilder()
    # Back to this kind's status chooser (review/approved); falls back to the
    # kind chooser when kind is unknown.
    tail.button(
        text="⬅️ بازگشت", callback_data=AdminCB(action="pending_orders", value=kind)
    )
    kb.attach(tail)
    return kb.as_markup()


def pending_order_actions(
    order_id: int, page: int, kind: str | None = None, group: str | None = None
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if group == "approved":
        # Approved orders only get completed — no re-approve / re-reject here.
        kb.button(text="🏁 تکمیل سفارش", callback_data=AdminOrderCB(action="complete", order_id=order_id, page=page, kind=kind, group=group), **style_kwargs(STYLE_SUCCESS))
        kb.button(text="👁 جزئیات", callback_data=AdminOrderCB(action="details", order_id=order_id, page=page, kind=kind, group=group))
        kb.button(text="💬 ارسال پیام به کاربر", callback_data=AdminOrderCB(action="msg", order_id=order_id, page=page, kind=kind, group=group))
        kb.button(text="⬅️ بازگشت به لیست", callback_data=AdminOrderCB(action="page", page=page, kind=kind, group=group))
        kb.adjust(1, 1, 1, 1)
    else:
        kb.button(text="✅ تایید", callback_data=AdminOrderCB(action="approve", order_id=order_id, page=page, kind=kind, group=group), **style_kwargs(STYLE_SUCCESS))
        kb.button(text="❌ رد", callback_data=AdminOrderCB(action="reject", order_id=order_id, page=page, kind=kind, group=group), **style_kwargs(STYLE_DANGER))
        kb.button(text="👁 جزئیات", callback_data=AdminOrderCB(action="details", order_id=order_id, page=page, kind=kind, group=group))
        kb.button(text="💬 ارسال پیام به کاربر", callback_data=AdminOrderCB(action="msg", order_id=order_id, page=page, kind=kind, group=group))
        kb.button(text="⬅️ بازگشت به لیست", callback_data=AdminOrderCB(action="page", page=page, kind=kind, group=group))
        kb.adjust(2, 1, 1, 1)
    return kb.as_markup()


def order_details_actions(
    order_id: int, page: int, kind: str | None = None, group: str | None = None
) -> InlineKeyboardMarkup:
    """Actions under a full order-details view, scoped to the status bucket."""
    kb = InlineKeyboardBuilder()
    if group == "approved":
        kb.button(
            text="🏁 تکمیل سفارش",
            callback_data=AdminOrderCB(action="complete", order_id=order_id, page=page, kind=kind, group=group),
            **style_kwargs(STYLE_SUCCESS),
        )
        kb.button(
            text="⬅️ بازگشت به سفارش",
            callback_data=AdminOrderCB(action="open", order_id=order_id, page=page, kind=kind, group=group),
        )
        kb.adjust(1)
    else:
        kb.button(
            text="✅ تایید",
            callback_data=AdminOrderCB(action="approve", order_id=order_id, page=page, kind=kind, group=group),
            **style_kwargs(STYLE_SUCCESS),
        )
        kb.button(
            text="❌ رد",
            callback_data=AdminOrderCB(action="reject", order_id=order_id, page=page, kind=kind, group=group),
            **style_kwargs(STYLE_DANGER),
        )
        kb.button(
            text="⬅️ بازگشت به سفارش",
            callback_data=AdminOrderCB(action="open", order_id=order_id, page=page, kind=kind, group=group),
        )
        kb.adjust(2, 1)
    return kb.as_markup()


def requested_deposit_review(req_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(
        text="✅ تایید بیعانه",
        callback_data=AdminRequestedCB(action="approve_deposit", req_id=req_id),
        **style_kwargs(STYLE_SUCCESS),
    )
    kb.button(
        text="❌ رد بیعانه",
        callback_data=AdminRequestedCB(action="reject_deposit", req_id=req_id),
        **style_kwargs(STYLE_DANGER),
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
    kb.attach(_pagination_row(AdminRequestedCB, "page", page, total_pages))

    tail = InlineKeyboardBuilder()
    tail.button(text="⬅️ بازگشت به پنل", callback_data=AdminCB(action="back_home"))
    kb.attach(tail)
    return kb.as_markup()


def requested_account_detail_menu(req_id: int, page: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🗑 حذف", callback_data=AdminRequestedCB(action="delete", req_id=req_id, page=page), **style_kwargs(STYLE_DANGER))
    kb.button(text="⬅️ بازگشت به لیست", callback_data=AdminRequestedCB(action="page", page=page))
    kb.adjust(1)
    return kb.as_markup()


def requested_account_delete_confirm(req_id: int, page: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(
        text="🗑 بله، حذف شود",
        callback_data=AdminRequestedCB(action="confirm_delete", req_id=req_id, page=page),
        **style_kwargs(STYLE_DANGER),
    )
    kb.button(
        text="↩️ انصراف",
        callback_data=AdminRequestedCB(action="view", req_id=req_id, page=page),
    )
    kb.adjust(2)
    return kb.as_markup()


def wallet_topup_list_menu(rows, page: int, total_pages: int) -> InlineKeyboardMarkup:
    """«💰 سفارش‌های کیف پول» — glass list of PENDING wallet-charge requests.

    ``rows`` are ``(req, user)`` tuples. Button labels are plain text (inline
    buttons can't carry HTML/links), so a usernameless user falls back to their
    name and finally their telegram id. Back returns to the pending-orders chooser.
    """
    kb = InlineKeyboardBuilder()
    for req, user in rows:
        if user is not None and user.username:
            handle = f"@{user.username}"
        elif user is not None and user.full_name:
            handle = user.full_name
        elif user is not None:
            handle = str(user.telegram_id)
        else:
            handle = "—"
        kb.button(
            text=f"💰 #{req.id} | {format_toman(req.amount)} | {handle}",
            callback_data=WalletTopUpCB(action="view", req_id=req.id, page=page),
        )
    kb.adjust(1)
    kb.attach(_pagination_row(WalletTopUpCB, "page", page, total_pages))

    tail = InlineKeyboardBuilder()
    tail.button(text="⬅️ بازگشت", callback_data=AdminCB(action="pending_orders"))
    kb.attach(tail)
    return kb.as_markup()


def wallet_topup_detail_menu(req_id: int, page: int) -> InlineKeyboardMarkup:
    """Decision buttons under one request opened from the list (page>=1)."""
    kb = InlineKeyboardBuilder()
    kb.button(
        text="✅ تایید شارژ کیف پول",
        callback_data=WalletTopUpCB(action="approve", req_id=req_id, page=page),
        **style_kwargs(STYLE_SUCCESS),
    )
    kb.button(
        text="❌ رد درخواست",
        callback_data=WalletTopUpCB(action="reject", req_id=req_id, page=page),
        **style_kwargs(STYLE_DANGER),
    )
    kb.button(
        text="📄 جزئیات کامل",
        callback_data=WalletTopUpCB(action="details", req_id=req_id, page=page),
    )
    kb.button(
        text="🔙 بازگشت",
        callback_data=WalletTopUpCB(action="page", page=page),
    )
    kb.adjust(2, 1, 1)
    return kb.as_markup()


def wallet_topup_notify_actions(req_id: int) -> InlineKeyboardMarkup:
    """Buttons under the instant-notification card (``page=0`` sentinel).

    ``page=0`` tells the handler the action came from the receipt-photo card (so
    it annotates that card) rather than the in-place list; same convention as the
    sale-account notification buttons.
    """
    kb = InlineKeyboardBuilder()
    kb.button(
        text="✅ تایید شارژ",
        callback_data=WalletTopUpCB(action="approve", req_id=req_id, page=0),
        **style_kwargs(STYLE_SUCCESS),
    )
    kb.button(
        text="❌ رد درخواست",
        callback_data=WalletTopUpCB(action="reject", req_id=req_id, page=0),
        **style_kwargs(STYLE_DANGER),
    )
    kb.button(
        text="📄 جزئیات",
        callback_data=WalletTopUpCB(action="details", req_id=req_id, page=0),
    )
    kb.adjust(2, 1)
    return kb.as_markup()


def ticket_actions(ticket_id: int, is_admin: bool) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(
        text="💬 پاسخ",
        callback_data=TicketCB(action="reply", ticket_id=ticket_id),
        **style_kwargs(STYLE_PRIMARY),
    )
    kb.button(
        text="🔒 بستن تیکت",
        callback_data=TicketCB(action="close", ticket_id=ticket_id),
        **style_kwargs(STYLE_DANGER),
    )
    kb.adjust(2)
    return kb.as_markup()


def referrers_menu(rows, page: int, total_pages: int) -> InlineKeyboardMarkup:
    """Glass list of referrers — «👤 @username | 5 دعوت» (or telegram id).

    ``rows`` are ``(user, referrer_id, count)`` tuples; ``user`` may be ``None``
    (deleted account) → fall back to the raw referrer id so the row still renders.
    """
    kb = InlineKeyboardBuilder()
    for user, referrer_id, count in rows:
        if user is not None and user.username:
            handle = f"@{user.username}"
        elif user is not None:
            handle = str(user.telegram_id)
        else:
            handle = str(referrer_id)
        kb.button(
            text=f"👤 {handle} | {count} دعوت",
            callback_data=AdminReferrerCB(action="view", referrer_id=referrer_id, page=1),
        )
    kb.adjust(1)
    kb.attach(_pagination_row(AdminReferrerCB, "page", page, total_pages))

    tail = InlineKeyboardBuilder()
    tail.button(
        text="♻️ ریست آمار همه دعوت‌کننده‌ها",
        callback_data=AdminReferrerCB(action="reset_all", page=page),
        **style_kwargs(STYLE_DANGER),
    )
    tail.button(text="⬅️ بازگشت به پنل", callback_data=AdminCB(action="back_home"))
    tail.adjust(1)
    kb.attach(tail)
    return kb.as_markup()


def referred_detail_menu(
    referrer_id: int, page: int, total_pages: int
) -> InlineKeyboardMarkup:
    """Invitee-list pagination + back, threading ``referrer_id`` through each page."""
    kb = InlineKeyboardBuilder()
    nav = InlineKeyboardBuilder()
    if page > 1:
        nav.button(
            text="⬅️ قبلی",
            callback_data=AdminReferrerCB(action="view", referrer_id=referrer_id, page=page - 1),
        )
    nav.button(text=f"{page}/{total_pages}", callback_data=NavCB(action="noop"))
    if page < total_pages:
        nav.button(
            text="بعدی ➡️",
            callback_data=AdminReferrerCB(action="view", referrer_id=referrer_id, page=page + 1),
        )
    kb.attach(nav)

    tail = InlineKeyboardBuilder()
    tail.button(text="⬅️ بازگشت", callback_data=AdminReferrerCB(action="page", page=1))
    kb.attach(tail)
    return kb.as_markup()
