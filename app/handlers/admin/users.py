"""Admin: 👤 مدیریت کاربران — search a user, view a full info card, and act on them.

This screen is *search-first*: an admin sends a numeric Telegram id or a @username
and gets a complete profile card (wallet, paid total, referrals, orders, ban state,
referrer, join date) with inline actions — adjust balance, send a message, ban /
unban, and reset the user's referral statistics.

The original ban-management system is preserved verbatim: the banned-user list,
the «🚫 بن کردن کاربر» flow (``UserBanFlow``) and one-tap unban all still work and
are reachable via «📋 لیست کاربران مسدود». The card's ban / unban buttons reuse the
same :class:`BanService`, so there is a single source of truth for bans.
"""
from __future__ import annotations

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.container import Services
from app.core.constants import TransactionType
from app.filters.admin import IsAdmin
from app.keyboards.callbacks import AdminCB, UserAdminCB
from app.keyboards.inline import cancel_only
from app.services.ban_service import BanEntry, BanError
from app.services.notification_service import NotificationService
from app.services.wallet_service import InsufficientBalanceError
from app.states.admin_states import UserBanFlow, UserManageFlow
from app.utils.helpers import (
    edit_or_answer,
    fmt_dt,
    format_toman,
    format_user_display,
    paginate_meta,
    user_profile_link,
)
from app.utils.validators import parse_price

router = Router(name="admin_users")

_PAGE_SIZE = 10


# ============================ banned-user list (kept) ============================
def _ban_line(entry: BanEntry) -> str:
    handle = f"@{entry.username}" if entry.username else "بدون یوزرنیم"
    name = user_profile_link(entry.user_id, entry.full_name) or "—"
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
    header = f"🚫 <b>کاربران مسدود</b>\nتعداد: <b>{total}</b>"
    body = "\n\n".join(_ban_line(e) for e in entries) or "هیچ کاربر مسدودی وجود ندارد."
    await edit_or_answer(
        message,
        f"{header}\n\n———\n\n{body}",
        reply_markup=_list_markup(entries, page, total_pages),
    )


# ================================ search + card ================================
def _search_menu() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📋 لیست کاربران مسدود", callback_data=UserAdminCB(action="banlist", page=1))
    kb.button(text="🔙 بازگشت", callback_data=AdminCB(action="back_home"))
    kb.adjust(1)
    return kb.as_markup()


def _card_menu(tg_id: int, is_banned: bool) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ افزایش موجودی", callback_data=UserAdminCB(action="bal_add", user_id=tg_id))
    kb.button(text="➖ کاهش موجودی", callback_data=UserAdminCB(action="bal_sub", user_id=tg_id))
    kb.button(text="💬 ارسال پیام", callback_data=UserAdminCB(action="msg", user_id=tg_id))
    if is_banned:
        kb.button(text="✅ رفع بن کاربر", callback_data=UserAdminCB(action="card_unban", user_id=tg_id))
    else:
        kb.button(text="🚫 بن کاربر", callback_data=UserAdminCB(action="card_ban", user_id=tg_id))
    kb.button(text="🔄 ریست زیرمجموعه‌گیری", callback_data=UserAdminCB(action="reset_refs", user_id=tg_id))
    kb.button(text="🔙 بازگشت", callback_data=AdminCB(action="back_home"))
    kb.adjust(2, 1, 1, 1, 1)
    return kb.as_markup()


async def _show_user_card(
    message, services: Services, tg_id: int, *, as_new: bool = False
) -> bool:
    """Render the full info card for the user with this *telegram* id.

    ``as_new`` sends a fresh message (when responding to the admin's typed input);
    otherwise the current card message is edited in place (callback navigation).
    Returns ``False`` (showing a not-found notice) when no such user exists.
    """
    user = await services.users.get_by_telegram_id(tg_id)
    if user is None:
        notice = "❌ کاربری با این مشخصات یافت نشد."
        if as_new:
            await message.answer(notice, reply_markup=_search_menu())
        else:
            await edit_or_answer(message, notice, reply_markup=_search_menu())
        return False

    # Read the wallet directly so merely viewing a profile never creates a row.
    wallet = await services.wallets_repo.get_by_user_id(user.id)
    balance = wallet.balance if wallet else 0
    total_paid = await services.orders.total_paid_by_user(user.id)
    placed = await services.orders.count_placed_by_user(user.id)
    completed = await services.orders.count_completed_by_user(user.id)
    ref_stats = await services.referral.stats(user)

    if user.referred_by_id:
        # ``referred_by_id`` holds the referrer's *internal* id.
        referrer = await services.users.get(user.referred_by_id)
        referrer_line = (
            format_user_display(referrer)
            if referrer is not None
            else f"<code>{user.referred_by_id}</code>"
        )
    else:
        referrer_line = "❌ ندارد"

    handle = f"@{user.username}" if user.username else "بدون یوزرنیم"
    name_line = user_profile_link(user.telegram_id, user.full_name) or "—"
    status_line = "🚫 مسدود" if user.is_banned else "✅ فعال"

    text = (
        "👤 <b>اطلاعات کاربر</b>\n\n"
        f"🆔 آیدی عددی: <code>{user.telegram_id}</code>\n"
        f"👤 یوزرنیم: {handle}\n"
        f"🏷 نام: {name_line}\n"
        f"💰 موجودی کیف پول: {format_toman(balance)}\n"
        f"💳 مجموع پرداختی: {format_toman(total_paid)}\n"
        f"👥 تعداد زیرمجموعه: {ref_stats['invited']}\n"
        f"🎁 مجموع پاداش دعوت: {format_toman(ref_stats['earned'])}\n"
        f"📨 سفارش‌های ثبت‌شده: {placed}\n"
        f"📦 سفارش‌های تکمیل‌شده: {completed}\n"
        f"🚫 وضعیت: {status_line}\n"
        f"👤 دعوت‌کننده: {referrer_line}\n"
        f"📅 تاریخ عضویت: {fmt_dt(user.created_at)}"
    )
    markup = _card_menu(user.telegram_id, user.is_banned)
    if as_new:
        await message.answer(text, reply_markup=markup)
    else:
        await edit_or_answer(message, text, reply_markup=markup)
    return True


# --------------------------------- home ---------------------------------
@router.callback_query(AdminCB.filter(F.action == "users"), IsAdmin())
async def users_home(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(UserManageFlow.searching)
    await edit_or_answer(
        callback.message,
        "👤 <b>مدیریت کاربران</b>\n\n🔎 آیدی عددی یا یوزرنیم کاربر را ارسال کنید.",
        reply_markup=_search_menu(),
    )
    await callback.answer()


@router.message(UserManageFlow.searching, F.text, IsAdmin())
async def user_search(message: Message, services: Services) -> None:
    raw = message.text.strip()
    user = None
    # ``parse_price`` returns an int for a numeric id (also tolerant of Persian
    # digits / separators) and ``None`` for a @username, so it cleanly splits the
    # two lookup paths.
    numeric = parse_price(raw)
    if numeric is not None:
        user = await services.users.get_by_telegram_id(numeric)
    if user is None:
        user = await services.users.get_by_username(raw)
    if user is None:
        await message.answer(
            "❌ کاربری با این مشخصات یافت نشد.\n"
            "آیدی عددی یا یوزرنیم را دوباره ارسال کنید یا «🔙 بازگشت» را بزنید.",
            reply_markup=_search_menu(),
        )
        return
    await _show_user_card(message, services, user.telegram_id, as_new=True)


@router.callback_query(UserAdminCB.filter(F.action == "card"), IsAdmin())
async def user_card_reshow(
    callback: CallbackQuery, callback_data: UserAdminCB, services: Services
) -> None:
    await _show_user_card(callback.message, services, callback_data.user_id)
    await callback.answer()


@router.callback_query(UserAdminCB.filter(F.action == "banlist"), IsAdmin())
async def users_banlist(
    callback: CallbackQuery, callback_data: UserAdminCB, services: Services
) -> None:
    await _show_list(callback.message, services, page=callback_data.page or 1)
    await callback.answer()


# ----------------------------- card: balance -----------------------------
@router.callback_query(UserAdminCB.filter(F.action == "bal_add"), IsAdmin())
async def card_balance_add(
    callback: CallbackQuery, callback_data: UserAdminCB, state: FSMContext
) -> None:
    await state.update_data(target_tg_id=callback_data.user_id, direction="add")
    await state.set_state(UserManageFlow.entering_balance)
    await edit_or_answer(
        callback.message,
        "➕ مبلغ افزایش موجودی را وارد کنید (تومان):",
        reply_markup=cancel_only(),
    )
    await callback.answer()


@router.callback_query(UserAdminCB.filter(F.action == "bal_sub"), IsAdmin())
async def card_balance_sub(
    callback: CallbackQuery, callback_data: UserAdminCB, state: FSMContext
) -> None:
    await state.update_data(target_tg_id=callback_data.user_id, direction="sub")
    await state.set_state(UserManageFlow.entering_balance)
    await edit_or_answer(
        callback.message,
        "➖ مبلغ کاهش موجودی را وارد کنید (تومان):",
        reply_markup=cancel_only(),
    )
    await callback.answer()


@router.message(UserManageFlow.entering_balance, F.text, IsAdmin())
async def card_balance_amount(
    message: Message, services: Services, state: FSMContext, bot
) -> None:
    data = await state.get_data()
    tg_id = int(data.get("target_tg_id") or 0)
    direction = data.get("direction") or "add"
    amount = parse_price(message.text)
    if amount is None or amount <= 0:
        await message.answer("مبلغ نامعتبر است. یک عدد مثبت وارد کنید.")
        return
    user = await services.users.get_by_telegram_id(tg_id)
    if user is None:
        await message.answer("کاربر یافت نشد.")
        await state.set_state(UserManageFlow.searching)
        return
    if direction == "add":
        await services.wallet.credit(
            user.id, amount, TransactionType.DEPOSIT, "افزایش موجودی توسط ادمین"
        )
        verb = "افزایش"
    else:
        try:
            await services.wallet.debit(
                user.id, amount, TransactionType.WITHDRAW, "کاهش موجودی توسط ادمین"
            )
        except InsufficientBalanceError:
            await message.answer("❌ موجودی کاربر کافی نیست؛ مبلغ کاهش از موجودی بیشتر است.")
            return
        verb = "کاهش"
    await services.commit()
    await NotificationService(bot).notify_user(
        tg_id,
        f"👛 موجودی کیف پول شما توسط پشتیبانی به میزان {format_toman(amount)} {verb} یافت.",
    )
    await message.answer(
        f"✅ موجودی کاربر <code>{tg_id}</code> به میزان {format_toman(amount)} {verb} یافت."
    )
    await state.set_state(UserManageFlow.searching)
    await _show_user_card(message, services, tg_id, as_new=True)


# ----------------------------- card: message -----------------------------
@router.callback_query(UserAdminCB.filter(F.action == "msg"), IsAdmin())
async def card_message_start(
    callback: CallbackQuery, callback_data: UserAdminCB, state: FSMContext
) -> None:
    await state.update_data(target_tg_id=callback_data.user_id)
    await state.set_state(UserManageFlow.entering_message)
    await edit_or_answer(
        callback.message,
        "💬 متن پیامی که برای کاربر ارسال شود را وارد کنید:",
        reply_markup=cancel_only(),
    )
    await callback.answer()


@router.message(UserManageFlow.entering_message, F.text, IsAdmin())
async def card_message_send(
    message: Message, services: Services, state: FSMContext, bot
) -> None:
    data = await state.get_data()
    tg_id = int(data.get("target_tg_id") or 0)
    body = message.html_text
    try:
        await bot.send_message(tg_id, f"📩 <b>پیام از پشتیبانی:</b>\n\n{body}")
        ok = True
    except TelegramAPIError:
        ok = False
    if ok:
        await message.answer("✅ پیام برای کاربر ارسال شد.")
    else:
        await message.answer("❌ ارسال پیام ناموفق بود (کاربر ربات را بلاک کرده یا در دسترس نیست).")
    await state.set_state(UserManageFlow.searching)
    await _show_user_card(message, services, tg_id, as_new=True)


# --------------------------- card: ban / unban ---------------------------
@router.callback_query(UserAdminCB.filter(F.action == "card_ban"), IsAdmin())
async def card_ban_start(
    callback: CallbackQuery, callback_data: UserAdminCB, state: FSMContext
) -> None:
    await state.update_data(target_tg_id=callback_data.user_id)
    await state.set_state(UserManageFlow.entering_ban_reason)
    await edit_or_answer(
        callback.message,
        "📝 دلیل بن را وارد کنید:\nمثال: اسپم، سوءاستفاده از سیستم، پرداخت نامعتبر، تخلف",
        reply_markup=cancel_only(),
    )
    await callback.answer()


@router.message(UserManageFlow.entering_ban_reason, F.text, IsAdmin())
async def card_ban_reason(
    message: Message, services: Services, state: FSMContext, bot
) -> None:
    data = await state.get_data()
    tg_id = int(data.get("target_tg_id") or 0)
    reason = message.text.strip()
    try:
        await services.ban.ban_user(tg_id, reason=reason, banned_by=message.from_user.id)
    except BanError as exc:
        await message.answer(f"❌ {exc}")
        await state.set_state(UserManageFlow.searching)
        await _show_user_card(message, services, tg_id, as_new=True)
        return
    await services.commit()
    await NotificationService(bot).notify_user(
        tg_id,
        "🚫 حساب شما توسط مدیریت مسدود شده است.\n\n"
        "در صورت نیاز با مدیریت مجموعه تماس بگیرید.",
    )
    await NotificationService(bot).log_event(
        "مسدودسازی کاربر",
        {"کاربر": f"<code>{tg_id}</code>", "دلیل": reason, "توسط": f"<code>{message.from_user.id}</code>"},
    )
    await message.answer(f"✅ کاربر <code>{tg_id}</code> مسدود شد.\n📝 دلیل: {reason}")
    await state.set_state(UserManageFlow.searching)
    await _show_user_card(message, services, tg_id, as_new=True)


@router.callback_query(UserAdminCB.filter(F.action == "card_unban"), IsAdmin())
async def card_unban(
    callback: CallbackQuery, callback_data: UserAdminCB, services: Services, bot
) -> None:
    tg_id = callback_data.user_id
    try:
        await services.ban.unban_user(tg_id)
    except BanError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    await services.commit()
    await callback.answer("کاربر رفع بن شد.")
    await NotificationService(bot).notify_user(
        tg_id, "✅ مسدودیت حساب شما برداشته شد. اکنون می‌توانید از ربات استفاده کنید."
    )
    await _show_user_card(callback.message, services, tg_id)


# ----------------------- card: reset referral stats ----------------------
@router.callback_query(UserAdminCB.filter(F.action == "reset_refs"), IsAdmin())
async def card_reset_refs_confirm(
    callback: CallbackQuery, callback_data: UserAdminCB
) -> None:
    kb = InlineKeyboardBuilder()
    kb.button(
        text="✅ تایید",
        callback_data=UserAdminCB(action="reset_refs_ok", user_id=callback_data.user_id),
    )
    kb.button(
        text="🔙 انصراف",
        callback_data=UserAdminCB(action="card", user_id=callback_data.user_id),
    )
    kb.adjust(2)
    await edit_or_answer(
        callback.message,
        "⚠️ آیا از ریست آمار زیرمجموعه‌گیری این کاربر مطمئن هستید؟\n\n"
        "فقط شمارنده‌ها و آمار صفر می‌شوند؛ روابط دعوت حفظ می‌شوند و پاداش تکراری "
        "داده نخواهد شد.",
        reply_markup=kb.as_markup(),
    )
    await callback.answer()


@router.callback_query(UserAdminCB.filter(F.action == "reset_refs_ok"), IsAdmin())
async def card_reset_refs_do(
    callback: CallbackQuery, callback_data: UserAdminCB, services: Services
) -> None:
    tg_id = callback_data.user_id
    user = await services.users.get_by_telegram_id(tg_id)
    if user is None:
        await callback.answer("کاربر یافت نشد.", show_alert=True)
        return
    affected = await services.referral.reset_user_statistics(user)
    await services.commit()
    await callback.answer(f"آمار زیرمجموعه‌گیری ریست شد ({affected} مورد).", show_alert=True)
    await _show_user_card(callback.message, services, tg_id)


# ============================ ban flow (kept) ============================
@router.callback_query(UserAdminCB.filter(F.action == "page"), IsAdmin())
async def users_page(
    callback: CallbackQuery, callback_data: UserAdminCB, services: Services
) -> None:
    await _show_list(callback.message, services, page=callback_data.page)
    await callback.answer()


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
        "مثال: اسپم، سوءاستفاده از سیستم، پرداخت نامعتبر, تخلف",
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
