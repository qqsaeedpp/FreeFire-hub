"""Admin order review — approve / reject / complete, with delivery & rewards."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.container import Services
from app.core.constants import (
    ORDER_STATUS_FA,
    PAYMENT_METHOD_FA,
    OrderStatus,
    OrderType,
)
from app.core.security import decrypt
from app.filters.admin import IsAdmin
from app.keyboards.callbacks import AdminCB, AdminOrderCB
from app.keyboards.inline import admin_order_review
from app.models.user import User
from app.services.notification_service import NotificationService
from app.states.admin_states import RejectReasonFlow
from app.utils.helpers import format_toman, user_ref

router = Router(name="admin_orders")


@router.callback_query(AdminCB.filter(F.action == "pending_orders"), IsAdmin())
async def pending_orders(callback: CallbackQuery, services: Services) -> None:
    orders = await services.orders.list_by_status(OrderStatus.UNDER_REVIEW, limit=10)
    if not orders:
        await callback.answer("سفارشی در انتظار بررسی نیست.", show_alert=True)
        return
    for o in orders:
        user = await services.users.get(o.user_id)
        method_fa = PAYMENT_METHOD_FA.get(o.payment_method, "-")
        await callback.message.answer(
            f"🧾 سفارش #{o.id}\nنوع: {o.order_type}\nکاربر: {user_ref(user)}\n"
            f"روش پرداخت: {method_fa}\n"
            f"مبلغ: {format_toman(o.amount)}\nوضعیت: {ORDER_STATUS_FA.get(o.status, o.status)}",
            reply_markup=admin_order_review(o.id),
        )
    await callback.answer()


@router.callback_query(AdminOrderCB.filter(F.action == "details"), IsAdmin())
async def order_details(
    callback: CallbackQuery, callback_data: AdminOrderCB, services: Services
) -> None:
    order = await services.order.get(callback_data.order_id)
    if order is None:
        await callback.answer("سفارش یافت نشد.", show_alert=True)
        return
    user = await services.users.get(order.user_id)
    lines = [
        f"📄 <b>جزئیات سفارش #{order.id}</b>",
        f"کاربر: {user_ref(user)}",
        f"نوع: {order.order_type}",
        f"مبلغ: {format_toman(order.amount)}",
        f"وضعیت: {ORDER_STATUS_FA.get(order.status, order.status)}",
    ]

    if order.order_type in (OrderType.DIAMOND_UID, OrderType.DIAMOND_ACCOUNT):
        diamond = await services.orders.get_diamond(order.id)
        if diamond:
            lines.append(f"پلن: {diamond.plan_name} ({diamond.diamonds} الماس)")
            if order.order_type == OrderType.DIAMOND_UID:
                lines.append(f"🆔 UID: <code>{diamond.uid}</code>")
            else:
                def dec(value: str | None) -> str:
                    return decrypt(value) if value else "-"

                lines += [
                    f"🔐 روش ورود: {diamond.login_method.value if diamond.login_method else '-'}",
                    f"📧 ایمیل اکانت: <code>{dec(diamond.account_email)}</code>",
                    f"🔑 رمز اکانت: <code>{dec(diamond.account_password)}</code>",
                    f"🧩 کد بکاپ: <code>{dec(diamond.backup_code)}</code>",
                    f"📧 جیمیل: <code>{dec(diamond.gmail)}</code>",
                    f"🔑 رمز جیمیل: <code>{dec(diamond.gmail_password)}</code>",
                    f"🧩 بکاپ جیمیل: <code>{dec(diamond.gmail_backup_code)}</code>",
                    f"🧷 بکاپ اکانت: <code>{dec(diamond.account_backup_code)}</code>",
                ]
    elif order.order_type == OrderType.ACCOUNT_PURCHASE:
        acc_order = await services.orders.get_account_order(order.id)
        if acc_order:
            lines.append(f"🛒 اکانت: #{acc_order.account_id}")

    await callback.message.answer("\n".join(lines))
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

    # Track the user's first successful purchase (referral payouts now happen on
    # join, so completion only records the purchase flag).
    if user and not user.has_purchased:
        await services.user.mark_purchased(user)

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
    status = "🏁 تکمیل‌شده" if completed else "✅ تاییدشده"
    msg = callback.message
    body = msg.text if msg.text is not None else (msg.caption or f"سفارش #{order_id}")
    new_text = f"{body}\n\n— وضعیت: {status}"
    try:
        if msg.text is not None:
            await msg.edit_text(new_text, reply_markup=None)
        else:  # admin card is a photo → update its caption in place
            await msg.edit_caption(caption=new_text, reply_markup=None)
    except Exception:  # noqa: BLE001 - keyboard may already be gone / unchanged
        pass
