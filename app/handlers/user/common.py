"""Common user handlers: /start, main menu, global cancel."""
from __future__ import annotations

from types import SimpleNamespace

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.container import Services
from app.core.config import settings
from app.core.logger import get_logger
from app.filters.buttons import MainBtn
from app.keyboards.callbacks import NavCB
from app.keyboards.reply import build_main_menu
from app.models.user import User
from app.services.button_service import BTN_KEY_CONTACT
from app.services.notification_service import NotificationService
from app.utils.helpers import (
    answer_managed,
    edit_or_answer,
    format_toman,
    format_user_display,
    safe_answer,
)

router = Router(name="user_common")
log = get_logger("user.common")


def _is_admin(user: User | None, tg_id: int) -> bool:
    return tg_id in settings.admin_ids or bool(user and user.is_admin)


async def _send_welcome(message: Message, services: Services, is_admin: bool) -> None:
    """Send the (admin-editable) welcome text with premium emoji preserved."""
    text, entities = await services.text.render("welcome")
    markup = await build_main_menu(services, is_admin)
    if entities:
        await safe_answer(
            message, text, reply_markup=markup, entities=entities, parse_mode=None
        )
    else:
        await safe_answer(message, text, reply_markup=markup)


async def process_pending_referral(services: Services, bot, invitee: User) -> None:
    """Pay out a referral captured at /start, once the invitee is past any gate.

    Safe to call from every post-/start entry point (deep-link start, plain
    start, or the «✅ عضو شدم» channel-join check): it no-ops unless the invitee
    has a pending referral code and no referrer yet. On a payout it commits the
    credit *before* announcing it, then DMs the referrer and notifies the admins.
    """
    result = await services.referral.process_pending(invitee)
    if not result.rewarded:
        return
    await services.commit()
    notifier = NotificationService(bot)
    # One shared formatter for both parties → «id | @username» or, with no
    # username, «id | <tappable profile name>». The invitee is a full User; the
    # referrer is rebuilt from the reward result's primitive fields.
    invitee_handle = format_user_display(invitee)
    referrer_handle = format_user_display(
        SimpleNamespace(
            telegram_id=result.referrer_telegram_id,
            username=result.referrer_username,
            full_name=result.referrer_full_name,
        )
    )
    if result.referrer_telegram_id:
        await notifier.notify_user(
            result.referrer_telegram_id,
            "🎉 یک زیرمجموعه جدید به لیست شما اضافه شد.\n"
            f"💰 {format_toman(result.amount)} به کیف پول شما اضافه شد.\n"
            "👤 کاربر:\n"
            f"{invitee_handle}",
        )
    await notifier.notify_admins(
        await services.admin.all_admin_ids(),
        "👥 زیرمجموعه جدید ثبت شد.\n"
        "دعوت‌کننده:\n"
        f"{referrer_handle}\n"
        "کاربر جدید:\n"
        f"{invitee_handle}",
    )
    await notifier.log_event(
        "زیرمجموعه جدید",
        {
            "دعوت‌کننده": referrer_handle,
            "کاربر جدید": invitee_handle,
            "پاداش": format_toman(result.amount),
        },
    )


@router.message(CommandStart(deep_link=True))
async def start_with_ref(
    message: Message,
    services: Services,
    db_user: User,
    state: FSMContext,
    bot,
) -> None:
    await state.clear()
    # The deep-link payload was captured into pending_referral_code by the DB
    # middleware (new users only); pay it out now that we're past any gate. The
    # anti-abuse guards live in ReferralService (referred only once, no self-
    # invite, never re-pays a user who already has a referrer).
    await process_pending_referral(services, bot, db_user)
    await _send_welcome(message, services, _is_admin(db_user, message.from_user.id))


@router.message(CommandStart())
async def start(
    message: Message,
    services: Services,
    db_user: User,
    state: FSMContext,
    bot,
    db_user_created: bool = False,
) -> None:
    await state.clear()
    # A user gated on their first /start <code> still carries the pending code;
    # a plain /start after they join is another chance to pay it out.
    await process_pending_referral(services, bot, db_user)
    await _send_welcome(message, services, _is_admin(db_user, message.from_user.id))
    if db_user_created:
        await NotificationService(bot).log_event(
            "کاربر جدید",
            {
                "آیدی": str(db_user.telegram_id),
                "یوزرنیم": f"@{db_user.username}" if db_user.username else "-",
                "نام": db_user.full_name or "-",
            },
        )


@router.message(MainBtn(BTN_KEY_CONTACT))
async def contact_methods(message: Message, services: Services) -> None:
    """Show the admin-editable «راه‌های ارتباطی» text (read live from the DB)."""
    rendered = await services.text.render("contact")
    await answer_managed(message, rendered)


@router.message(Command("menu"))
@router.message(F.text == "🏠 منوی اصلی")
async def show_menu(
    message: Message, services: Services, db_user: User, state: FSMContext
) -> None:
    await state.clear()
    await safe_answer(
        message,
        "🏠 منوی اصلی:",
        reply_markup=await build_main_menu(
            services, _is_admin(db_user, message.from_user.id)
        ),
    )


async def _cancel_draft_order(services: Services, state: FSMContext) -> None:
    """Cancel any draft order left behind by an aborted flow.

    Flows stash the in-progress order id under one of a few keys; whichever is
    present is cancelled (only if still PENDING) so it won't show in «my orders».
    """
    data = await state.get_data()
    for key in ("order_id", "pay_order_id", "disc_order_id"):
        order_id = data.get(key)
        if order_id:
            await services.order.cancel_if_pending(order_id)
            await services.commit()
            return


@router.message(F.text == "❌ لغو")
async def cancel_text(
    message: Message, services: Services, db_user: User, state: FSMContext
) -> None:
    await _cancel_draft_order(services, state)
    await state.clear()
    await safe_answer(
        message,
        "عملیات لغو شد. ✅",
        reply_markup=await build_main_menu(
            services, _is_admin(db_user, message.from_user.id)
        ),
    )


@router.callback_query(NavCB.filter(F.action == "cancel"))
async def cancel_cb(
    callback: CallbackQuery, services: Services, db_user: User, state: FSMContext
) -> None:
    await _cancel_draft_order(services, state)
    await state.clear()
    await edit_or_answer(callback.message, "عملیات لغو شد. ✅")
    await safe_answer(
        callback.message,
        "🏠 منوی اصلی:",
        reply_markup=await build_main_menu(
            services, _is_admin(db_user, callback.from_user.id)
        ),
    )
    await callback.answer()


@router.callback_query(NavCB.filter(F.action == "noop"))
async def noop_cb(callback: CallbackQuery) -> None:
    await callback.answer()
