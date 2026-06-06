"""Requested-account (wanted) flow.

The *sell-account* flow now lives in :mod:`app.handlers.account_form`, which
shares one FSM and one ``Account`` model between the admin and user paths.
"""
from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.container import Services
from app.core.config import settings
from app.keyboards.inline import cancel_only
from app.keyboards.reply import BTN_REQUEST_ACCOUNT, main_menu
from app.models.user import User
from app.services.notification_service import NotificationService
from app.states.user_states import RequestedAccountFlow
from app.utils.helpers import format_toman, user_ref
from app.utils.validators import parse_price

router = Router(name="user_sell")


# ========================= REQUESTED ACCOUNT =========================


@router.message(F.text == BTN_REQUEST_ACCOUNT)
async def req_entry(message: Message, state: FSMContext) -> None:
    await state.set_state(RequestedAccountFlow.entering_price)
    await message.answer(
        "📝 <b>ثبت اکانت درخواستی</b>\n"
        f"توجه: برای ثبت سفارش، بیعانه‌ای معادل "
        f"<b>{format_toman(settings.requested_account_deposit)}</b> دریافت می‌شود.\n\n"
        "قیمت مدنظر خود را (به تومان) وارد کنید:",
        reply_markup=cancel_only(),
    )


@router.message(RequestedAccountFlow.entering_price, F.text)
async def req_price(message: Message, state: FSMContext) -> None:
    price = parse_price(message.text)
    if price is None or price <= 0:
        await message.answer("❌ قیمت نامعتبر است.")
        return
    await state.update_data(price=price)
    await state.set_state(RequestedAccountFlow.entering_elite)
    await message.answer("⭐️ تعداد الیت پس مدنظر:", reply_markup=cancel_only())


@router.message(RequestedAccountFlow.entering_elite, F.text)
async def req_elite(message: Message, state: FSMContext) -> None:
    await state.update_data(elite=parse_price(message.text) or 0)
    await state.set_state(RequestedAccountFlow.entering_sets)
    await message.answer("🎽 ست‌های موردنظر را بنویسید:", reply_markup=cancel_only())


@router.message(RequestedAccountFlow.entering_sets, F.text)
async def req_sets(message: Message, state: FSMContext) -> None:
    await state.update_data(sets=message.text.strip())
    await state.set_state(RequestedAccountFlow.entering_guns)
    await message.answer("🔫 گان‌های موردنظر را بنویسید:", reply_markup=cancel_only())


@router.message(RequestedAccountFlow.entering_guns, F.text)
async def req_guns(message: Message, state: FSMContext) -> None:
    await state.update_data(guns=message.text.strip())
    await state.set_state(RequestedAccountFlow.entering_description)
    await message.answer("📝 توضیحات تکمیلی:", reply_markup=cancel_only())


@router.message(RequestedAccountFlow.entering_description, F.text)
async def req_description(message: Message, state: FSMContext) -> None:
    await state.update_data(description=message.text.strip())
    await state.set_state(RequestedAccountFlow.awaiting_deposit_receipt)
    await message.answer(
        f"💳 لطفاً بیعانه <b>{format_toman(settings.requested_account_deposit)}</b> را به کارت زیر واریز کنید:\n"
        f"<code>{settings.card_number}</code>\nبه نام: <b>{settings.card_holder}</b>\n\n"
        "سپس تصویر رسید را ارسال کنید. 📸",
        reply_markup=cancel_only(),
    )


@router.message(RequestedAccountFlow.awaiting_deposit_receipt, F.photo)
async def req_deposit(
    message: Message, services: Services, state: FSMContext, db_user: User, bot
) -> None:
    data = await state.get_data()
    req = await services.account.create_requested_account(
        db_user.id,
        target_price=data["price"],
        elite_count=data["elite"],
        sets=data["sets"],
        guns=data["guns"],
        description=data["description"],
        deposit_paid=True,
    )
    await services.commit()
    file_id = message.photo[-1].file_id
    await message.answer(
        f"✅ درخواست اکانت شما با شماره #{req.id} ثبت شد و در حال بررسی است.",
        reply_markup=main_menu(db_user.is_admin),
    )
    notifier = NotificationService(bot)
    caption = (
        f"📝 <b>اکانت درخواستی</b> #{req.id}\n"
        f"کاربر: {user_ref(db_user)}\n"
        f"قیمت مدنظر: {format_toman(data['price'])}\n"
        f"الیت: {data['elite']} | ست: {data['sets']} | گان: {data['guns']}\n"
        f"توضیحات: {data['description']}\n"
        f"بیعانه: {format_toman(settings.requested_account_deposit)} (پرداخت شد)"
    )
    try:
        await bot.send_photo(settings.admin_id, file_id, caption=caption)
    except Exception:  # noqa: BLE001
        await notifier.notify_admin(caption)
    await notifier.log_event(
        "اکانت درخواستی", {"درخواست": f"#{req.id}", "کاربر": user_ref(db_user)}
    )
    await state.clear()


@router.message(RequestedAccountFlow.awaiting_deposit_receipt)
async def req_deposit_not_photo(message: Message) -> None:
    await message.answer("لطفاً تصویر رسید بیعانه را ارسال کنید. 📸")
