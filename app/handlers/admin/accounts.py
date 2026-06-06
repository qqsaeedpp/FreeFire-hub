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

from app.container import Services
from app.filters.admin import IsAdmin
from app.keyboards.callbacks import AdminCB, AdminSaleCB
from app.keyboards.inline import cancel_only
from app.services.notification_service import NotificationService
from app.states.admin_states import EditDiamondPrice
from app.utils.helpers import edit_or_answer, format_toman
from app.utils.validators import parse_price

router = Router(name="admin_accounts")


# ===================== ADMIN DECISIONS ON A USER LISTING =====================
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


@router.callback_query(AdminSaleCB.filter(F.action == "buy"), IsAdmin())
async def sale_buy(
    callback: CallbackQuery, callback_data: AdminSaleCB, services: Services, bot
) -> None:
    account = await services.account.get(callback_data.account_id)
    if account is None:
        await callback.answer("اکانت یافت نشد.", show_alert=True)
        return
    await services.account.buy_from_seller(account)
    await services.commit()

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        f"✅ اکانت #{account.id} توسط شما خریداری شد و در بخش مدیریت ثبت گردید."
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
    account = await services.account.get(callback_data.account_id)
    if account is None:
        await callback.answer("اکانت یافت نشد.", show_alert=True)
        return
    await services.account.publish_listing(account)
    await services.commit()

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        f"📋 اکانت #{account.id} به فروشگاه اضافه شد و برای همه نمایش داده می‌شود."
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


# ============================ DIAMOND PRICES ============================
@router.callback_query(AdminCB.filter(F.action == "diamond_prices"), IsAdmin())
async def diamond_prices(callback: CallbackQuery, services: Services) -> None:
    plans = await services.diamond.list_plans()
    kb = InlineKeyboardBuilder()
    for p in plans:
        kb.button(
            text=f"{p.name} — {format_toman(p.price)}",
            callback_data=AdminCB(action="edit_plan", value=p.code),
        )
    kb.adjust(1)
    await edit_or_answer(
        callback.message,
        "💎 برای تغییر قیمت، پلن موردنظر را انتخاب کنید:",
        reply_markup=kb.as_markup(),
    )
    await callback.answer()


@router.callback_query(AdminCB.filter(F.action == "edit_plan"), IsAdmin())
async def edit_plan(
    callback: CallbackQuery, callback_data: AdminCB, state: FSMContext
) -> None:
    await state.set_state(EditDiamondPrice.entering_price)
    await state.update_data(plan_code=callback_data.value)
    await edit_or_answer(
        callback.message,
        f"قیمت جدید برای پلن <code>{callback_data.value}</code> را وارد کنید (تومان):",
        reply_markup=cancel_only(),
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
    ok = await services.diamond.set_plan_price(data["plan_code"], price)
    await message.answer("✅ قیمت به‌روزرسانی شد." if ok else "پلن یافت نشد.")
    await state.clear()
