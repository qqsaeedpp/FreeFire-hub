"""Generic 'choose a payment method' step.

Every paid flow (diamond purchase, account purchase, wallet top-up) routes through
here after its order is created: the user picks a method, we record the choice on
the order, then hand control back to that flow's ``awaiting_receipt`` state.

Three methods exist:

* ONLINE — no gateway yet, so it falls back to showing the card-to-card details.
* CARD_TO_CARD — shows the stored card for the flow's :class:`CardPurpose`
  (admin-managed; falls back to the ``CARD_NUMBER`` / ``CARD_HOLDER`` env values).
* WALLET — only offered for diamond purchases (``can_use_wallet=True``); the
  balance is debited immediately and the order is sent to the admin for delivery
  without a receipt photo.
"""
from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State
from aiogram.types import CallbackQuery, Message

from app.container import Services
from app.core.config import settings
from app.core.constants import (
    PAYMENT_METHOD_FA,
    CardPurpose,
    PaymentMethod,
    TransactionType,
)
from app.keyboards.callbacks import PayMethodCB
from app.keyboards.inline import admin_order_review, cancel_only, payment_method_menu
from app.models.user import User
from app.services.notification_service import NotificationService
from app.services.wallet_service import InsufficientBalanceError
from app.states.user_states import PaymentFlow
from app.utils.helpers import format_toman, user_ref

router = Router(name="user_payment")


async def card_payment_text(services: Services, purpose: CardPurpose, amount: int) -> str:
    """Build the card-to-card instructions for a given sales channel.

    Uses the admin-managed card stored for ``purpose``, falling back to the
    ``CARD_NUMBER`` / ``CARD_HOLDER`` env defaults when none is configured.
    """
    card = await services.card.get_card(purpose)
    number = card.card_number if card else settings.card_number
    holder = card.holder_name if card else settings.card_holder
    return (
        f"💳 مبلغ قابل پرداخت: <b>{format_toman(amount)}</b>\n\n"
        f"لطفاً مبلغ را به کارت زیر واریز کنید:\n"
        f"<code>{number}</code>\n"
        f"به نام: <b>{holder}</b>\n\n"
        f"سپس <b>تصویر رسید</b> را همین‌جا ارسال کنید. 📸"
    )


async def prompt_payment_method(
    target: Message | CallbackQuery,
    state: FSMContext,
    *,
    order_id: int | None,
    amount: int,
    receipt_state: State | str,
    purpose: CardPurpose = CardPurpose.ACCOUNT,
    can_use_wallet: bool = False,
    prefix: str = "",
) -> None:
    """Persist the payment context and show the payment-method choice.

    ``receipt_state`` is the flow-specific state to resume once a card/online
    method is picked (a ``State`` or its raw string). ``order_id`` may be
    ``None`` for order-less flows (e.g. wallet top-up). ``purpose`` selects which
    stored card is shown. ``can_use_wallet`` adds the wallet button (diamond
    purchases only).
    """
    receipt_state_str = (
        receipt_state.state if isinstance(receipt_state, State) else receipt_state
    )
    await state.set_state(PaymentFlow.choosing_method)
    await state.update_data(
        pay_order_id=order_id,
        pay_amount=amount,
        pay_receipt_state=receipt_state_str,
        pay_purpose=purpose.value,
        pay_can_use_wallet=can_use_wallet,
    )
    text = (prefix + "💼 <b>روش پرداخت را انتخاب کنید:</b>").strip()
    markup = payment_method_menu(can_use_wallet=can_use_wallet)
    if isinstance(target, CallbackQuery):
        await target.message.edit_text(text, reply_markup=markup)
        await target.answer()
    else:
        await target.answer(text, reply_markup=markup)


@router.callback_query(PayMethodCB.filter(), F.message)
async def method_chosen(
    callback: CallbackQuery,
    callback_data: PayMethodCB,
    services: Services,
    state: FSMContext,
    db_user: User,
    bot,
) -> None:
    data = await state.get_data()
    receipt_state = data.get("pay_receipt_state")
    amount = data.get("pay_amount", 0)
    if receipt_state is None:
        await callback.answer("جلسه پرداخت منقضی شده. دوباره تلاش کنید.", show_alert=True)
        await state.clear()
        return

    method = PaymentMethod(callback_data.method)
    purpose = CardPurpose(data.get("pay_purpose", CardPurpose.ACCOUNT.value))
    order_id = data.get("pay_order_id")

    # ---- wallet payment (diamond purchases only) ----
    if method is PaymentMethod.WALLET:
        if not data.get("pay_can_use_wallet") or order_id is None:
            await callback.answer("پرداخت با کیف پول برای این خرید فعال نیست.", show_alert=True)
            return
        await _pay_with_wallet(callback, services, state, db_user, bot, order_id, amount)
        return

    await state.update_data(pay_method=method.value)

    # Order-based flows record the method on the order; order-less flows (wallet
    # top-up) just keep it in FSM data for the caller to display.
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
        note + await card_payment_text(services, purpose, amount),
        reply_markup=cancel_only(),
    )
    await callback.answer()


async def _pay_with_wallet(
    callback: CallbackQuery,
    services: Services,
    state: FSMContext,
    db_user: User,
    bot,
    order_id: int,
    amount: int,
) -> None:
    order = await services.order.get(order_id)
    if order is None:
        await callback.answer("سفارش یافت نشد.", show_alert=True)
        await state.clear()
        return

    # Charge against the order's authoritative (possibly discounted) amount.
    charge = order.amount
    try:
        await services.wallet.debit(
            db_user.id, charge, TransactionType.PURCHASE,
            description=f"خرید جم (سفارش #{order.id})",
        )
    except InsufficientBalanceError:
        wallet = await services.wallet.get_or_create(db_user.id)
        await callback.answer(
            f"موجودی کیف پول کافی نیست. موجودی شما: {format_toman(wallet.balance)}",
            show_alert=True,
        )
        return

    await services.order.set_payment_method(order, PaymentMethod.WALLET)
    await services.order.mark_wallet_paid(order)
    await services.commit()
    await state.clear()

    await callback.message.edit_text(
        f"✅ پرداخت از کیف پول انجام شد.\nشماره سفارش: <b>#{order.id}</b>\n"
        f"سفارش شما در حال بررسی و آماده‌سازی توسط پشتیبانی است."
    )
    await callback.answer("پرداخت با موفقیت انجام شد.")

    notifier = NotificationService(bot)
    caption = (
        f"🆕 <b>سفارش جم (پرداخت از کیف پول)</b>\n"
        f"سفارش: #{order.id}\n"
        f"کاربر: {user_ref(db_user)}\n"
        f"روش پرداخت: {PAYMENT_METHOD_FA[PaymentMethod.WALLET]}\n"
        f"مبلغ: {format_toman(charge)}"
    )
    await notifier.notify_admin(caption, reply_markup=admin_order_review(order.id))
    # Additive layer: alert every other authorized admin (legacy notify_admin
    # above covered settings.admin_id). Pending Orders / callbacks unchanged.
    await notifier.notify_admins(
        await services.admin.all_admin_ids(),
        caption,
        reply_markup=admin_order_review(order.id),
        exclude={settings.admin_id},
    )
    await notifier.log_event(
        "سفارش جم (کیف پول)",
        {"سفارش": f"#{order.id}", "کاربر": user_ref(db_user), "مبلغ": format_toman(charge)},
    )
