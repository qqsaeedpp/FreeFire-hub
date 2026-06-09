"""Admin: 💰 تنظیمات بیعانه — manage the requested-account deposit + card.

Deposit applies *only* to requested accounts (not normal account purchases).
The admin sets the deposit amount, destination card number and card-holder name;
the requested-account flow reads these at runtime, so nothing is hardcoded.
"""
from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.container import Services
from app.core.constants import DEPOSIT_TYPE_FA, DepositType
from app.filters.admin import IsAdmin
from app.keyboards.callbacks import AdminCB, DepositCB
from app.keyboards.inline import cancel_only
from app.models.deposit_setting import DepositSetting
from app.states.admin_states import DepositSettingsFlow
from app.utils.helpers import edit_or_answer, format_toman
from app.utils.validators import parse_price

router = Router(name="admin_deposit")


def _detail_markup(dtype: DepositType) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(
        text="✏️ مبلغ بیعانه",
        callback_data=DepositCB(action="edit_amount", dtype=dtype.value),
    )
    kb.button(
        text="💳 شماره کارت",
        callback_data=DepositCB(action="edit_card", dtype=dtype.value),
    )
    kb.button(
        text="👤 نام صاحب کارت",
        callback_data=DepositCB(action="edit_holder", dtype=dtype.value),
    )
    kb.button(text="🔙 بازگشت", callback_data=AdminCB(action="back_home"))
    kb.adjust(1)
    return kb.as_markup()


def _detail_text(dtype: DepositType, row: DepositSetting) -> str:
    return (
        f"{DEPOSIT_TYPE_FA[dtype]}\n\n"
        f"💰 مبلغ بیعانه: <b>{format_toman(row.amount)}</b>\n"
        f"💳 شماره کارت: <code>{row.card_number or '—'}</code>\n"
        f"👤 صاحب کارت: <b>{row.card_holder or '—'}</b>\n\n"
        "برای تغییر هر مورد دکمه مربوطه را بزنید."
    )


async def _show_detail(
    services: Services, message: Message, dtype: DepositType
) -> None:
    row = await services.deposit.get_or_seed(dtype)
    await services.commit()
    await edit_or_answer(
        message, _detail_text(dtype, row), reply_markup=_detail_markup(dtype)
    )


# --------------------------------- home ---------------------------------
@router.callback_query(AdminCB.filter(F.action == "deposit_settings"), IsAdmin())
async def deposit_home(
    callback: CallbackQuery, services: Services, state: FSMContext
) -> None:
    # Deposit applies only to requested accounts — open that detail directly.
    await state.clear()
    await _show_detail(services, callback.message, DepositType.ACCOUNT_REQUEST)
    await callback.answer()


@router.callback_query(DepositCB.filter(F.action == "home"), IsAdmin())
async def deposit_home_cb(
    callback: CallbackQuery, services: Services, state: FSMContext
) -> None:
    await state.clear()
    await _show_detail(services, callback.message, DepositType.ACCOUNT_REQUEST)
    await callback.answer()


# --------------------------------- view ---------------------------------
@router.callback_query(DepositCB.filter(F.action == "view"), IsAdmin())
async def deposit_view(
    callback: CallbackQuery, callback_data: DepositCB, services: Services
) -> None:
    dtype = DepositType(callback_data.dtype or DepositType.ACCOUNT_REQUEST.value)
    await _show_detail(services, callback.message, dtype)
    await callback.answer()


# ------------------------------ edit amount ------------------------------
@router.callback_query(DepositCB.filter(F.action == "edit_amount"), IsAdmin())
async def edit_amount_start(
    callback: CallbackQuery, callback_data: DepositCB, state: FSMContext
) -> None:
    await state.set_state(DepositSettingsFlow.entering_amount)
    await state.update_data(deposit_type=callback_data.dtype)
    await edit_or_answer(
        callback.message,
        "💰 مبلغ جدید بیعانه را وارد کنید (تومان):",
        reply_markup=cancel_only(),
    )
    await callback.answer()


@router.message(DepositSettingsFlow.entering_amount, F.text, IsAdmin())
async def edit_amount_save(
    message: Message, services: Services, state: FSMContext
) -> None:
    amount = parse_price(message.text)
    if amount is None or amount < 0:
        await message.answer("مبلغ نامعتبر است. یک عدد معتبر وارد کنید.")
        return
    data = await state.get_data()
    dtype = DepositType(data["deposit_type"])
    await services.deposit.set_amount(dtype, amount)
    await services.commit()
    await state.clear()
    await message.answer(f"✅ مبلغ بیعانه به {format_toman(amount)} تغییر یافت.")
    await _show_detail(services, message, dtype)


# ------------------------------ edit card ------------------------------
@router.callback_query(DepositCB.filter(F.action == "edit_card"), IsAdmin())
async def edit_card_start(
    callback: CallbackQuery, callback_data: DepositCB, state: FSMContext
) -> None:
    await state.set_state(DepositSettingsFlow.entering_card_number)
    await state.update_data(deposit_type=callback_data.dtype)
    await edit_or_answer(
        callback.message,
        "💳 شماره کارت مقصد را وارد کنید:",
        reply_markup=cancel_only(),
    )
    await callback.answer()


@router.message(DepositSettingsFlow.entering_card_number, F.text, IsAdmin())
async def edit_card_save(
    message: Message, services: Services, state: FSMContext
) -> None:
    data = await state.get_data()
    dtype = DepositType(data["deposit_type"])
    await services.deposit.set_card_number(dtype, message.text.strip()[:32])
    await services.commit()
    await state.clear()
    await message.answer("✅ شماره کارت ذخیره شد.")
    await _show_detail(services, message, dtype)


# ------------------------------ edit holder ------------------------------
@router.callback_query(DepositCB.filter(F.action == "edit_holder"), IsAdmin())
async def edit_holder_start(
    callback: CallbackQuery, callback_data: DepositCB, state: FSMContext
) -> None:
    await state.set_state(DepositSettingsFlow.entering_card_holder)
    await state.update_data(deposit_type=callback_data.dtype)
    await edit_or_answer(
        callback.message,
        "👤 نام صاحب کارت را وارد کنید:",
        reply_markup=cancel_only(),
    )
    await callback.answer()


@router.message(DepositSettingsFlow.entering_card_holder, F.text, IsAdmin())
async def edit_holder_save(
    message: Message, services: Services, state: FSMContext
) -> None:
    data = await state.get_data()
    dtype = DepositType(data["deposit_type"])
    await services.deposit.set_card_holder(dtype, message.text.strip()[:128])
    await services.commit()
    await state.clear()
    await message.answer("✅ نام صاحب کارت ذخیره شد.")
    await _show_detail(services, message, dtype)
