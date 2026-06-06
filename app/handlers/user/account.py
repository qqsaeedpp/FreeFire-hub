"""Account shop — browse, view details, reserve & purchase."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.container import Services
from app.core.config import settings
from app.core.constants import PAGE_SIZE, PAYMENT_METHOD_FA
from app.handlers.user.payment import prompt_payment_method
from app.keyboards.callbacks import AccountCB
from app.keyboards.inline import (
    account_detail_menu,
    accounts_list_menu,
    admin_order_review,
)
from app.keyboards.reply import BTN_BUY_ACCOUNT, main_menu
from app.models.account import Account
from app.models.user import User
from app.services.account_service import AccountReservationError
from app.services.notification_service import NotificationService
from app.states.user_states import AccountPurchaseFlow
from app.utils.helpers import (
    edit_or_answer,
    format_toman,
    paginate_meta,
    parse_images,
    send_album,
    user_ref,
)

router = Router(name="user_account")


def _detail_text(acc: Account) -> str:
    return (
        f"🛒 <b>اکانت #{acc.id}</b>\n"
        f"{acc.title}\n\n"
        f"💵 قیمت: <b>{format_toman(acc.price)}</b>\n"
        f"🎚 لول: {acc.level}\n"
        f"🎽 تعداد اسکین: {acc.skins_count}\n"
        f"⭐️ تعداد الیت پس: {acc.elite_count}\n"
        f"🔫 اسکین اسلحه: {acc.gun_skins_count}\n\n"
        f"📝 توضیحات:\n{acc.description or '-'}"
    )


async def _send_list(target: Message, services: Services, page: int) -> None:
    items, total = await services.account.list_available(page=page, page_size=PAGE_SIZE)
    _, total_pages = paginate_meta(total, page, PAGE_SIZE)
    if total == 0:
        await target.answer("فعلاً اکانتی برای فروش موجود نیست. 🙏")
        return
    await target.answer(
        f"🛒 <b>لیست اکانت‌های موجود</b> ({total} اکانت)\nیکی را برای مشاهده جزئیات انتخاب کنید:",
        reply_markup=accounts_list_menu(items, page, total_pages),
    )


@router.message(F.text == BTN_BUY_ACCOUNT)
async def entry(message: Message, services: Services, state: FSMContext) -> None:
    await state.set_state(AccountPurchaseFlow.browsing)
    await _send_list(message, services, page=1)


@router.callback_query(AccountCB.filter(F.action == "page"))
async def change_page(
    callback: CallbackQuery, callback_data: AccountCB, services: Services
) -> None:
    items, total = await services.account.list_available(
        page=callback_data.page, page_size=PAGE_SIZE
    )
    _, total_pages = paginate_meta(total, callback_data.page, PAGE_SIZE)
    # edit_or_answer: the previous screen may be a photo (account detail), which
    # can't be edited into a text list — fall back to a fresh message there.
    await edit_or_answer(
        callback.message,
        f"🛒 <b>لیست اکانت‌های موجود</b> ({total} اکانت):",
        reply_markup=accounts_list_menu(items, callback_data.page, total_pages),
    )
    await callback.answer()


@router.callback_query(AccountCB.filter(F.action == "view"))
async def view_account(
    callback: CallbackQuery, callback_data: AccountCB, services: Services, bot
) -> None:
    acc = await services.account.get(callback_data.account_id)
    if acc is None:
        await callback.answer("اکانت یافت نشد.", show_alert=True)
        return
    images = parse_images(acc.images)
    kb = account_detail_menu(acc.id, callback_data.page)
    if images:
        # Albums can't carry inline buttons, so the gallery goes out first and the
        # action buttons follow in a separate message.
        await send_album(
            bot, callback.message.chat.id, images, caption=_detail_text(acc)
        )
        await callback.message.answer("👇 برای خرید این اکانت:", reply_markup=kb)
    else:
        await edit_or_answer(callback.message, _detail_text(acc), reply_markup=kb)
    await callback.answer()


@router.callback_query(AccountCB.filter(F.action == "buy"))
async def buy_account(
    callback: CallbackQuery,
    callback_data: AccountCB,
    services: Services,
    state: FSMContext,
    db_user: User,
    bot,
) -> None:
    try:
        account = await services.account.reserve(callback_data.account_id, db_user.id)
    except AccountReservationError:
        await callback.answer("متاسفانه این اکانت دیگر موجود نیست.", show_alert=True)
        return
    order = await services.account.create_purchase_order(db_user.id, account)
    await services.commit()

    await state.update_data(order_id=order.id, account_id=account.id)
    await prompt_payment_method(
        callback,
        state,
        order_id=order.id,
        amount=account.price,
        receipt_state=AccountPurchaseFlow.awaiting_receipt,
        prefix=f"✅ اکانت #{account.id} برای شما رزرو شد.\n\n",
    )


@router.message(AccountPurchaseFlow.awaiting_receipt, F.photo)
async def account_receipt(
    message: Message, services: Services, state: FSMContext, db_user: User, bot
) -> None:
    data = await state.get_data()
    order = await services.order.get(data["order_id"])
    if order is None:
        await message.answer("سفارش یافت نشد.")
        await state.clear()
        return
    file_id = message.photo[-1].file_id
    await services.order.attach_receipt(order, file_id)
    await services.commit()

    await message.answer(
        f"✅ رسید دریافت شد. سفارش #{order.id} در حال بررسی است.",
        reply_markup=main_menu(db_user.is_admin),
    )
    notifier = NotificationService(bot)
    method_fa = PAYMENT_METHOD_FA.get(order.payment_method, "-")
    caption = (
        f"🆕 <b>خرید اکانت</b>\nسفارش: #{order.id}\n"
        f"اکانت: #{data['account_id']}\n"
        f"کاربر: {user_ref(db_user)}\n"
        f"روش پرداخت: {method_fa}\n"
        f"مبلغ: {format_toman(order.amount)}"
    )
    try:
        await bot.send_photo(
            settings.admin_id, file_id, caption=caption,
            reply_markup=admin_order_review(order.id),
        )
    except Exception:  # noqa: BLE001
        await notifier.notify_admin(caption, reply_markup=admin_order_review(order.id))
    await notifier.log_event(
        "خرید اکانت",
        {"سفارش": f"#{order.id}", "اکانت": f"#{data['account_id']}", "کاربر": user_ref(db_user)},
    )
    await state.clear()


@router.message(AccountPurchaseFlow.awaiting_receipt)
async def account_receipt_not_photo(message: Message) -> None:
    await message.answer("لطفاً تصویر رسید را ارسال کنید. 📸")
