"""Admin: manage shop accounts — browse, hide/unhide, edit price/title, delete."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.container import Services
from app.core.constants import ACCOUNT_STATUS_FA, PAGE_SIZE, AccountStatus
from app.filters.admin import IsAdmin
from app.keyboards.callbacks import AdminAccountCB, AdminCB
from app.keyboards.inline import (
    cancel_only,
    manage_account_delete_confirm,
    manage_account_detail_menu,
    manage_accounts_menu,
)
from app.models.account import Account
from app.states.admin_states import AccountEditFlow
from app.utils.helpers import edit_or_answer, format_toman, paginate_meta
from app.utils.validators import parse_price

router = Router(name="admin_sale_accounts")


def _detail(acc: Account) -> str:
    return (
        f"🗂 <b>اکانت #{acc.id}</b>\n"
        f"{acc.title}\n\n"
        f"💵 قیمت: <b>{format_toman(acc.price)}</b>\n"
        f"وضعیت: {ACCOUNT_STATUS_FA.get(acc.status, acc.status)}\n\n"
        f"📝 {acc.description or '-'}"
    )


async def _show_list(message, services: Services, page: int) -> None:
    items, total = await services.account.list_manageable(page=page, page_size=PAGE_SIZE)
    _, total_pages = paginate_meta(total, page, PAGE_SIZE)
    if total == 0:
        await edit_or_answer(message, "هیچ اکانتی برای مدیریت وجود ندارد.")
        return
    await edit_or_answer(
        message,
        f"🗂 <b>مدیریت اکانت‌های فروش</b> ({total} اکانت)\nیکی را انتخاب کنید:",
        reply_markup=manage_accounts_menu(items, page, total_pages),
    )


@router.callback_query(AdminCB.filter(F.action == "manage_accounts"), IsAdmin())
async def manage_home(callback: CallbackQuery, services: Services) -> None:
    await _show_list(callback.message, services, page=1)
    await callback.answer()


@router.callback_query(AdminAccountCB.filter(F.action == "page"), IsAdmin())
async def manage_page(
    callback: CallbackQuery, callback_data: AdminAccountCB, services: Services
) -> None:
    await _show_list(callback.message, services, page=callback_data.page)
    await callback.answer()


@router.callback_query(AdminAccountCB.filter(F.action == "view"), IsAdmin())
async def manage_view(
    callback: CallbackQuery, callback_data: AdminAccountCB, services: Services
) -> None:
    acc = await services.account.get(callback_data.account_id)
    if acc is None:
        await callback.answer("اکانت یافت نشد.", show_alert=True)
        return
    await edit_or_answer(
        callback.message,
        _detail(acc),
        reply_markup=manage_account_detail_menu(
            acc.id, callback_data.page, acc.status == AccountStatus.HIDDEN
        ),
    )
    await callback.answer()


@router.callback_query(AdminAccountCB.filter(F.action == "hide"), IsAdmin())
async def manage_hide(
    callback: CallbackQuery, callback_data: AdminAccountCB, services: Services
) -> None:
    acc = await services.account.get(callback_data.account_id)
    if acc is None:
        await callback.answer("اکانت یافت نشد.", show_alert=True)
        return
    await services.account.hide(acc)
    await services.commit()
    await manage_view(callback, callback_data, services)


@router.callback_query(AdminAccountCB.filter(F.action == "unhide"), IsAdmin())
async def manage_unhide(
    callback: CallbackQuery, callback_data: AdminAccountCB, services: Services
) -> None:
    acc = await services.account.get(callback_data.account_id)
    if acc is None:
        await callback.answer("اکانت یافت نشد.", show_alert=True)
        return
    await services.account.unhide(acc)
    await services.commit()
    await manage_view(callback, callback_data, services)


@router.callback_query(AdminAccountCB.filter(F.action == "delete"), IsAdmin())
async def manage_delete_prompt(
    callback: CallbackQuery, callback_data: AdminAccountCB, services: Services
) -> None:
    acc = await services.account.get(callback_data.account_id)
    if acc is None:
        await callback.answer("اکانت یافت نشد.", show_alert=True)
        return
    await edit_or_answer(
        callback.message,
        f"⚠️ اکانت #{acc.id} حذف شود؟ اکانت از فروشگاه و لیست مدیریت حذف می‌شود "
        f"ولی سابقه فروش آن حفظ خواهد شد.",
        reply_markup=manage_account_delete_confirm(acc.id, callback_data.page),
    )
    await callback.answer()


@router.callback_query(AdminAccountCB.filter(F.action == "confirm_delete"), IsAdmin())
async def manage_delete(
    callback: CallbackQuery, callback_data: AdminAccountCB, services: Services
) -> None:
    acc = await services.account.get(callback_data.account_id)
    if acc is None:
        await callback.answer("اکانت یافت نشد.", show_alert=True)
        return
    await services.account.remove(acc)
    await services.commit()
    await callback.answer("اکانت حذف شد.")
    await _show_list(callback.message, services, page=callback_data.page)


@router.callback_query(AdminAccountCB.filter(F.action == "edit_price"), IsAdmin())
async def manage_edit_price_start(
    callback: CallbackQuery, callback_data: AdminAccountCB, state: FSMContext
) -> None:
    await state.set_state(AccountEditFlow.entering_price)
    await state.update_data(edit_account_id=callback_data.account_id, edit_page=callback_data.page)
    await edit_or_answer(
        callback.message, "💵 قیمت جدید (تومان) را وارد کنید:", reply_markup=cancel_only()
    )
    await callback.answer()


@router.message(AccountEditFlow.entering_price, F.text, IsAdmin())
async def manage_edit_price_save(
    message: Message, services: Services, state: FSMContext
) -> None:
    price = parse_price(message.text)
    if price is None or price <= 0:
        await message.answer("❌ قیمت نامعتبر است.")
        return
    data = await state.get_data()
    acc = await services.account.get(data["edit_account_id"])
    if acc is None:
        await message.answer("اکانت یافت نشد.")
        await state.clear()
        return
    await services.account.update_fields(acc, price=price)
    await services.commit()
    await state.clear()
    await message.answer(f"✅ قیمت اکانت #{acc.id} به {format_toman(price)} تغییر یافت.")


@router.callback_query(AdminAccountCB.filter(F.action == "edit_title"), IsAdmin())
async def manage_edit_title_start(
    callback: CallbackQuery, callback_data: AdminAccountCB, state: FSMContext
) -> None:
    await state.set_state(AccountEditFlow.entering_title)
    await state.update_data(edit_account_id=callback_data.account_id, edit_page=callback_data.page)
    await edit_or_answer(
        callback.message, "✏️ عنوان جدید اکانت را وارد کنید:", reply_markup=cancel_only()
    )
    await callback.answer()


@router.message(AccountEditFlow.entering_title, F.text, IsAdmin())
async def manage_edit_title_save(
    message: Message, services: Services, state: FSMContext
) -> None:
    data = await state.get_data()
    acc = await services.account.get(data["edit_account_id"])
    if acc is None:
        await message.answer("اکانت یافت نشد.")
        await state.clear()
        return
    await services.account.update_fields(acc, title=message.text.strip()[:255])
    await services.commit()
    await state.clear()
    await message.answer(f"✅ عنوان اکانت #{acc.id} به‌روزرسانی شد.")
