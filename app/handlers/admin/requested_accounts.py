"""Admin: requested (wanted) accounts — deposit approval + manage approved list."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery

from app.container import Services
from app.core.constants import PAGE_SIZE, SaleRequestStatus
from app.filters.admin import IsAdmin
from app.keyboards.callbacks import AdminCB, AdminRequestedCB
from app.keyboards.inline import (
    requested_account_delete_confirm,
    requested_account_detail_menu,
    requested_accounts_menu,
)
from app.services.notification_service import NotificationService
from app.utils.helpers import edit_or_answer, format_toman, paginate_meta, user_ref

router = Router(name="admin_requested_accounts")

_LIST_PAGE_SIZE = 10


def _detail(req, user) -> str:
    return (
        f"📝 <b>اکانت درخواستی #{req.id}</b>\n"
        f"کاربر: {user_ref(user)}\n\n"
        f"💵 قیمت مدنظر: <b>{format_toman(req.target_price)}</b>\n"
        f"⭐️ الیت: {req.elite_count}\n"
        f"🎽 ست‌ها: {req.sets or '-'}\n"
        f"🔫 گان‌ها: {req.guns or '-'}\n"
        f"📝 توضیحات: {req.description or '-'}\n"
        f"💳 بیعانه: {format_toman(req.deposit_amount)} "
        f"({'پرداخت‌شده' if req.deposit_paid else 'پرداخت‌نشده'})"
    )


# ------------------- deposit approval (from the receipt photo) -------------------
@router.callback_query(AdminRequestedCB.filter(F.action == "approve_deposit"), IsAdmin())
async def approve_deposit(
    callback: CallbackQuery, callback_data: AdminRequestedCB, services: Services, bot
) -> None:
    req = await services.account.get_requested(callback_data.req_id)
    if req is None:
        await callback.answer("درخواست یافت نشد.", show_alert=True)
        return
    await services.account.approve_requested_deposit(req)
    await services.commit()
    user = await services.users.get(req.user_id)
    if user:
        await NotificationService(bot).notify_user(
            user.telegram_id,
            f"✅ بیعانه درخواست اکانت #{req.id} شما تایید شد و در حال پیگیری است.",
        )
    try:
        await callback.message.edit_caption(
            caption=(callback.message.caption or "") + "\n\n✅ بیعانه تایید شد.",
            reply_markup=None,
        )
    except Exception:  # noqa: BLE001
        pass
    await callback.answer("بیعانه تایید شد. به لیست اکانت‌های درخواستی اضافه شد.")


@router.callback_query(AdminRequestedCB.filter(F.action == "reject_deposit"), IsAdmin())
async def reject_deposit(
    callback: CallbackQuery, callback_data: AdminRequestedCB, services: Services, bot
) -> None:
    req = await services.account.get_requested(callback_data.req_id)
    if req is None:
        await callback.answer("درخواست یافت نشد.", show_alert=True)
        return
    await services.account.reject_requested_deposit(req)
    await services.commit()
    user = await services.users.get(req.user_id)
    if user:
        await NotificationService(bot).notify_user(
            user.telegram_id,
            f"❌ بیعانه درخواست اکانت #{req.id} شما تایید نشد. لطفاً با پشتیبانی در تماس باشید.",
        )
    try:
        await callback.message.edit_caption(
            caption=(callback.message.caption or "") + "\n\n❌ بیعانه رد شد.",
            reply_markup=None,
        )
    except Exception:  # noqa: BLE001
        pass
    await callback.answer("بیعانه رد شد.")


# ------------------- approved requested-accounts list -------------------
async def _show_list(message, services: Services, page: int) -> None:
    items, total = await services.account.list_requested(
        status=SaleRequestStatus.APPROVED, page=page, page_size=_LIST_PAGE_SIZE
    )
    _, total_pages = paginate_meta(total, page, _LIST_PAGE_SIZE)
    if total == 0:
        await edit_or_answer(message, "هیچ اکانت درخواستی تاییدشده‌ای وجود ندارد.")
        return
    await edit_or_answer(
        message,
        f"📝 <b>اکانت‌های درخواستی</b> ({total} مورد)\nیکی را انتخاب کنید:",
        reply_markup=requested_accounts_menu(items, page, total_pages),
    )


@router.callback_query(AdminCB.filter(F.action == "requested_accounts"), IsAdmin())
async def requested_home(callback: CallbackQuery, services: Services) -> None:
    await _show_list(callback.message, services, page=1)
    await callback.answer()


@router.callback_query(AdminRequestedCB.filter(F.action == "page"), IsAdmin())
async def requested_page(
    callback: CallbackQuery, callback_data: AdminRequestedCB, services: Services
) -> None:
    await _show_list(callback.message, services, page=callback_data.page)
    await callback.answer()


@router.callback_query(AdminRequestedCB.filter(F.action == "view"), IsAdmin())
async def requested_view(
    callback: CallbackQuery, callback_data: AdminRequestedCB, services: Services
) -> None:
    req = await services.account.get_requested(callback_data.req_id)
    if req is None:
        await callback.answer("درخواست یافت نشد.", show_alert=True)
        return
    user = await services.users.get(req.user_id)
    await edit_or_answer(
        callback.message,
        _detail(req, user),
        reply_markup=requested_account_detail_menu(req.id, callback_data.page),
    )
    await callback.answer()


@router.callback_query(AdminRequestedCB.filter(F.action == "delete"), IsAdmin())
async def requested_delete_prompt(
    callback: CallbackQuery, callback_data: AdminRequestedCB, services: Services
) -> None:
    req = await services.account.get_requested(callback_data.req_id)
    if req is None:
        await callback.answer("درخواست یافت نشد.", show_alert=True)
        return
    await edit_or_answer(
        callback.message,
        f"⚠️ درخواست اکانت #{req.id} حذف شود؟",
        reply_markup=requested_account_delete_confirm(req.id, callback_data.page),
    )
    await callback.answer()


@router.callback_query(AdminRequestedCB.filter(F.action == "confirm_delete"), IsAdmin())
async def requested_delete(
    callback: CallbackQuery, callback_data: AdminRequestedCB, services: Services
) -> None:
    req = await services.account.get_requested(callback_data.req_id)
    if req is None:
        await callback.answer("درخواست یافت نشد.", show_alert=True)
        return
    await services.account.delete_requested(req)
    await services.commit()
    await callback.answer("درخواست حذف شد.")
    await _show_list(callback.message, services, page=callback_data.page)
