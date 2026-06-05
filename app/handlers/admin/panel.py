"""Admin panel — entry, statistics, wallet top-up approval, wallet adjust."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.container import Services
from app.core.constants import OrderStatus, TransactionType
from app.filters.admin import IsAdmin
from app.keyboards.callbacks import AdminCB
from app.keyboards.inline import cancel_only
from app.keyboards.reply import BTN_ADMIN
from app.models.user import User
from app.services.notification_service import NotificationService
from app.states.admin_states import WalletAdjustFlow
from app.utils.helpers import edit_or_answer, format_toman
from app.utils.validators import parse_price

router = Router(name="admin_panel")


def admin_menu() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📊 آمار", callback_data=AdminCB(action="stats"))
    kb.button(text="🧾 سفارش‌های در انتظار", callback_data=AdminCB(action="pending_orders"))
    kb.button(text="➕ افزودن اکانت", callback_data=AdminCB(action="add_account"))
    kb.button(text="💎 قیمت جم", callback_data=AdminCB(action="diamond_prices"))
    kb.button(text="👛 تنظیم موجودی کاربر", callback_data=AdminCB(action="wallet_adjust"))
    kb.button(text="📣 پیام همگانی", callback_data=AdminCB(action="broadcast"))
    kb.adjust(2, 2, 2)
    return kb.as_markup()


@router.message(F.text == BTN_ADMIN, IsAdmin())
@router.message(F.text == "/admin", IsAdmin())
async def admin_home(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("🛠 <b>پنل مدیریت</b>\nیک گزینه را انتخاب کنید:", reply_markup=admin_menu())


@router.callback_query(AdminCB.filter(F.action == "stats"), IsAdmin())
async def stats(callback: CallbackQuery, services: Services) -> None:
    total_users = await services.users.count()
    active_users = await services.users.count_active()
    pending = await services.orders.count_by_status(OrderStatus.UNDER_REVIEW)
    completed = await services.orders.count_by_status(OrderStatus.COMPLETED)
    revenue = await services.orders.revenue()
    available_accounts = await services.accounts_repo.count_available()
    text = (
        "📊 <b>آمار فروشگاه</b>\n\n"
        f"👥 کاربران: {total_users} (فعال: {active_users})\n"
        f"🧾 سفارش در انتظار بررسی: {pending}\n"
        f"🏁 سفارش تکمیل‌شده: {completed}\n"
        f"💰 درآمد کل: {format_toman(revenue)}\n"
        f"🛒 اکانت‌های موجود: {available_accounts}"
    )
    await callback.message.edit_text(text, reply_markup=admin_menu())
    await callback.answer()


@router.callback_query(AdminCB.filter(F.action == "approve_topup"), IsAdmin())
async def approve_topup(
    callback: CallbackQuery, callback_data: AdminCB, services: Services, bot
) -> None:
    try:
        user_id_str, amount_str = callback_data.value.split("-")
        user_id, amount = int(user_id_str), int(amount_str)
    except ValueError:
        await callback.answer("داده نامعتبر.", show_alert=True)
        return
    await services.wallet.credit(
        user_id, amount, TransactionType.DEPOSIT, description="شارژ تاییدشده توسط ادمین"
    )
    await services.commit()
    user = await services.users.get(user_id)
    if user:
        await NotificationService(bot).notify_user(
            user.telegram_id,
            f"✅ کیف پول شما به مبلغ {format_toman(amount)} شارژ شد.",
        )
    await callback.answer("شارژ تایید شد.")
    await callback.message.edit_reply_markup(reply_markup=None)


# ---- wallet adjust flow ----
@router.callback_query(AdminCB.filter(F.action == "wallet_adjust"), IsAdmin())
async def wallet_adjust_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(WalletAdjustFlow.entering_user)
    await edit_or_answer(
        callback.message,
        "👛 آیدی عددی تلگرام کاربر را وارد کنید:",
        reply_markup=cancel_only(),
    )
    await callback.answer()


@router.message(WalletAdjustFlow.entering_user, F.text, IsAdmin())
async def wallet_adjust_user(
    message: Message, services: Services, state: FSMContext
) -> None:
    tg_id = parse_price(message.text)
    if tg_id is None:
        await message.answer("آیدی نامعتبر است.")
        return
    user = await services.users.get_by_telegram_id(tg_id)
    if user is None:
        await message.answer("کاربری با این آیدی یافت نشد.")
        return
    await state.update_data(user_id=user.id, telegram_id=tg_id)
    await state.set_state(WalletAdjustFlow.entering_amount)
    await message.answer(
        "مبلغ تغییر را وارد کنید (مثبت=افزایش، منفی=کاهش). مثال: 50000 یا -20000"
    )


@router.message(WalletAdjustFlow.entering_amount, F.text, IsAdmin())
async def wallet_adjust_amount(
    message: Message, services: Services, state: FSMContext, bot
) -> None:
    raw = message.text.strip().replace(",", "")
    try:
        amount = int(raw)
    except ValueError:
        await message.answer("عدد نامعتبر.")
        return
    data = await state.get_data()
    if amount >= 0:
        await services.wallet.credit(
            data["user_id"], amount, TransactionType.DEPOSIT, "تنظیم دستی ادمین"
        )
    else:
        await services.wallet.debit(
            data["user_id"], -amount, TransactionType.WITHDRAW, "تنظیم دستی ادمین"
        )
    await services.commit()
    await message.answer(f"✅ موجودی کاربر {data['telegram_id']} به‌روزرسانی شد.")
    await NotificationService(bot).notify_user(
        data["telegram_id"],
        f"👛 موجودی کیف پول شما توسط پشتیبانی به میزان {format_toman(abs(amount))} "
        f"{'افزایش' if amount >= 0 else 'کاهش'} یافت.",
    )
    await state.clear()
