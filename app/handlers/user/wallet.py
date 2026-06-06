"""Wallet handlers — balance, top-up request, transaction history."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.container import Services
from app.core.config import settings
from app.core.constants import (
    PAYMENT_METHOD_FA,
    CardPurpose,
    PaymentMethod,
    TransactionType,
)
from app.handlers.user.payment import prompt_payment_method
from app.keyboards.inline import cancel_only
from app.keyboards.reply import BTN_WALLET, main_menu
from app.models.user import User
from app.services.notification_service import NotificationService
from app.states.user_states import WalletFlow
from app.utils.helpers import format_toman, user_ref
from app.utils.validators import parse_price

router = Router(name="user_wallet")

_TX_FA = {
    TransactionType.DEPOSIT: "افزایش موجودی",
    TransactionType.WITHDRAW: "برداشت",
    TransactionType.PURCHASE: "خرید",
    TransactionType.REFERRAL_REWARD: "پاداش زیرمجموعه",
    TransactionType.REFUND: "بازگشت وجه",
}


@router.message(F.text == BTN_WALLET)
async def wallet_home(message: Message, services: Services, db_user: User) -> None:
    wallet = await services.wallet.get_or_create(db_user.id)
    txs = await services.wallet.history(db_user.id, limit=10)
    await services.commit()

    lines = [f"👛 <b>کیف پول شما</b>\n💰 موجودی: <b>{format_toman(wallet.balance)}</b>\n"]
    if txs:
        lines.append("🧾 <b>آخرین تراکنش‌ها:</b>")
        for tx in txs:
            sign = "➕" if tx.amount >= 0 else "➖"
            lines.append(
                f"{sign} {format_toman(abs(tx.amount))} — {_TX_FA.get(tx.type, tx.type)}"
            )
    else:
        lines.append("هنوز تراکنشی ندارید.")
    lines.append("\nبرای افزایش موجودی دستور /topup را بزنید.")
    await message.answer("\n".join(lines))


@router.message(F.text == "/topup")
async def topup_start(message: Message, state: FSMContext) -> None:
    await state.set_state(WalletFlow.entering_topup_amount)
    await message.answer(
        "💳 مبلغ موردنظر برای افزایش موجودی را (به تومان) وارد کنید:",
        reply_markup=cancel_only(),
    )


@router.message(WalletFlow.entering_topup_amount, F.text)
async def topup_amount(message: Message, state: FSMContext) -> None:
    amount = parse_price(message.text)
    if amount is None or amount < 10_000:
        await message.answer("❌ مبلغ نامعتبر است (حداقل ۱۰,۰۰۰ تومان).")
        return
    await state.update_data(amount=amount)
    await prompt_payment_method(
        message,
        state,
        order_id=None,
        amount=amount,
        receipt_state=WalletFlow.awaiting_topup_receipt,
        purpose=CardPurpose.DIAMOND,
    )


@router.message(WalletFlow.awaiting_topup_receipt, F.photo)
async def topup_receipt(
    message: Message, services: Services, state: FSMContext, db_user: User, bot
) -> None:
    data = await state.get_data()
    amount = data["amount"]
    method_fa = PAYMENT_METHOD_FA.get(
        PaymentMethod(data["pay_method"]) if data.get("pay_method") else None, "-"
    )
    file_id = message.photo[-1].file_id
    await message.answer(
        "✅ رسید شارژ کیف پول دریافت شد و پس از تایید پشتیبانی به موجودی شما اضافه می‌شود.",
        reply_markup=main_menu(db_user.is_admin),
    )
    notifier = NotificationService(bot)
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from app.keyboards.callbacks import AdminCB

    kb = InlineKeyboardBuilder()
    kb.button(
        text="✅ تایید شارژ",
        callback_data=AdminCB(action="approve_topup", value=f"{db_user.id}-{amount}"),
    )
    caption = (
        f"💳 <b>درخواست شارژ کیف پول</b>\n"
        f"کاربر: {user_ref(db_user)}\n"
        f"روش پرداخت: {method_fa}\n"
        f"مبلغ: {format_toman(amount)}"
    )
    try:
        await bot.send_photo(
            settings.admin_id, file_id, caption=caption, reply_markup=kb.as_markup()
        )
    except Exception:  # noqa: BLE001
        await notifier.notify_admin(caption, reply_markup=kb.as_markup())
    await notifier.log_event(
        "پرداخت", {"نوع": "شارژ کیف پول", "کاربر": user_ref(db_user), "مبلغ": format_toman(amount)}
    )
    await state.clear()


@router.message(WalletFlow.awaiting_topup_receipt)
async def topup_not_photo(message: Message) -> None:
    await message.answer("لطفاً تصویر رسید را ارسال کنید. 📸")
