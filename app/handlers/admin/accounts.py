"""Admin: review user-listed accounts and edit diamond plan prices.

The account-creation form (both admin and user paths) now lives in
``app.handlers.account_form``. This module keeps the admin-only decisions on a
user-submitted listing (buy it directly vs. publish it to the shop) and the
diamond-plan price editor.
"""
from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from html import escape

from app.container import Services
from app.core.constants import PAGE_SIZE, AccountStatus
from app.filters.admin import IsAdmin
from app.keyboards.callbacks import AdminCB, AdminSaleCB, NavCB
from app.keyboards.inline import (
    cancel_only,
    pending_sale_actions,
    pending_sales_menu,
)
from app.services.diamond_service import CAT_ACCOUNT, CAT_DIAMOND, CAT_LEVELUP
from app.services.notification_service import NotificationService
from app.states.admin_states import EditDiamondPrice
from app.utils.helpers import (
    edit_or_answer,
    format_toman,
    paginate_meta,
    sale_request_caption,
)
from app.utils.validators import parse_price

router = Router(name="admin_accounts")


# ===================== ADMIN DECISIONS ON A USER LISTING =====================
# The decision buttons are SHARED between the instant new-listing notification
# (``page == 0``) and the «📦 سفارشات فروش اکانت کاربران» review list (``page >= 1``).
# A PENDING_REVIEW guard makes every action idempotent: once one admin decides,
# every other open card/list entry for that listing is a no-op + "already handled"
# alert, and any list still showing it refreshes that listing out of view.
async def _notify_seller(bot, services: Services, account, text: str) -> None:
    """Best-effort DM to the seller; never breaks the admin flow."""
    if account.seller_user_id is None:
        return
    seller = await services.users.get(account.seller_user_id)
    if seller is None:
        return
    try:
        await bot.send_message(seller.telegram_id, text)
    except Exception:  # noqa: BLE001 - seller may have blocked the bot
        pass


async def _show_pending_sales(message, services: Services, page: int) -> None:
    """Render the review list in place (edit if possible, else answer)."""
    items, total = await services.account.list_pending_listings(
        page=page, page_size=PAGE_SIZE
    )
    _, total_pages = paginate_meta(total, page, PAGE_SIZE)
    page = min(max(1, page), total_pages)
    if not items:
        await edit_or_answer(
            message,
            "📦 <b>سفارشات فروش اکانت کاربران</b>\n\nهیچ درخواست در انتظاری وجود ندارد.",
            reply_markup=pending_sales_menu([], page, total_pages),
        )
        return
    await edit_or_answer(
        message,
        "📦 <b>سفارشات فروش اکانت کاربران</b>\n\n"
        f"تعداد در انتظار بررسی: {total}\n"
        "یک مورد را برای بررسی انتخاب کنید:",
        reply_markup=pending_sales_menu(items, page, total_pages),
    )


async def _load_pending(callback, callback_data: AdminSaleCB, services: Services):
    """Fetch a still-pending listing, or alert + refresh the list and return None."""
    account = await services.account.get(callback_data.account_id)
    if account is None:
        await callback.answer("اکانت یافت نشد.", show_alert=True)
        return None
    if account.status != AccountStatus.PENDING_REVIEW:
        await callback.answer("این درخواست قبلاً بررسی شده است.", show_alert=True)
        if callback_data.page >= 1:
            await _show_pending_sales(callback.message, services, callback_data.page)
        return None
    return account


async def _after_decision(
    callback, callback_data: AdminSaleCB, services: Services, confirm_text: str
) -> None:
    """Refresh the list in place (from the list) or strip the card (from notif)."""
    if callback_data.page >= 1:
        await _show_pending_sales(callback.message, services, callback_data.page)
    else:
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:  # noqa: BLE001 - card may be an album/already edited
            pass
        await callback.message.answer(confirm_text)


@router.callback_query(AdminCB.filter(F.action == "sell_requests"), IsAdmin())
async def sell_requests(
    callback: CallbackQuery, services: Services, state: FSMContext
) -> None:
    await state.clear()
    await _show_pending_sales(callback.message, services, 1)
    await callback.answer()


@router.callback_query(AdminSaleCB.filter(F.action == "page"), IsAdmin())
async def sale_page(
    callback: CallbackQuery, callback_data: AdminSaleCB, services: Services
) -> None:
    await _show_pending_sales(callback.message, services, max(1, callback_data.page))
    await callback.answer()


@router.callback_query(AdminSaleCB.filter(F.action == "open"), IsAdmin())
async def sale_open(
    callback: CallbackQuery, callback_data: AdminSaleCB, services: Services
) -> None:
    page = max(1, callback_data.page)
    account = await services.account.get(callback_data.account_id)
    if account is None or account.status != AccountStatus.PENDING_REVIEW:
        await callback.answer("این درخواست دیگر در دسترس نیست.", show_alert=True)
        await _show_pending_sales(callback.message, services, page)
        return
    seller = (
        await services.users.get(account.seller_user_id)
        if account.seller_user_id
        else None
    )
    detail = (
        f"{sale_request_caption(account, seller)}\n\n"
        f"📌 عنوان: {escape(account.title)}\n"
        f"🆔 شناسه: #{account.id}"
    )
    await edit_or_answer(
        callback.message, detail, reply_markup=pending_sale_actions(account.id, page)
    )
    await callback.answer()


@router.callback_query(AdminSaleCB.filter(F.action == "buy"), IsAdmin())
async def sale_buy(
    callback: CallbackQuery, callback_data: AdminSaleCB, services: Services, bot
) -> None:
    account = await _load_pending(callback, callback_data, services)
    if account is None:
        return
    await services.account.buy_from_seller(account)
    await services.commit()
    await _after_decision(
        callback,
        callback_data,
        services,
        f"✅ اکانت #{account.id} توسط شما خریداری شد و در بخش مدیریت ثبت گردید.",
    )
    await _notify_seller(
        bot,
        services,
        account,
        f"✅ اکانت شما (#{account.id}) توسط پشتیبانی خریداری شد.",
    )
    await NotificationService(bot).log_event(
        "خرید اکانت توسط ادمین", {"اکانت": f"#{account.id}"}
    )
    await callback.answer()


@router.callback_query(AdminSaleCB.filter(F.action == "list"), IsAdmin())
async def sale_list(
    callback: CallbackQuery, callback_data: AdminSaleCB, services: Services, bot
) -> None:
    account = await _load_pending(callback, callback_data, services)
    if account is None:
        return
    await services.account.publish_listing(account)
    await services.commit()
    await _after_decision(
        callback,
        callback_data,
        services,
        f"📋 اکانت #{account.id} به فروشگاه اضافه شد و برای همه نمایش داده می‌شود.",
    )
    await _notify_seller(
        bot,
        services,
        account,
        f"📋 اکانت شما (#{account.id}) در فروشگاه منتشر شد و برای فروش در دسترس است.",
    )
    await NotificationService(bot).log_event(
        "انتشار اکانت کاربر", {"اکانت": f"#{account.id}"}
    )
    await callback.answer()


@router.callback_query(AdminSaleCB.filter(F.action == "reject"), IsAdmin())
async def sale_reject(
    callback: CallbackQuery, callback_data: AdminSaleCB, services: Services, bot
) -> None:
    account = await _load_pending(callback, callback_data, services)
    if account is None:
        return
    await services.account.reject_listing(account)
    await services.commit()
    await _after_decision(
        callback,
        callback_data,
        services,
        f"❌ درخواست فروش اکانت #{account.id} رد شد.",
    )
    await _notify_seller(
        bot,
        services,
        account,
        f"❌ متاسفانه درخواست فروش اکانت شما (#{account.id}) رد شد.",
    )
    await NotificationService(bot).log_event(
        "رد درخواست فروش اکانت", {"اکانت": f"#{account.id}"}
    )
    await callback.answer()


# ============================ DIAMOND PRICES ============================
# The price panel is organised into three independent categories. Each category
# key maps to a plan category; "levelup" additionally exposes the buy-all bundle.
_PRICE_CATS = {
    "uid": (CAT_DIAMOND, "🆔 قیمت جم با UID"),
    "account": (CAT_ACCOUNT, "🔐 قیمت جم با اطلاعات اکانت"),
    "levelup": (CAT_LEVELUP, "🚀 قیمت Level Up"),
}
# Reverse lookup: a plan's category → the panel key it lives under.
_CAT_TO_KEY = {cat: key for key, (cat, _) in _PRICE_CATS.items()}
# Sentinel plan_code used when editing the Level-Up buy-all bundle price.
_LVLALL_CODE = "__levelup_all__"


def _price_categories_kb() -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    for key, (_, label) in _PRICE_CATS.items():
        kb.button(text=label, callback_data=AdminCB(action="price_cat", value=key))
    kb.button(text="🔙 بازگشت", callback_data=AdminCB(action="back_home"))
    kb.adjust(1)
    return kb


def _category_prices_kb(plans, cat_key: str, all_price: int | None = None) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    for p in plans:
        kb.button(
            text=f"{p.name} — {format_toman(p.price)}",
            callback_data=AdminCB(action="edit_plan", value=p.code),
        )
    if cat_key == "levelup" and all_price is not None:
        kb.button(
            text=f"🛒 خرید همه — {format_toman(all_price)}",
            callback_data=AdminCB(action="edit_lvlall"),
        )
    kb.button(text="🔙 بازگشت", callback_data=AdminCB(action="diamond_prices"))
    kb.adjust(1)
    return kb


def _diamond_price_edit_kb(cat_key: str) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.button(text="🔙 بازگشت", callback_data=AdminCB(action="price_cat", value=cat_key))
    kb.button(text="❌ لغو", callback_data=NavCB(action="cancel"))
    kb.adjust(2)
    return kb


async def _show_category_prices(message, services: Services, cat_key: str) -> None:
    category, label = _PRICE_CATS[cat_key]
    plans = await services.diamond.list_plans_by_category(category)
    all_price = (
        await services.diamond.get_levelup_all_price() if cat_key == "levelup" else None
    )
    await edit_or_answer(
        message,
        f"{label}\nبرای تغییر قیمت، مورد دلخواه را انتخاب کنید:",
        reply_markup=_category_prices_kb(plans, cat_key, all_price).as_markup(),
    )


@router.callback_query(AdminCB.filter(F.action == "diamond_prices"), IsAdmin())
async def diamond_prices(
    callback: CallbackQuery, services: Services, state: FSMContext
) -> None:
    await state.clear()
    await edit_or_answer(
        callback.message,
        "💰 <b>مدیریت قیمت‌ها</b>\nدسته‌بندی موردنظر را انتخاب کنید:",
        reply_markup=_price_categories_kb().as_markup(),
    )
    await callback.answer()


@router.callback_query(AdminCB.filter(F.action == "price_cat"), IsAdmin())
async def price_category(
    callback: CallbackQuery, callback_data: AdminCB, services: Services, state: FSMContext
) -> None:
    cat_key = callback_data.value
    if cat_key not in _PRICE_CATS:
        await callback.answer("دسته نامعتبر.", show_alert=True)
        return
    await state.clear()
    await _show_category_prices(callback.message, services, cat_key)
    await callback.answer()


@router.callback_query(AdminCB.filter(F.action == "edit_plan"), IsAdmin())
async def edit_plan(
    callback: CallbackQuery, callback_data: AdminCB, services: Services, state: FSMContext
) -> None:
    plan = await services.diamond.get_plan(callback_data.value)
    if plan is None:
        await callback.answer("پلن یافت نشد.", show_alert=True)
        return
    cat_key = _CAT_TO_KEY.get(plan.category, "uid")
    await state.set_state(EditDiamondPrice.entering_price)
    await state.update_data(plan_code=callback_data.value, cat_key=cat_key)
    await edit_or_answer(
        callback.message,
        f"💎 پلن: <b>{plan.name}</b>\nقیمت فعلی: {format_toman(plan.price)}\n\n"
        f"قیمت جدید را وارد کنید (تومان):",
        reply_markup=_diamond_price_edit_kb(cat_key).as_markup(),
    )
    await callback.answer()


@router.callback_query(AdminCB.filter(F.action == "edit_lvlall"), IsAdmin())
async def edit_levelup_all(
    callback: CallbackQuery, services: Services, state: FSMContext
) -> None:
    current = await services.diamond.get_levelup_all_price()
    await state.set_state(EditDiamondPrice.entering_price)
    await state.update_data(plan_code=_LVLALL_CODE, cat_key="levelup")
    await edit_or_answer(
        callback.message,
        f"🛒 <b>خرید همه لول‌اپ‌ها</b>\nقیمت فعلی: {format_toman(current)}\n\n"
        f"قیمت جدید را وارد کنید (تومان):",
        reply_markup=_diamond_price_edit_kb("levelup").as_markup(),
    )
    await callback.answer()


@router.message(EditDiamondPrice.entering_price, F.text, IsAdmin())
async def save_plan_price(
    message: Message, services: Services, state: FSMContext
) -> None:
    price = parse_price(message.text)
    if price is None or price <= 0:
        await message.answer("قیمت نامعتبر.")
        return
    data = await state.get_data()
    cat_key = data.get("cat_key", "uid")
    code = data.get("plan_code")
    if code == _LVLALL_CODE:
        await services.diamond.set_levelup_all_price(price)
        ok = True
    else:
        ok = await services.diamond.set_plan_price(code, price)
    await services.commit()
    await state.clear()
    if ok:
        category, label = _PRICE_CATS[cat_key]
        plans = await services.diamond.list_plans_by_category(category)
        all_price = (
            await services.diamond.get_levelup_all_price()
            if cat_key == "levelup" else None
        )
        await message.answer(
            f"✅ قیمت به‌روزرسانی شد.\n\n{label}:",
            reply_markup=_category_prices_kb(plans, cat_key, all_price).as_markup(),
        )
    else:
        await message.answer("پلن یافت نشد.")
