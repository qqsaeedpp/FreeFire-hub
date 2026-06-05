"""Admin order review — approve / reject / complete, with delivery & rewards."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.container import Services
from app.core.constants import ORDER_STATUS_FA, OrderStatus, OrderType
from app.core.security import decrypt
from app.filters.admin import IsAdmin
from app.keyboards.callbacks import AdminCB, AdminOrderCB
from app.keyboards.inline import admin_order_review
from app.models.user import User
from app.services.notification_service import NotificationService
from app.states.admin_states import RejectReasonFlow
from app.utils.helpers import format_toman

router = Router(name="admin_orders")


@router.callback_query(AdminCB.filter(F.action == "pending_orders"), IsAdmin())
async def pending_orders(callback: CallbackQuery, services: Services) -> None:
    orders = await services.orders.list_by_status(OrderStatus.UNDER_REVIEW, limit=10)
    if not orders:
        await callback.answer("سفارشی در انتظار بررسی نیست.", show_alert=True)
        return
    for o in orders:
        user = await services.users.get(o.user_id)
        tg = user.telegram_id if user else "?"
        await callback.message.answer(
            f"🧾 سفارش #{o.id}\nنوع: {o.order_type}\nکاربر: <code>{tg}</code>\n"
            f"مبلغ: {format_toman(o.amount)}\nوضعیت: {ORDER_STATUS_FA.get(o.status, o.status)}",
            reply_markup=admin_order_review(o.id),
        )
    await callback.answer()


@router.callback_query(AdminOrderCB.filter(F.action == "approve"), IsAdmin())
async def approve(
    callback: CallbackQuery, callback_data: AdminOrderCB, services: Services, bot
) -> None:
    order = await services.order.get(callback_data.order_id)
    if order is None:
        await callback.answer("سفارش یافت نشد.", show_alert=True)
        return
    await services.order.approve(order)
    await services.commit()
    user = await services.users.get(order.user_id)
    if user:
        await NotificationService(bot).notify_user(
            user.telegram_id,
            f"✅ سفارش #{order.id} شما تایید شد و در حال آماده‌سازی است.",
        )
    await callback.answer("تایید شد.")
    await _refresh(callback, order.id)


@router.callback_query(AdminOrderCB.filter(F.action == "complete"), IsAdmin())
async def complete(
    callback: CallbackQuery, callback_data: AdminOrderCB, services: Services, bot
) -> None:
    order = await services.order.get(callback_data.order_id)
    if order is None:
        await callback.answer("سفارش یافت نشد.", show_alert=True)
        return

    await services.order.complete(order)
    user = await services.users.get(order.user_id)
    notifier = NotificationService(bot)

    # Deliver account credentials for account purchases.
    if order.order_type == OrderType.ACCOUNT_PURCHASE and user:
        acc_order = await services.orders.get_account_order(order.id)
        if acc_order:
            account = await services.account.get(acc_order.account_id)
            if account:
                creds = await services.account.deliver(account, acc_order)
                await notifier.notify_user(
                    user.telegram_id,
                    f"🎉 سفارش #{order.id} تکمیل شد!\n\n"
                    f"🔐 اطلاعات اکانت شما:\n<code>{creds or 'توسط پشتیبانی ارسال می‌شود'}</code>",
                )
    elif user:
        await notifier.notify_user(
            user.telegram_id, f"🏁 سفارش #{order.id} شما با موفقیت تکمیل شد. ممنون از خرید شما!"
        )

    # First successful purchase -> mark + reward referrer.
    if user and not user.has_purchased:
        await services.user.mark_purchased(user)
        result = await services.referral.reward_on_first_purchase(user)
        if result.rewarded and result.referrer_telegram_id:
            await notifier.notify_user(
                result.referrer_telegram_id,
                f"🎁 یکی از زیرمجموعه‌های شما اولین خرید خود را انجام داد!\n"
                f"مبلغ {format_toman(result.amount)} به کیف پول شما اضافه شد.",
            )
            await notifier.log_event(
                "ثبت زیرمجموعه",
                {"معرف": str(result.referrer_telegram_id), "پاداش": format_toman(result.amount)},
            )

    await services.commit()
    await notifier.log_event(
        "سفارش تکمیل شد", {"سفارش": f"#{order.id}", "مبلغ": format_toman(order.amount)}
    )
    await callback.answer("سفارش تکمیل شد.")
    await _refresh(callback, order.id, completed=True)


@router.callback_query(AdminOrderCB.filter(F.action == "reject"), IsAdmin())
async def reject_start(
    callback: CallbackQuery, callback_data: AdminOrderCB, state: FSMContext
) -> None:
    await state.set_state(RejectReasonFlow.entering_reason)
    await state.update_data(order_id=callback_data.order_id)
    await callback.message.answer(
        f"دلیل رد سفارش #{callback_data.order_id} را بنویسید (یا «-» برای بدون دلیل):"
    )
    await callback.answer()


@router.message(RejectReasonFlow.entering_reason, F.text, IsAdmin())
async def reject_finish(
    message: Message, services: Services, state: FSMContext, bot
) -> None:
    data = await state.get_data()
    order = await services.order.get(data["order_id"])
    if order is None:
        await message.answer("سفارش یافت نشد.")
        await state.clear()
        return
    reason = message.text.strip()
    reason = None if reason == "-" else reason
    await services.order.reject(order, reason)

    # Release a reserved account back to the shop on rejection.
    if order.order_type == OrderType.ACCOUNT_PURCHASE:
        acc_order = await services.orders.get_account_order(order.id)
        if acc_order:
            account = await services.account.get(acc_order.account_id)
            if account:
                await services.account.release(account)

    await services.commit()
    user = await services.users.get(order.user_id)
    if user:
        await NotificationService(bot).notify_user(
            user.telegram_id,
            f"❌ سفارش #{order.id} شما رد شد."
            + (f"\nدلیل: {reason}" if reason else ""),
        )
    await message.answer("سفارش رد شد.")
    await state.clear()


async def _refresh(callback: CallbackQuery, order_id: int, completed: bool = False) -> None:
    try:
        status = "🏁 تکمیل‌شده" if completed else "✅ تاییدشده"
        await callback.message.edit_text(
            f"{callback.message.text}\n\n— وضعیت: {status}", reply_markup=None
        )
    except Exception:  # noqa: BLE001 - message may be a photo caption
        pass
