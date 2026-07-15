"""Admin: 👮 مدیریت ادمین‌ها — owner-only roster management.

Owners (the bootstrap ``ADMIN_ID`` ids) can add unlimited admins, remove
panel-added admins, and view the full list with roles. A newly added admin gets
access immediately on their next interaction (no restart) because the privilege
is mirrored onto ``User.is_admin`` and the membership cache is invalidated.
"""
from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.container import Services
from app.core.constants import ADMIN_ROLE_FA, AdminRole
from app.filters.admin import IsAdmin
from app.keyboards.callbacks import AdminCB, AdminMgmtCB
from app.keyboards.inline import cancel_only
from app.services.admin_service import AdminEntry, AdminError
from app.states.admin_states import AdminManageFlow
from app.utils.helpers import edit_or_answer, user_profile_link
from app.utils.validators import parse_price

router = Router(name="admin_admins")


def _entry_line(entry: AdminEntry) -> str:
    handle = f"@{entry.username}" if entry.username else "بدون یوزرنیم"
    # Tappable profile link for the name, so an admin without a @username is still
    # reachable in one tap (tg://user?id=). Falls back to «—» when no name.
    name = user_profile_link(entry.user_id, entry.first_name) or "—"
    return (
        f"{ADMIN_ROLE_FA[entry.role]} | {name}\n"
        f"<code>{entry.user_id}</code> | {handle}"
    )


def _list_markup(entries: list[AdminEntry]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for entry in entries:
        if entry.removable:
            kb.button(
                text=f"🗑 حذف {entry.first_name or entry.user_id}",
                callback_data=AdminMgmtCB(action="confirm_remove", user_id=entry.user_id),
            )
    kb.button(text="➕ افزودن ادمین", callback_data=AdminMgmtCB(action="add"))
    kb.button(text="🔙 بازگشت", callback_data=AdminCB(action="back_home"))
    kb.adjust(1)
    return kb.as_markup()


async def _show_list(services: Services, message: Message) -> None:
    entries = await services.admin.list_admins()
    lines = ["👮 <b>مدیریت ادمین‌ها</b>\n"]
    lines.extend(_entry_line(e) for e in entries)
    lines.append("\n👑 مالک قابل حذف نیست. برای افزودن، آیدی عددی کاربر را دارید.")
    await edit_or_answer(
        message, "\n\n".join(lines), reply_markup=_list_markup(entries)
    )


def _require_owner(services: Services, user_id: int) -> bool:
    return services.admin.is_owner(user_id)


# --------------------------------- home ---------------------------------
@router.callback_query(AdminCB.filter(F.action == "admins"), IsAdmin())
async def admins_home(
    callback: CallbackQuery, services: Services, state: FSMContext
) -> None:
    if not _require_owner(services, callback.from_user.id):
        await callback.answer("فقط مالک ربات به این بخش دسترسی دارد.", show_alert=True)
        return
    await state.clear()
    await _show_list(services, callback.message)
    await callback.answer()


# ---------------------------------- add ----------------------------------
@router.callback_query(AdminMgmtCB.filter(F.action == "add"), IsAdmin())
async def admin_add_start(
    callback: CallbackQuery, services: Services, state: FSMContext
) -> None:
    if not _require_owner(services, callback.from_user.id):
        await callback.answer("فقط مالک ربات می‌تواند ادمین اضافه کند.", show_alert=True)
        return
    await state.set_state(AdminManageFlow.entering_user)
    await edit_or_answer(
        callback.message,
        "➕ <b>افزودن ادمین</b>\n\n"
        "آیدی عددی تلگرام کاربر را وارد کنید.\n"
        "⚠️ کاربر باید قبلاً ربات را استارت کرده باشد.",
        reply_markup=cancel_only(),
    )
    await callback.answer()


@router.message(AdminManageFlow.entering_user, F.text, IsAdmin())
async def admin_add_save(
    message: Message, services: Services, state: FSMContext
) -> None:
    if not _require_owner(services, message.from_user.id):
        await state.clear()
        return
    user_id = parse_price(message.text)
    if user_id is None or user_id <= 0:
        await message.answer("آیدی نامعتبر است. یک عدد معتبر وارد کنید.")
        return
    try:
        admin = await services.admin.add_admin(user_id, role=AdminRole.ADMIN)
    except AdminError as exc:
        await message.answer(f"❌ {exc}", reply_markup=cancel_only())
        return
    await services.commit()
    await state.clear()
    name = admin.first_name or str(admin.user_id)
    await message.answer(f"✅ «{name}» به‌عنوان ادمین اضافه شد و دسترسی فعال شد.")
    await _show_list(services, message)


# -------------------------------- remove --------------------------------
@router.callback_query(AdminMgmtCB.filter(F.action == "confirm_remove"), IsAdmin())
async def admin_confirm_remove(
    callback: CallbackQuery, callback_data: AdminMgmtCB, services: Services
) -> None:
    if not _require_owner(services, callback.from_user.id):
        await callback.answer("فقط مالک ربات می‌تواند ادمین حذف کند.", show_alert=True)
        return
    kb = InlineKeyboardBuilder()
    kb.button(
        text="✅ بله، حذف کن",
        callback_data=AdminMgmtCB(action="remove", user_id=callback_data.user_id),
    )
    kb.button(text="🔙 انصراف", callback_data=AdminMgmtCB(action="home"))
    kb.adjust(1)
    await edit_or_answer(
        callback.message,
        f"⚠️ آیا از حذف دسترسی ادمین <code>{callback_data.user_id}</code> مطمئن هستید؟",
        reply_markup=kb.as_markup(),
    )
    await callback.answer()


@router.callback_query(AdminMgmtCB.filter(F.action == "remove"), IsAdmin())
async def admin_remove(
    callback: CallbackQuery, callback_data: AdminMgmtCB, services: Services
) -> None:
    if not _require_owner(services, callback.from_user.id):
        await callback.answer("فقط مالک ربات می‌تواند ادمین حذف کند.", show_alert=True)
        return
    try:
        await services.admin.remove_admin(callback_data.user_id)
    except AdminError as exc:
        await callback.answer(str(exc), show_alert=True)
        await _show_list(services, callback.message)
        return
    await services.commit()
    await callback.answer("ادمین حذف شد.")
    await _show_list(services, callback.message)


@router.callback_query(AdminMgmtCB.filter(F.action == "home"), IsAdmin())
async def admin_mgmt_home(
    callback: CallbackQuery, services: Services, state: FSMContext
) -> None:
    if not _require_owner(services, callback.from_user.id):
        await callback.answer("فقط مالک ربات به این بخش دسترسی دارد.", show_alert=True)
        return
    await state.clear()
    await _show_list(services, callback.message)
    await callback.answer()
