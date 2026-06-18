"""Admin: wallet top-up requests — the «💰 سفارش‌های کیف پول» pending section.

Lists PENDING wallet-charge requests (paginated, 10/page), opens one with its
receipt, and approves/rejects through the shared :class:`WalletTopUpService` so the
wallet is credited **exactly once** (idempotent). The UX mirrors pending-orders:
the list message is edited in place into the detail and the receipt photo is sent
as a separate message; the instant-notification card path uses the ``page=0``
sentinel (same convention as the sale-account notifications). This is purely
additive — the legacy ``approve_topup``/``reject_topup`` buttons still work.
"""
from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from app.container import Services
from app.filters.admin import IsAdmin
from app.keyboards.callbacks import AdminCB, WalletTopUpCB
from app.keyboards.inline import wallet_topup_detail_menu, wallet_topup_list_menu
from app.services.notification_service import NotificationService
from app.utils.helpers import (
    edit_or_answer,
    format_toman,
    paginate_meta,
    user_ref,
    wallet_topup_detail_text,
)

router = Router(name="admin_wallet_requests")

_PAGE_SIZE = 10


async def _delete_receipt(bot, chat_id: int, state: FSMContext) -> None:
    """Remove the separate receipt-photo message sent for an opened request."""
    data = await state.get_data()
    mid = data.get("wtop_receipt_msg_id")
    if mid:
        try:
            await bot.delete_message(chat_id, mid)
        except Exception:  # noqa: BLE001 - already gone / too old to delete
            pass
        await state.update_data(wtop_receipt_msg_id=None)


async def _show_list(message, services: Services, page: int) -> None:
    """Render one page of pending requests, with a smart clamp when a page empties."""
    items, total = await services.wallet_topup.list_pending(
        page=page, page_size=_PAGE_SIZE
    )
    if total == 0:
        await edit_or_answer(message, "✅ درخواست شارژ کیف پولی در انتظار بررسی نیست.")
        return
    _, total_pages = paginate_meta(total, page, _PAGE_SIZE)
    if page > total_pages:  # the last item on a stale page was just processed
        page = total_pages
        items, total = await services.wallet_topup.list_pending(
            page=page, page_size=_PAGE_SIZE
        )
    rows = [(req, await services.users.get(req.user_id)) for req in items]
    await edit_or_answer(
        message,
        f"💰 <b>سفارش‌های کیف پول</b> ({total} درخواست)\nیکی را انتخاب کنید:",
        reply_markup=wallet_topup_list_menu(rows, page, total_pages),
    )


async def _show_detail(
    callback: CallbackQuery, services: Services, state: FSMContext, bot, req, page: int
) -> None:
    """Edit the message into the full request detail + (re)show the receipt photo."""
    user = await services.users.get(req.user_id)
    await edit_or_answer(
        callback.message,
        wallet_topup_detail_text(req, user),
        reply_markup=wallet_topup_detail_menu(req.id, page),
    )
    # On the notification card the receipt is already on screen (the card *is* the
    # photo); from the list detail (a text message) send it as a separate message.
    if req.receipt_file_id and callback.message.photo is None:
        await _delete_receipt(bot, callback.message.chat.id, state)
        sent = await callback.message.answer_photo(
            req.receipt_file_id, caption=f"📷 رسید درخواست شارژ #{req.id}"
        )
        await state.update_data(wtop_receipt_msg_id=sent.message_id)


async def _refresh_after(
    callback: CallbackQuery,
    services: Services,
    state: FSMContext,
    bot,
    page: int,
    note: str | None,
) -> None:
    """After a decision: refresh the in-place list, or annotate the notification card.

    ``page >= 1`` + a text message → acted from the list detail: drop the receipt
    photo and reshow the live list so the processed request disappears. Otherwise
    (``page == 0`` or a photo card) → strip the buttons and append ``note`` to the
    caption. ``note`` is ``None`` when the request was already processed (nothing
    new to announce), in which case only the buttons are removed.
    """
    msg = callback.message
    if page >= 1 and msg.photo is None:
        await _delete_receipt(bot, msg.chat.id, state)
        await _show_list(msg, services, page)
        return
    try:
        if note:
            await msg.edit_caption(
                caption=(msg.caption or "") + f"\n\n{note}", reply_markup=None
            )
        else:
            await msg.edit_reply_markup(reply_markup=None)
    except Exception:  # noqa: BLE001 - caption unchanged / message too old
        pass


# ------------------------------ list & detail ------------------------------
@router.callback_query(AdminCB.filter(F.action == "wallet_requests"), IsAdmin())
async def wallet_requests_home(
    callback: CallbackQuery, services: Services, state: FSMContext, bot
) -> None:
    await _delete_receipt(bot, callback.message.chat.id, state)
    await _show_list(callback.message, services, page=1)
    await callback.answer()


@router.callback_query(WalletTopUpCB.filter(F.action == "page"), IsAdmin())
async def wallet_requests_page(
    callback: CallbackQuery,
    callback_data: WalletTopUpCB,
    services: Services,
    state: FSMContext,
    bot,
) -> None:
    await _delete_receipt(bot, callback.message.chat.id, state)
    await _show_list(callback.message, services, page=max(1, callback_data.page))
    await callback.answer()


@router.callback_query(WalletTopUpCB.filter(F.action == "view"), IsAdmin())
@router.callback_query(WalletTopUpCB.filter(F.action == "details"), IsAdmin())
async def wallet_request_view(
    callback: CallbackQuery,
    callback_data: WalletTopUpCB,
    services: Services,
    state: FSMContext,
    bot,
) -> None:
    req = await services.wallet_topup.get(callback_data.req_id)
    if req is None:
        await callback.answer("درخواست یافت نشد.", show_alert=True)
        return
    await _show_detail(callback, services, state, bot, req, callback_data.page)
    await callback.answer()


# ------------------------------ decisions ------------------------------
@router.callback_query(WalletTopUpCB.filter(F.action == "approve"), IsAdmin())
async def wallet_request_approve(
    callback: CallbackQuery,
    callback_data: WalletTopUpCB,
    services: Services,
    state: FSMContext,
    bot,
) -> None:
    req = await services.wallet_topup.get(callback_data.req_id)
    if req is None:
        await callback.answer("درخواست یافت نشد.", show_alert=True)
        return
    credited = await services.wallet_topup.approve(req)
    await services.commit()
    notifier = NotificationService(bot)
    if credited is None:  # already processed → idempotent no-op (no double credit)
        await callback.answer("این درخواست قبلاً بررسی شده است.", show_alert=True)
        await _refresh_after(callback, services, state, bot, callback_data.page, None)
        return
    user = await services.users.get(req.user_id)
    if user:
        await notifier.notify_user(
            user.telegram_id,
            "✅ درخواست شارژ کیف پول شما تایید شد.\n"
            f"💰 مبلغ شارژ شده:\n{format_toman(credited)}",
        )
    await notifier.log_event(
        "شارژ کیف پول",
        {"وضعیت": "تایید و شارژ شد", "کاربر": user_ref(user), "مبلغ": format_toman(credited)},
    )
    await callback.answer("شارژ تایید شد.")
    await _refresh_after(
        callback, services, state, bot, callback_data.page, "✅ تایید و شارژ شد."
    )


@router.callback_query(WalletTopUpCB.filter(F.action == "reject"), IsAdmin())
async def wallet_request_reject(
    callback: CallbackQuery,
    callback_data: WalletTopUpCB,
    services: Services,
    state: FSMContext,
    bot,
) -> None:
    req = await services.wallet_topup.get(callback_data.req_id)
    if req is None:
        await callback.answer("درخواست یافت نشد.", show_alert=True)
        return
    ok = await services.wallet_topup.reject(req)
    await services.commit()
    notifier = NotificationService(bot)
    if not ok:  # already processed → idempotent no-op
        await callback.answer("این درخواست قبلاً بررسی شده است.", show_alert=True)
        await _refresh_after(callback, services, state, bot, callback_data.page, None)
        return
    user = await services.users.get(req.user_id)
    if user:
        await notifier.notify_user(
            user.telegram_id, "❌ درخواست شارژ کیف پول شما رد شد."
        )
    await notifier.log_event(
        "شارژ کیف پول",
        {"وضعیت": "رد شد", "کاربر": user_ref(user), "مبلغ": format_toman(req.amount)},
    )
    await callback.answer("درخواست رد شد.")
    await _refresh_after(
        callback, services, state, bot, callback_data.page, "❌ رد شد."
    )
