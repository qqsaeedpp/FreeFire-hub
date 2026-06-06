"""Generic 'choose a payment method' step.

Every paid flow (diamond purchase, account purchase, wallet top-up) routes through
here after its order is created: the user picks ONLINE or CARD_TO_CARD, we record
the choice on the order, then hand control back to that flow's
``awaiting_receipt`` state.

Online payment has no gateway yet, so for now both methods display the
card-to-card details. The selection is still recorded so the admin can see it and
a real online gateway can be slotted in later without touching the call sites.
"""
from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State
from aiogram.types import CallbackQuery, Message

from app.container import Services
from app.core.config import settings
from app.core.constants import PaymentMethod
from app.keyboards.callbacks import PayMethodCB
from app.keyboards.inline import cancel_only, payment_method_menu
from app.states.user_states import PaymentFlow
from app.utils.helpers import format_toman

router = Router(name="user_payment")


def card_payment_text(amount: int) -> str:
    return (
        f"💳 مبلغ قابل پرداخت: <b>{format_toman(amount)}</b>\n\n"
        f"لطفاً مبلغ را به کارت زیر واریز کنید:\n"
        f"<code>{settings.card_number}</code>\n"
        f"به نام: <b>{settings.card_holder}</b>\n\n"
        f"سپس <b>تصویر رسید</b> را همین‌جا ارسال کنید. 📸"
    )


async def prompt_payment_method(
    target: Message | CallbackQuery,
    state: FSMContext,
    *,
    order_id: int | None,
    amount: int,
    receipt_state: State,
    prefix: str = "",
) -> None:
    """Persist the payment context and show the payment-method choice.

    ``receipt_state`` is the flow-specific state to resume once a method is
    picked. ``order_id`` may be ``None`` for order-less flows (e.g. wallet
    top-up); the selected method is then only stashed in FSM data
    (``pay_method``) for the caller to display. ``prefix`` is optional text
    prepended to the menu prompt.
    """
    await state.set_state(PaymentFlow.choosing_method)
    await state.update_data(
        pay_order_id=order_id,
        pay_amount=amount,
        pay_receipt_state=receipt_state.state,
    )
    text = (prefix + "💼 <b>روش پرداخت را انتخاب کنید:</b>").strip()
    if isinstance(target, CallbackQuery):
        await target.message.edit_text(text, reply_markup=payment_method_menu())
        await target.answer()
    else:
        await target.answer(text, reply_markup=payment_method_menu())


@router.callback_query(PayMethodCB.filter(), F.message)
async def method_chosen(
    callback: CallbackQuery,
    callback_data: PayMethodCB,
    services: Services,
    state: FSMContext,
) -> None:
    data = await state.get_data()
    receipt_state = data.get("pay_receipt_state")
    amount = data.get("pay_amount", 0)
    if receipt_state is None:
        await callback.answer("جلسه پرداخت منقضی شده. دوباره تلاش کنید.", show_alert=True)
        await state.clear()
        return

    method = PaymentMethod(callback_data.method)
    await state.update_data(pay_method=method.value)

    # Order-based flows record the method on the order; order-less flows (wallet
    # top-up) just keep it in FSM data for the caller to display.
    order_id = data.get("pay_order_id")
    if order_id is not None:
        order = await services.order.get(order_id)
        if order is None:
            await callback.answer("سفارش یافت نشد.", show_alert=True)
            await state.clear()
            return
        await services.order.set_payment_method(order, method)
        await services.commit()

    await state.set_state(receipt_state)

    note = ""
    if method is PaymentMethod.ONLINE:
        note = (
            "ℹ️ درگاه پرداخت آنلاین به‌زودی فعال می‌شود؛ "
            "فعلاً مبلغ را کارت‌به‌کارت واریز کنید.\n\n"
        )
    await callback.message.edit_text(
        note + card_payment_text(amount), reply_markup=cancel_only()
    )
    await callback.answer()
