"""Common user handlers: /start, main menu, global cancel."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.container import Services
from app.core.config import settings
from app.core.logger import get_logger
from app.keyboards.callbacks import NavCB
from app.keyboards.reply import build_main_menu
from app.models.user import User
from app.services.notification_service import NotificationService
from app.utils.helpers import edit_or_answer, format_toman, user_ref

router = Router(name="user_common")
log = get_logger("user.common")


def _is_admin(user: User | None, tg_id: int) -> bool:
    return tg_id in settings.admin_ids or bool(user and user.is_admin)


async def _send_welcome(message: Message, services: Services, is_admin: bool) -> None:
    """Send the (admin-editable) welcome text with premium emoji preserved."""
    text, entities = await services.text.render("welcome")
    markup = await build_main_menu(services, is_admin)
    if entities:
        await message.answer(
            text, entities=entities, parse_mode=None, reply_markup=markup
        )
    else:
        await message.answer(text, reply_markup=markup)


@router.message(CommandStart(deep_link=True))
async def start_with_ref(
    message: Message,
    command: CommandObject,
    services: Services,
    db_user: User,
    state: FSMContext,
    bot,
    db_user_created: bool = False,
) -> None:
    await state.clear()
    ref = (command.args or "").strip()
    # Reward a referral only for a genuinely NEW user opening the link, and only
    # when they have no referrer yet and aren't self-referring. A repeat /start
    # (db_user_created is False) can never re-trigger a payout.
    if (
        db_user_created
        and ref
        and db_user.referred_by_id is None
        and ref != db_user.referral_code
    ):
        result = await services.referral.link_and_reward(db_user, ref)
        await services.commit()
        if result.rewarded:
            notifier = NotificationService(bot)
            if result.referrer_telegram_id:
                await notifier.notify_user(
                    result.referrer_telegram_id,
                    f"🎁 یک زیرمجموعه جدید از طریق لینک شما عضو شد!\n"
                    f"مبلغ {format_toman(result.amount)} به کیف پول شما اضافه شد.",
                )
            await notifier.log_event(
                "زیرمجموعه جدید",
                {"کاربر": user_ref(db_user), "کد معرف": ref,
                 "پاداش": format_toman(result.amount)},
            )
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


@router.message(Command("menu"))
@router.message(F.text == "🏠 منوی اصلی")
async def show_menu(
    message: Message, services: Services, db_user: User, state: FSMContext
) -> None:
    await state.clear()
    await message.answer(
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
    await message.answer(
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
    await callback.message.answer(
        "🏠 منوی اصلی:",
        reply_markup=await build_main_menu(
            services, _is_admin(db_user, callback.from_user.id)
        ),
    )
    await callback.answer()


@router.callback_query(NavCB.filter(F.action == "noop"))
async def noop_cb(callback: CallbackQuery) -> None:
    await callback.answer()
