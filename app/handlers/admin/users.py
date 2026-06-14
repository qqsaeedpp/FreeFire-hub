"""Admin: 🚫 مدیریت کاربران — ban / unban users with a reason.

Banning sets the ``User.is_banned`` flag the gate reads and writes an audit row
(reason / banned_by / banned_at). Owners and admins are protected by the service.
The list shows every currently-active ban with a one-tap unban button.
"""
from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.container import Services
from app.filters.admin import IsAdmin
from app.keyboards.callbacks import AdminCB, UserAdminCB
from app.keyboards.inline import cancel_only
from app.services.ban_service import BanEntry, BanError
from app.services.notification_service import NotificationService
from app.states.admin_states import UserBanFlow
from app.utils.helpers import edit_or_answer, fmt_dt, paginate_meta
from app.utils.validators import parse_price

router = Router(name="admin_users")

_PAGE_SIZE = 10


def _ban_line(entry: BanEntry) -> str:
    handle = f"@{entry.username}" if entry.username else "بدون یوزرنیم"
    name = entry.full_name or "—"
    reason = entry.reason or "—"
    by = f"<code>{entry.banned_by}</code>" if entry.banned_by else "—"
    return (
        f"🚫 <code>{entry.user_id}</code> | {handle}\n"
        f"   👤 {name}\n"
        f"   📝 دلیل: {reason}\n"
        f"   📅 {fmt_dt(entry.banned_at)} | توسط: {by}"
    )


def _list_markup(
    entries: list[BanEntry], page: int, total_pages: int
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for e in entries:
        kb.button(
            text=f"✅ رفع بن {e.full_name or e.user_id}",
            callback_data=UserAdminCB(action="confirm_unban", user_id=e.user_id, page=page),
        )
    kb.button(text="🚫 بن کردن کاربر", callback_data=UserAdminCB(action="ban"))
    nav: list = []
    if page > 1:
        nav.append(("⬅️ قبلی", UserAdminCB(action="page", page=page - 1)))
    if page < total_pages:
        nav.append(("بعدی ➡️", UserAdminCB(action="page", page=page + 1)))
    for text, cb in nav:
        kb.button(text=text, callback_data=cb)
    kb.button(text="🔙 بازگشت", callback_data=AdminCB(action="back_home"))
    # one ban-row per line, then the add button, an optional nav row, then back
    rows = [1] * len(entries) + [1] + ([len(nav)] if nav else []) + [1]
    kb.adjust(*rows)
    return kb.as_markup()


async def _show_list(message, services: Services, page: int) -> None:
    entries, total = await services.ban.list_banned(page=page, page_size=_PAGE_SIZE)
    _, total_pages = paginate_meta(total, page, _PAGE_SIZE)
    header = f"🚫 <b>مدیریت کاربران</b>\nکاربران مسدود: <b>{total}</b>"
    body = "\n\n".join(_ban_line(e) for e in entries) or "هیچ کاربر مسدودی وجود ندارد."
    await edit_or_answer(
        message,
        f"{header}\n\n———\n\n{body}",
        reply_markup=_list_markup(entries, page, total_pages),
    )


# --------------------------------- home ---------------------------------
@router.callback_query(AdminCB.filter(F.action == "users"), IsAdmin())
async def users_home(
    callback: CallbackQuery, services: Services, state: FSMContext
) -> None:
    await state.clear()
    await _show_list(callback.message, services, page=1)
    await callback.answer()


@router.callback_query(UserAdminCB.filter(F.action == "page"), IsAdmin())
async def users_page(
    callback: CallbackQuery, callback_data: UserAdminCB, services: Services
) -> None:
    await _show_list(callback.message, services, page=callback_data.page)
    await callback.answer()


# ---------------------------------- ban ----------------------------------
@router.callback_query(UserAdminCB.filter(F.action == "ban"), IsAdmin())
async def ban_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(UserBanFlow.entering_user)
    await edit_or_answer(
        callback.message,
        "🚫 <b>بن کردن کاربر</b>\n\nآیدی عددی تلگرام کاربر را وارد کنید:",
        reply_markup=cancel_only(),
    )
    await callback.answer()


@router.message(UserBanFlow.entering_user, F.text, IsAdmin())
async def ban_user_id(
    message: Message, services: Services, state: FSMContext
) -> None:
    user_id = parse_price(message.text)
    if user_id is None or user_id <= 0:
        await message.answer("آیدی نامعتبر است. یک عدد معتبر وارد کنید.")
        return
    await state.update_data(ban_user_id=user_id)
    await state.set_state(UserBanFlow.entering_reason)
    await message.answer(
        "📝 دلیل بن را وارد کنید.\n"
        "مثال: اسپم، سوءاستفاده از سیستم، پرداخت نامعتبر، تخلف",
        reply_markup=cancel_only(),
    )


@router.message(UserBanFlow.entering_reason, F.text, IsAdmin())
async def ban_reason(
    message: Message, services: Services, state: FSMContext, bot
) -> None:
    data = await state.get_data()
    user_id = int(data["ban_user_id"])
    reason = message.text.strip()
    try:
        await services.ban.ban_user(
            user_id, reason=reason, banned_by=message.from_user.id
        )
    except BanError as exc:
        await message.answer(f"❌ {exc}", reply_markup=cancel_only())
        return
    await services.commit()
    await state.clear()
    await message.answer(f"✅ کاربر <code>{user_id}</code> مسدود شد.\n📝 دلیل: {reason}")
    # Best-effort: tell the user and log the action.
    await NotificationService(bot).notify_user(
        user_id,
        "🚫 حساب شما توسط مدیریت مسدود شده است.\n\n"
        "در صورت نیاز با مدیریت مجموعه تماس بگیرید.",
    )
    await NotificationService(bot).log_event(
        "مسدودسازی کاربر",
        {"کاربر": f"<code>{user_id}</code>", "دلیل": reason, "توسط": f"<code>{message.from_user.id}</code>"},
    )
    await _show_list(message, services, page=1)


# --------------------------------- unban ---------------------------------
@router.callback_query(UserAdminCB.filter(F.action == "confirm_unban"), IsAdmin())
async def unban_confirm(
    callback: CallbackQuery, callback_data: UserAdminCB
) -> None:
    kb = InlineKeyboardBuilder()
    kb.button(
        text="✅ بله، رفع بن",
        callback_data=UserAdminCB(
            action="unban", user_id=callback_data.user_id, page=callback_data.page
        ),
    )
    kb.button(
        text="🔙 انصراف", callback_data=UserAdminCB(action="page", page=callback_data.page)
    )
    kb.adjust(1)
    await edit_or_answer(
        callback.message,
        f"⚠️ آیا از رفع بن کاربر <code>{callback_data.user_id}</code> مطمئن هستید؟",
        reply_markup=kb.as_markup(),
    )
    await callback.answer()


@router.callback_query(UserAdminCB.filter(F.action == "unban"), IsAdmin())
async def unban(
    callback: CallbackQuery, callback_data: UserAdminCB, services: Services, bot
) -> None:
    try:
        await services.ban.unban_user(callback_data.user_id)
    except BanError as exc:
        await callback.answer(str(exc), show_alert=True)
        await _show_list(callback.message, services, page=callback_data.page)
        return
    await services.commit()
    await callback.answer("کاربر رفع بن شد.")
    await NotificationService(bot).notify_user(
        callback_data.user_id, "✅ مسدودیت حساب شما برداشته شد. اکنون می‌توانید از ربات استفاده کنید."
    )
    await _show_list(callback.message, services, page=callback_data.page)
