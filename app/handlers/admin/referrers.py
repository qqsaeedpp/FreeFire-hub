"""Admin: invite management — browse referrers and each one's invited users."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.container import Services
from app.filters.admin import IsAdmin
from app.keyboards.callbacks import AdminCB, AdminReferrerCB
from app.keyboards.inline import referred_detail_menu, referrers_menu
from app.utils.helpers import (
    edit_or_answer,
    fmt_dt,
    format_toman,
    format_user_display,
    paginate_meta,
    user_profile_link,
)

router = Router(name="admin_referrers")

_PAGE_SIZE = 10


def _referred_line(ref, user) -> str:
    """One invited-user row: id, username, first name, invite date, reward state."""
    if user is not None:
        uid = user.telegram_id
        handle = f"@{user.username}" if user.username else "بدون یوزرنیم"
        name = user_profile_link(user.telegram_id, user.full_name) or "-"
    else:
        uid = ref.referred_id
        handle = "بدون یوزرنیم"
        name = "-"
    reward = "✅ پرداخت‌شده" if ref.rewarded else "⛔️ پرداخت‌نشده"
    return (
        f"• 🆔 <code>{uid}</code> | {handle}\n"
        f"   👤 {name}\n"
        f"   📅 {fmt_dt(ref.created_at)} | 💰 {reward}"
    )


async def _show_referrers(message, services: Services, page: int) -> None:
    rows, total = await services.referral.referrers_overview(
        page=page, page_size=_PAGE_SIZE
    )
    _, total_pages = paginate_meta(total, page, _PAGE_SIZE)
    if total == 0:
        await edit_or_answer(message, "هنوز هیچ کاربری کسی را دعوت نکرده است.")
        return
    await edit_or_answer(
        message,
        f"👥 <b>مدیریت دعوت‌کننده‌ها</b> ({total} دعوت‌کننده)\nیکی را انتخاب کنید:",
        reply_markup=referrers_menu(rows, page, total_pages),
    )


async def _show_detail(
    message, services: Services, referrer_id: int, page: int
) -> None:
    rows, total, rewarded_sum = await services.referral.referred_detail(
        referrer_id, page=page, page_size=_PAGE_SIZE
    )
    referrer = await services.users.get(referrer_id)
    _, total_pages = paginate_meta(total, page, _PAGE_SIZE)

    if referrer is not None:
        ref_line = format_user_display(referrer)
    else:
        ref_line = f"<code>{referrer_id}</code> | بدون یوزرنیم"

    header = (
        f"👤 <b>دعوت‌کننده:</b>\n{ref_line}\n\n"
        f"👥 <b>تعداد دعوت‌شده‌ها:</b> {total} نفر\n"
        f"💰 <b>مجموع پاداش پرداخت‌شده:</b> {format_toman(rewarded_sum)}"
    )
    body = "\n\n".join(_referred_line(r, u) for r, u in rows) or "—"
    await edit_or_answer(
        message,
        f"{header}\n\n———\n\n{body}",
        reply_markup=referred_detail_menu(referrer_id, page, total_pages),
    )


@router.callback_query(AdminCB.filter(F.action == "referrers"), IsAdmin())
async def referrers_home(callback: CallbackQuery, services: Services) -> None:
    await _show_referrers(callback.message, services, page=1)
    await callback.answer()


@router.callback_query(AdminReferrerCB.filter(F.action == "page"), IsAdmin())
async def referrers_page(
    callback: CallbackQuery, callback_data: AdminReferrerCB, services: Services
) -> None:
    await _show_referrers(callback.message, services, page=callback_data.page)
    await callback.answer()


@router.callback_query(AdminReferrerCB.filter(F.action == "view"), IsAdmin())
async def referrer_view(
    callback: CallbackQuery, callback_data: AdminReferrerCB, services: Services
) -> None:
    await _show_detail(
        callback.message, services, callback_data.referrer_id, callback_data.page
    )
    await callback.answer()


# ---- global referral-stats reset (relations preserved) ----
@router.callback_query(AdminReferrerCB.filter(F.action == "reset_all"), IsAdmin())
async def referrers_reset_all_confirm(callback: CallbackQuery) -> None:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ تایید", callback_data=AdminReferrerCB(action="reset_all_ok"))
    kb.button(text="❌ لغو", callback_data=AdminReferrerCB(action="page", page=1))
    kb.adjust(2)
    await edit_or_answer(
        callback.message,
        "⚠️ آیا از ریست آمار تمام دعوت‌کننده‌ها مطمئن هستید؟\n\n"
        "فقط شمارنده‌ها و آمارها صفر می‌شوند؛ هیچ رکوردی از روابط دعوت حذف نمی‌شود "
        "و پاداش تکراری به کسی داده نخواهد شد.",
        reply_markup=kb.as_markup(),
    )
    await callback.answer()


@router.callback_query(AdminReferrerCB.filter(F.action == "reset_all_ok"), IsAdmin())
async def referrers_reset_all_do(callback: CallbackQuery, services: Services) -> None:
    affected = await services.referral.reset_all_statistics()
    await services.commit()
    kb = InlineKeyboardBuilder()
    kb.button(text="🔙 بازگشت به پنل", callback_data=AdminCB(action="back_home"))
    await edit_or_answer(
        callback.message,
        f"✅ آمار تمام دعوت‌کننده‌ها ریست شد ({affected} مورد).\n"
        "روابط دعوت حفظ شده‌اند و پاداش تکراری داده نمی‌شود.",
        reply_markup=kb.as_markup(),
    )
    await callback.answer()
