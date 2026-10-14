"""Admin: 👮 مدیریت ادمین‌ها — owner-only roster management.

Owners (the bootstrap ``ADMIN_ID`` ids) can add unlimited admins, remove
panel-added admins, and view the full list with roles. A newly added admin gets
access immediately on their next interaction (no restart) because the privilege
is mirrored onto ``User.is_admin`` and the membership cache is invalidated.

Owners also pick which admin the green «✅ خرید» button under a new-listing
announcement opens («🛒 ادمین دکمهٔ خرید», see ``BuyContactService``).
"""
from __future__ import annotations

from html import escape

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
from app.services.buy_contact_service import BuyContact, BuyContactError, default_username
from app.services.notification_service import NotificationService
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
    kb.button(text="🛒 ادمین دکمهٔ خرید", callback_data=AdminMgmtCB(action="buy_menu"))
    kb.button(text="➕ افزودن ادمین", callback_data=AdminMgmtCB(action="add"))
    kb.button(text="🔙 بازگشت", callback_data=AdminCB(action="back_home"))
    kb.adjust(1)
    return kb.as_markup()


def _contact_label(contact: BuyContact) -> str:
    return f"@{contact.username}" + (" (پیش‌فرض)" if contact.is_default else "")


async def _show_list(services: Services, message: Message) -> None:
    entries = await services.admin.list_admins()
    lines = ["👮 <b>مدیریت ادمین‌ها</b>\n"]
    lines.extend(_entry_line(e) for e in entries)
    contact = await services.buy_contact.current()
    lines.append(f"🛒 <b>دکمهٔ «خرید» آگهی‌ها به پیوی:</b> {_contact_label(contact)}")
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


# ------------------------- buy-button contact -------------------------
def _buy_menu_markup(entries: list[AdminEntry], current: BuyContact) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for entry in entries:
        if not entry.username:
            continue
        picked = entry.username.lower() == current.username.lower()
        name = (entry.first_name or "").strip()[:30]
        kb.button(
            text=("✅ " if picked else "") + f"@{entry.username}" + (f" — {name}" if name else ""),
            callback_data=AdminMgmtCB(action="buy_set", user_id=entry.user_id),
        )
    if not current.is_default:
        kb.button(
            text=f"↩️ بازگشت به پیش‌فرض (@{default_username()})",
            callback_data=AdminMgmtCB(action="buy_reset"),
        )
    kb.button(text="🔙 بازگشت", callback_data=AdminMgmtCB(action="home"))
    kb.adjust(1)
    return kb.as_markup()


async def _show_buy_menu(services: Services, message: Message) -> None:
    current = await services.buy_contact.current()
    entries = await services.buy_contact.candidates()
    text = (
        "🛒 <b>ادمین دکمهٔ «خرید»</b>\n\n"
        "وقتی کاربر زیر آگهی اکانت روی «✅ خرید» بزند، به پیوی این ادمین می‌رود "
        "(در ربات و در کانال‌های تبلیغ، برای آگهی‌های بعدی).\n\n"
        f"ادمین فعلی: {_contact_label(current)}\n\n"
        "یکی از ادمین‌ها را انتخاب کنید:"
    )
    no_username = [escape(e.first_name or str(e.user_id)) for e in entries if not e.username]
    if no_username:
        text += (
            "\n\n⚠️ این ادمین‌ها یوزرنیم ندارند و قابل انتخاب نیستند: "
            + "، ".join(no_username)
        )
    await edit_or_answer(message, text, reply_markup=_buy_menu_markup(entries, current))


async def _log_buy_change(bot, old: BuyContact, new: BuyContact, by: int) -> None:
    await NotificationService(bot).log_event(
        "تغییر تنظیمات",
        {
            "فیلد": "ادمین دکمهٔ خرید",
            "مقدار قبلی": _contact_label(old),
            "مقدار جدید": _contact_label(new),
            "توسط": str(by),
        },
    )


@router.callback_query(AdminMgmtCB.filter(F.action == "buy_menu"), IsAdmin())
async def buy_contact_menu(
    callback: CallbackQuery, services: Services, state: FSMContext
) -> None:
    if not _require_owner(services, callback.from_user.id):
        await callback.answer("فقط مالک ربات به این بخش دسترسی دارد.", show_alert=True)
        return
    await state.clear()
    await _show_buy_menu(services, callback.message)
    await callback.answer()


@router.callback_query(AdminMgmtCB.filter(F.action == "buy_set"), IsAdmin())
async def buy_contact_set(
    callback: CallbackQuery, callback_data: AdminMgmtCB, services: Services, bot
) -> None:
    if not _require_owner(services, callback.from_user.id):
        await callback.answer("فقط مالک ربات به این بخش دسترسی دارد.", show_alert=True)
        return
    old = await services.buy_contact.current()
    try:
        new = await services.buy_contact.select(
            callback_data.user_id, changed_by=callback.from_user.id
        )
    except BuyContactError as exc:
        await callback.answer(str(exc), show_alert=True)
        await _show_buy_menu(services, callback.message)
        return
    await services.commit()
    await callback.answer(f"✅ دکمهٔ خرید از این پس به پیوی @{new.username} می‌رود.")
    await _show_buy_menu(services, callback.message)
    await _log_buy_change(bot, old, new, callback.from_user.id)


@router.callback_query(AdminMgmtCB.filter(F.action == "buy_reset"), IsAdmin())
async def buy_contact_reset(callback: CallbackQuery, services: Services, bot) -> None:
    if not _require_owner(services, callback.from_user.id):
        await callback.answer("فقط مالک ربات به این بخش دسترسی دارد.", show_alert=True)
        return
    old = await services.buy_contact.current()
    new = await services.buy_contact.reset(changed_by=callback.from_user.id)
    await services.commit()
    await callback.answer(f"✅ دکمهٔ خرید به پیش‌فرض (@{new.username}) برگشت.")
    await _show_buy_menu(services, callback.message)
    await _log_buy_change(bot, old, new, callback.from_user.id)
