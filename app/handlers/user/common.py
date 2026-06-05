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
from app.keyboards.reply import main_menu
from app.models.user import User
from app.services.notification_service import NotificationService
from app.utils.helpers import edit_or_answer, format_toman

router = Router(name="user_common")
log = get_logger("user.common")

WELCOME = (
    "🎮 <b>به فروشگاه FreeFire Hub خوش آمدید!</b>\n\n"
    "از منوی زیر می‌توانید جم بخرید، اکانت بخرید یا بفروشید، "
    "کیف پول خود را مدیریت کنید و زیرمجموعه بگیرید.\n\n"
    "برای شروع یکی از گزینه‌ها را انتخاب کنید 👇"
)


def _is_admin(user: User | None, tg_id: int) -> bool:
    return tg_id in settings.admin_ids or bool(user and user.is_admin)


@router.message(CommandStart(deep_link=True))
async def start_with_ref(
    message: Message,
    command: CommandObject,
    services: Services,
    db_user: User,
    state: FSMContext,
    bot,
) -> None:
    await state.clear()
    ref = (command.args or "").strip()
    # Link referral only if this user has no referrer yet and isn't self-referring.
    if ref and db_user.referred_by_id is None and ref != db_user.referral_code:
        await services.user._link_referral(db_user, ref)
        await services.commit()
        await NotificationService(bot).log_event(
            "زیرمجموعه جدید",
            {"کاربر": str(db_user.telegram_id), "کد معرف": ref},
        )
    await message.answer(
        WELCOME, reply_markup=main_menu(_is_admin(db_user, message.from_user.id))
    )


@router.message(CommandStart())
async def start(
    message: Message,
    db_user: User,
    state: FSMContext,
    bot,
    db_user_created: bool = False,
) -> None:
    await state.clear()
    await message.answer(
        WELCOME, reply_markup=main_menu(_is_admin(db_user, message.from_user.id))
    )
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
async def show_menu(message: Message, db_user: User, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "🏠 منوی اصلی:",
        reply_markup=main_menu(_is_admin(db_user, message.from_user.id)),
    )


@router.message(F.text == "❌ لغو")
async def cancel_text(message: Message, db_user: User, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "عملیات لغو شد. ✅",
        reply_markup=main_menu(_is_admin(db_user, message.from_user.id)),
    )


@router.callback_query(NavCB.filter(F.action == "cancel"))
async def cancel_cb(
    callback: CallbackQuery, db_user: User, state: FSMContext
) -> None:
    await state.clear()
    await edit_or_answer(callback.message, "عملیات لغو شد. ✅")
    await callback.message.answer(
        "🏠 منوی اصلی:",
        reply_markup=main_menu(_is_admin(db_user, callback.from_user.id)),
    )
    await callback.answer()


@router.callback_query(NavCB.filter(F.action == "noop"))
async def noop_cb(callback: CallbackQuery) -> None:
    await callback.answer()
