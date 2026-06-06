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
from app.keyboards.inline import pending_order_actions, pending_orders_menu
from app.models.user import User
from app.services.notification_service import NotificationService
from app.states.admin_states import RejectReasonFlow
from app.utils.helpers import edit_or_answer, format_toman, paginate_meta, user_ref

router = Router(name="admin_orders")

_PENDING_PAGE_SIZE = 10


async def _pending_list_content(services: Services, page: int):
    """Compute (text, markup) for the pending-orders list with a smart page clamp."""
    total = await services.orders.count_by_status(OrderStatus.UNDER_REVIEW)
    total_pages = max(1, (total + _PENDING_PAGE_SIZE - 1) // _PENDING_PAGE_SIZE)
    page = max(1, min(page, total_pages))  # smart-clamp when a page empties out
    if total == 0:
        return "✅ سفارشی در انتظار بررسی نیست.", pending_orders_menu([], 1, 1)
    offset = (page - 1) * _PENDING_PAGE_SIZE
    orders = await services.orders.list_by_status(
        OrderStatus.UNDER_REVIEW, offset=offset, limit=_PENDING_PAGE_SIZE
    )
    text = (
        f"🧾 <b>سفارش‌های در انتظار بررسی</b> ({total} سفارش)\nیکی را انتخاب کنید:"
    )
    return text, pending_orders_menu(orders, page, total_pages)


async def _show_pending(message, services: Services, page: int) -> None:
    text, markup = await _pending_list_content(services, page)
    await edit_or_answer(message, text, reply_markup=markup)


async def _delete_pending_receipt(bot, chat_id: int, state: FSMContext) -> None:
    """Remove the separate receipt-photo message sent for an opened order."""
    data = await state.get_data()
    mid = data.get("pending_receipt_msg_id")
    if mid:
        try:
            await bot.delete_message(chat_id, mid)
        except Exception:  # noqa: BLE001 - already gone / too old to delete
            pass
        await state.update_data(pending_receipt_msg_id=None)


def _order_caption(order, user) -> str:
    method_fa = PAYMENT_METHOD_FA.get(order.payment_method, "-")
    return (
        f"🧾 <b>سفارش #{order.id}</b>\n"
        f"نوع: {order.order_type}\n"
        f"کاربر: {user_ref(user)}\n"
        f"روش پرداخت: {method_fa}\n"
        f"مبلغ: {format_toman(order.amount)}\n"
        f"وضعیت: {ORDER_STATUS_FA.get(order.status, order.status)}"
    )


@router.callback_query(AdminCB.filter(F.action == "pending_orders"), IsAdmin())
async def pending_orders(
    callback: CallbackQuery, services: Services, state: FSMContext, bot
) -> None:
    await _delete_pending_receipt(bot, callback.message.chat.id, state)
    await _show_pending(callback.message, services, page=1)
    await callback.answer()


@router.callback_query(AdminOrderCB.filter(F.action == "page"), IsAdmin())
async def pending_page(
    callback: CallbackQuery,
    callback_data: AdminOrderCB,
    services: Services,
    state: FSMContext,
    bot,
) -> None:
    await _delete_pending_receipt(bot, callback.message.chat.id, state)
    await _show_pending(callback.message, services, page=callback_data.page)
    await callback.answer()


@router.callback_query(AdminOrderCB.filter(F.action == "open"), IsAdmin())
async def open_order(
    callback: CallbackQuery,
    callback_data: AdminOrderCB,
    services: Services,
    state: FSMContext,
    bot,
) -> None:
    order = await services.order.get(callback_data.order_id)
    if order is None:
        await callback.answer("سفارش یافت نشد.", show_alert=True)
        return
    # Drop a previously-opened order's receipt photo before opening this one.
    await _delete_pending_receipt(bot, callback.message.chat.id, state)
    user = await services.users.get(order.user_id)
    caption = _order_caption(order, user)
    actions = pending_order_actions(order.id, callback_data.page)
    # The list message is edited in place into the order detail (so it can later
    # be refreshed in place); the receipt photo is sent as a separate message.
    await edit_or_answer(callback.message, caption, reply_markup=actions)
    payment = await services.payments.get_by_order_id(order.id)
    if payment and payment.receipt_file_id:
        sent = await callback.message.answer_photo(
            payment.receipt_file_id, caption=f"🧾 فیش واریزی سفارش #{order.id}"
        )
        await state.update_data(pending_receipt_msg_id=sent.message_id)
    else:
        await state.update_data(pending_receipt_msg_id=None)
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
                    f"📧 ایمیل اکانت: <code>{dec(diamond.account_email)}</code>",
                    f"🔑 رمز جیمیل: <code>{dec(diamond.gmail_password)}</code>",
                    f"🧩 کد بکاپ: <code>{dec(diamond.backup_code)}</code>",
                ]
    elif order.order_type == OrderType.ACCOUNT_PURCHASE:
        acc_order = await services.orders.get_account_order(order.id)
        if acc_order:
            lines.append(f"🛒 اکانت: #{acc_order.account_id}")

    await callback.message.answer("\n".join(lines))
    await callback.answer()


@router.callback_query(AdminOrderCB.filter(F.action == "approve"), IsAdmin())
async def approve(
    callback: CallbackQuery,
    callback_data: AdminOrderCB,
    services: Services,
    state: FSMContext,
    bot,
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
    # Pending detail (text) → refresh the live list in place; the processed
    # order drops out at once. Notification card (photo) → keep its caption.
    if callback.message.photo is None:
        await _delete_pending_receipt(bot, callback.message.chat.id, state)
        await _show_pending(callback.message, services, page=callback_data.page)
    else:
        await _refresh(callback, order.id)


@router.callback_query(AdminOrderCB.filter(F.action == "complete"), IsAdmin())
async def complete(
    callback: CallbackQuery,
    callback_data: AdminOrderCB,
    services: Services,
    state: FSMContext,
    bot,
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
    if callback.message.photo is None:
        await _delete_pending_receipt(bot, callback.message.chat.id, state)
        await _show_pending(callback.message, services, page=callback_data.page)
    else:
        await _refresh(callback, order.id, completed=True)


@router.callback_query(AdminOrderCB.filter(F.action == "reject"), IsAdmin())
async def reject_start(
    callback: CallbackQuery, callback_data: AdminOrderCB, state: FSMContext
) -> None:
    await state.set_state(RejectReasonFlow.entering_reason)
    # Remember where the reject came from so the reason step can refresh the
    # live pending list in place. A photo message is the notification card; a
    # text message is the in-place pending detail.
    if callback.message.photo is None:
        await state.update_data(
            order_id=callback_data.order_id,
            reject_list_chat_id=callback.message.chat.id,
            reject_list_msg_id=callback.message.message_id,
            reject_list_page=callback_data.page,
        )
    else:
        await state.update_data(
            order_id=callback_data.order_id,
            reject_list_chat_id=None,
            reject_list_msg_id=None,
            reject_list_page=callback_data.page,
        )
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

    # If the reject started from the in-place pending detail, refresh that
    # same list message so the rejected order drops out immediately.
    list_chat_id = data.get("reject_list_chat_id")
    list_msg_id = data.get("reject_list_msg_id")
    if list_chat_id and list_msg_id:
        await _delete_pending_receipt(bot, list_chat_id, state)
        text, markup = await _pending_list_content(
            services, data.get("reject_list_page", 1)
        )
        try:
            await bot.edit_message_text(
                text,
                chat_id=list_chat_id,
                message_id=list_msg_id,
                reply_markup=markup,
            )
        except Exception:  # noqa: BLE001 - message gone / not modified
            pass
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
