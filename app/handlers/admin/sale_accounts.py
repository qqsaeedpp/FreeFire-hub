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
from app.services.account_service import is_account_visible_for_users
from app.states.admin_states import AccountEditFlow
from app.utils.entities import (
    EntityCard,
    dump_entities,
    entities_for_storage,
    entity_kwargs,
    has_custom_emoji,
    load_entities,
    normalize_with_entities,
)
from app.utils.helpers import (
    edit_or_answer,
    fmt_dt,
    format_toman,
    paginate_meta,
    parse_images,
    send_album,
)
from app.utils.validators import parse_price

router = Router(name="admin_sale_accounts")


def _img_line(acc: Account) -> str:
    images = parse_images(acc.images)
    return (
        f"🖼 تصاویر: {len(images)} عکس"
        if images
        else "🖼 ⚠️ برای این اکانت عکسی ثبت نشده است."
    )


def _vis_line(acc: Account) -> str:
    return (
        "🛒 نمایش برای کاربران: ✅ قابل مشاهده در فروشگاه"
        if is_account_visible_for_users(acc)
        else "🛒 نمایش برای کاربران: ⛔️ نمایش داده نمی‌شود"
    )


def _detail(acc: Account) -> str:
    return (
        f"🆔 شناسه: <b>#{acc.id}</b>\n"
        f"📝 عنوان: {acc.title}\n"
        f"💰 قیمت: <b>{format_toman(acc.price)}</b>\n"
        f"📊 وضعیت: {ACCOUNT_STATUS_FA.get(acc.status, acc.status)}\n"
        f"{_vis_line(acc)}\n"
        f"📅 تاریخ ثبت: {fmt_dt(acc.created_at)}\n\n"
        f"📄 توضیحات:\n{acc.description or '-'}\n\n"
        f"{_img_line(acc)}"
    )


def _detail_content(acc: Account) -> tuple[str, list | None]:
    """Management detail as ``(text, entities)``.

    Same layout as :func:`_detail`; rebuilt as text + entities only when the
    listing carries premium emoji (then sent with ``parse_mode=None``), otherwise
    the existing HTML string is returned (``entities is None``) unchanged.
    """
    title_ents = load_entities(acc.title_entities_json)
    desc_ents = load_entities(acc.description_entities_json)
    if not has_custom_emoji(title_ents) and not has_custom_emoji(desc_ents):
        return _detail(acc), None
    return (
        EntityCard()
        .text("🆔 شناسه: ").bold(f"#{acc.id}").text("\n")
        .text("📝 عنوان: ").text(acc.title or "-", title_ents).text("\n")
        .text("💰 قیمت: ").bold(format_toman(acc.price)).text("\n")
        .text(f"📊 وضعیت: {ACCOUNT_STATUS_FA.get(acc.status, acc.status)}\n")
        .text(f"{_vis_line(acc)}\n")
        .text(f"📅 تاریخ ثبت: {fmt_dt(acc.created_at)}\n\n")
        .text("📄 توضیحات:\n").text(acc.description or "-", desc_ents).text("\n\n")
        .text(_img_line(acc))
        .build()
    )


async def _send_detail(message, bot, acc: Account, page: int) -> None:
    """Send an account's images (album) followed by its detail + management buttons.

    A media group can't carry an inline keyboard, so the gallery (all stored
    images, as a MediaGroup when more than one) goes out first and the detail
    text — which always states the image count, or the «no images» warning —
    carries the buttons in a follow-up message. Images live in the account's own
    ``images`` CSV column, so they always belong to exactly this account.
    """
    images = parse_images(acc.images)
    if images:
        await send_album(bot, message.chat.id, images)
    text, entities = _detail_content(acc)
    await message.answer(
        text,
        reply_markup=manage_account_detail_menu(
            acc.id, page, acc.status == AccountStatus.HIDDEN
        ),
        **entity_kwargs(entities),
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
    callback: CallbackQuery, callback_data: AdminAccountCB, services: Services, bot
) -> None:
    acc = await services.account.get(callback_data.account_id)
    if acc is None:
        await callback.answer("اکانت یافت نشد.", show_alert=True)
        return
    await _send_detail(callback.message, bot, acc, callback_data.page)
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
    # Toggle refresh: update the detail message in place (status + button) so the
    # already-sent image gallery above it isn't re-sent on every hide/unhide.
    text, entities = _detail_content(acc)
    await edit_or_answer(
        callback.message,
        text,
        reply_markup=manage_account_detail_menu(acc.id, callback_data.page, True),
        entities=entities,
    )
    await callback.answer("اکانت مخفی شد.")


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
    text, entities = _detail_content(acc)
    await edit_or_answer(
        callback.message,
        text,
        reply_markup=manage_account_detail_menu(acc.id, callback_data.page, False),
        entities=entities,
    )
    await callback.answer("اکانت در فروشگاه نمایش داده شد.")


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
    # Capture premium emoji in the new title too; storing None when the admin
    # retypes a plain title clears any stale entities from the previous value.
    title, entities = normalize_with_entities(
        message.text, message.entities, max_len=255
    )
    await services.account.update_fields(
        acc,
        title=title,
        title_entities_json=dump_entities(entities_for_storage(entities)),
    )
    await services.commit()
    await state.clear()
    await message.answer(f"✅ عنوان اکانت #{acc.id} به‌روزرسانی شد.")
