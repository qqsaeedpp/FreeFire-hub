"""Optional discount-code step for diamond purchases.

Inserted between order creation and the payment-method choice: the user is asked
whether they have a code; if a valid one is entered, the order's amount is reduced
by the code's percentage and the code's use is recorded, then control flows on to
``prompt_payment_method``.
"""
from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State
from aiogram.types import CallbackQuery, Message

from app.container import Services
from app.core.constants import CardPurpose
from app.handlers.user.payment import prompt_payment_method
from app.keyboards.inline import cancel_only, discount_prompt_menu
from app.keyboards.callbacks import DiscountCB
from app.services.discount_service import DiscountError
from app.states.user_states import DiscountFlow
from app.utils.helpers import format_toman

router = Router(name="user_discount")


async def prompt_discount(
    target: Message | CallbackQuery,
    state: FSMContext,
    *,
    order_id: int,
    base_amount: int,
    receipt_state: State,
    prefix: str = "",
) -> None:
    """Stash the discount context and ask whether the user has a code."""
    receipt_state_str = (
        receipt_state.state if isinstance(receipt_state, State) else receipt_state
    )
    await state.set_state(DiscountFlow.deciding)
    await state.update_data(
        disc_order_id=order_id,
        disc_base_amount=base_amount,
        disc_receipt_state=receipt_state_str,
        disc_prefix=prefix,
    )
    text = (prefix + "🎟 اگر کد تخفیف دارید وارد کنید، در غیر این صورت ادامه دهید.").strip()
    if isinstance(target, CallbackQuery):
        await target.message.edit_text(text, reply_markup=discount_prompt_menu())
        await target.answer()
    else:
        await target.answer(text, reply_markup=discount_prompt_menu())


async def _to_payment(
    target: Message | CallbackQuery, state: FSMContext, *, amount: int, prefix: str
) -> None:
    data = await state.get_data()
    await prompt_payment_method(
        target,
        state,
        order_id=data["disc_order_id"],
        amount=amount,
        receipt_state=data["disc_receipt_state"],
        purpose=CardPurpose.DIAMOND,
        can_use_wallet=True,
        prefix=prefix,
    )


@router.callback_query(DiscountFlow.deciding, DiscountCB.filter(F.action == "skip"))
async def skip_discount(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    await _to_payment(callback, state, amount=data["disc_base_amount"], prefix="")


@router.callback_query(DiscountFlow.deciding, DiscountCB.filter(F.action == "have"))
async def want_discount(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(DiscountFlow.entering_code)
    await callback.message.edit_text(
        "🎟 کد تخفیف را وارد کنید:", reply_markup=cancel_only()
    )
    await callback.answer()


@router.message(DiscountFlow.entering_code, F.text)
async def enter_code(message: Message, services: Services, state: FSMContext) -> None:
    data = await state.get_data()
    base_amount = data["disc_base_amount"]
    try:
        entry = await services.discount.validate(message.text)
    except DiscountError as exc:
        await message.answer(f"❌ {exc}\nکد دیگری وارد کنید یا «❌ لغو» را بزنید.")
        return

    final = services.discount.apply(base_amount, entry.percent)
    order = await services.order.get(data["disc_order_id"])
    if order is None:
        await message.answer("سفارش یافت نشد. لطفاً دوباره تلاش کنید.")
        await state.clear()
        return
    await services.order.update_amount(order, final)
    await services.discount.redeem(entry)
    await services.commit()

    prefix = (
        f"✅ کد تخفیف <b>{entry.percent}%</b> اعمال شد.\n"
        f"مبلغ پس از تخفیف: <b>{format_toman(final)}</b> "
        f"(قبلاً {format_toman(base_amount)})\n\n"
    )
    await _to_payment(message, state, amount=final, prefix=prefix)
