"""Unified account-listing form, shared by the admin 'add account' entry and the
user 'sell account' entry.

Both paths walk the exact same FSM (``AccountFormFlow``) and create the exact same
``Account`` model. The only difference is the resulting status and who is notified:

* admin → account is published straight to the shop (``AVAILABLE``).
* user  → account is parked as ``PENDING_REVIEW`` and the admin is offered two
  actions: buy it directly, or push it into the public shop.
"""
from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.container import Services
from app.core.config import settings
from app.core.constants import AccountStatus
from app.filters.admin import IsAdmin
from app.keyboards.callbacks import AdminCB
from app.keyboards.inline import admin_sale_review, cancel_only
from app.keyboards.reply import build_main_menu
from app.filters.buttons import MainBtn
from app.services.button_service import BTN_KEY_SELL_ACCOUNT
from app.models.user import User
from app.services.notification_service import NotificationService
from app.states.user_states import AccountFormFlow
from app.utils.helpers import (
    edit_or_answer,
    format_toman,
    is_admin_user,
    parse_images,
    send_album,
    user_ref,
)
from app.utils.validators import parse_price

router = Router(name="account_form")

_SKIP = {"-", "ندارم", "خالی"}


def _opt(text: str) -> str | None:
    text = text.strip()
    return None if text in _SKIP else text


# ============================ ENTRY POINTS ============================
@router.callback_query(AdminCB.filter(F.action == "add_account"), IsAdmin())
async def admin_entry(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AccountFormFlow.title)
    await state.update_data(mode="admin")
    await edit_or_answer(
        callback.message, "➕ <b>افزودن اکانت</b>\nعنوان اکانت را وارد کنید:",
        reply_markup=cancel_only(),
    )
    await callback.answer()


@router.message(MainBtn(BTN_KEY_SELL_ACCOUNT))
async def user_entry(message: Message, state: FSMContext) -> None:
    await state.set_state(AccountFormFlow.title)
    await state.update_data(mode="user")
    await message.answer(
        "💰 <b>فروش اکانت</b>\nاطلاعات اکانت را مرحله‌به‌مرحله وارد کنید.\n\n"
        "عنوان اکانت را وارد کنید:",
        reply_markup=cancel_only(),
    )


# ============================ SHARED STEPS ============================
@router.message(AccountFormFlow.title, F.text)
async def step_title(message: Message, state: FSMContext) -> None:
    await state.update_data(title=message.text.strip()[:255])
    await state.set_state(AccountFormFlow.price)
    await message.answer("💵 قیمت (تومان):", reply_markup=cancel_only())


@router.message(AccountFormFlow.price, F.text)
async def step_price(message: Message, state: FSMContext) -> None:
    price = parse_price(message.text)
    if price is None or price <= 0:
        await message.answer("❌ قیمت نامعتبر است. یک عدد وارد کنید.")
        return
    await state.update_data(price=price)
    await state.set_state(AccountFormFlow.level)
    await message.answer("🎚 لول اکانت:", reply_markup=cancel_only())


@router.message(AccountFormFlow.level, F.text)
async def step_level(message: Message, state: FSMContext) -> None:
    await state.update_data(level=parse_price(message.text) or 0)
    await state.set_state(AccountFormFlow.elite)
    await message.answer("⭐️ تعداد الیت پس:", reply_markup=cancel_only())


@router.message(AccountFormFlow.elite, F.text)
async def step_elite(message: Message, state: FSMContext) -> None:
    await state.update_data(elite=parse_price(message.text) or 0)
    await state.set_state(AccountFormFlow.skins)
    await message.answer("🎽 تعداد اسکین:", reply_markup=cancel_only())


@router.message(AccountFormFlow.skins, F.text)
async def step_skins(message: Message, state: FSMContext) -> None:
    await state.update_data(skins=parse_price(message.text) or 0)
    await state.set_state(AccountFormFlow.gun_skins)
    await message.answer("🔫 تعداد گان اسکین:", reply_markup=cancel_only())


@router.message(AccountFormFlow.gun_skins, F.text)
async def step_gun_skins(message: Message, state: FSMContext) -> None:
    await state.update_data(gun_skins=parse_price(message.text) or 0)
    await state.set_state(AccountFormFlow.description)
    await message.answer("📝 توضیحات:", reply_markup=cancel_only())


@router.message(AccountFormFlow.description, F.text)
async def step_description(message: Message, state: FSMContext) -> None:
    await state.update_data(description=message.text.strip(), images=[])
    await state.set_state(AccountFormFlow.images)
    await message.answer(
        "📸 تصاویر اکانت را ارسال کنید (هر تعداد، حتی به‌صورت آلبوم).\n"
        "پس از اتمام دستور /done را بزنید.",
        reply_markup=cancel_only(),
    )


@router.message(AccountFormFlow.images, F.photo)
async def step_image(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    images = data.get("images", [])
    images.append(message.photo[-1].file_id)
    await state.update_data(images=images)
    # In an album each photo arrives separately; acknowledge only the first so the
    # user isn't spammed with one reply per image.
    if message.media_group_id is None or len(images) == 1:
        await message.answer(f"✅ تصویر {len(images)} ذخیره شد. برای پایان /done را بزنید.")


@router.message(AccountFormFlow.images, F.text == "/done")
async def step_images_done(message: Message, state: FSMContext) -> None:
    await state.set_state(AccountFormFlow.save_info)
    await message.answer(
        "💾 اطلاعات سیو اکانت را وارد کنید (رمزنگاری‌شده ذخیره می‌شود).\n"
        "اگر ندارید «-» بفرستید.",
        reply_markup=cancel_only(),
    )


@router.message(AccountFormFlow.save_info, F.text)
async def step_save_info(message: Message, state: FSMContext) -> None:
    await state.update_data(save_info=_opt(message.text))
    await state.set_state(AccountFormFlow.login_info)
    await message.answer(
        "🔐 اطلاعات ورود اکانت را وارد کنید (ایمیل/رمز/روش ورود).\n"
        "رمزنگاری‌شده ذخیره و فقط پس از فروش تحویل می‌شود. اگر ندارید «-» بفرستید.",
        reply_markup=cancel_only(),
    )


@router.message(AccountFormFlow.login_info, F.text)
async def step_login_info(message: Message, state: FSMContext) -> None:
    await state.update_data(login_info=_opt(message.text))
    await state.set_state(AccountFormFlow.special_items)
    await message.answer(
        "✨ آیتم‌های خاص اکانت را بنویسید (اگر ندارید «-» بفرستید):",
        reply_markup=cancel_only(),
    )


@router.message(AccountFormFlow.special_items, F.text)
async def step_special_items(
    message: Message, services: Services, state: FSMContext, db_user: User, bot
) -> None:
    data = await state.get_data()
    data["special_items"] = _opt(message.text)
    is_admin = data.get("mode") == "admin"

    account = await services.account.create_listing(
        title=data["title"],
        price=data["price"],
        level=data["level"],
        elite_count=data["elite"],
        skins_count=data["skins"],
        gun_skins_count=data["gun_skins"],
        description=data["description"],
        images=",".join(data.get("images", [])),
        special_items=data["special_items"],
        credentials=data.get("login_info"),
        save_info=data.get("save_info"),
        status=AccountStatus.AVAILABLE if is_admin else AccountStatus.PENDING_REVIEW,
        seller_user_id=None if is_admin else db_user.id,
    )
    await services.commit()
    await state.clear()

    if is_admin:
        await message.answer(f"✅ اکانت #{account.id} ثبت و در فروشگاه منتشر شد.")
        return

    await message.answer(
        f"✅ اکانت شما با شماره #{account.id} ثبت شد و برای بررسی به پشتیبانی ارسال شد.",
        reply_markup=await build_main_menu(services, is_admin_user(message, db_user)),
    )
    await _notify_admin_new_listing(bot, account, db_user)


async def _notify_admin_new_listing(bot, account, seller: User) -> None:
    notifier = NotificationService(bot)
    caption = (
        f"💰 <b>اکانت جدید برای فروش</b> #{account.id}\n"
        f"فروشنده: {user_ref(seller)}\n"
        f"عنوان: {account.title}\n"
        f"قیمت پیشنهادی: {format_toman(account.price)}\n"
        f"لول: {account.level} | الیت: {account.elite_count} | "
        f"اسکین: {account.skins_count} | گان: {account.gun_skins_count}\n"
        f"آیتم خاص: {account.special_items or '-'}\n"
        f"توضیحات: {account.description or '-'}"
    )
    images = parse_images(account.images)
    try:
        await send_album(bot, settings.admin_id, images, caption=caption)
        await bot.send_message(
            settings.admin_id,
            f"یک تصمیم برای اکانت #{account.id} بگیرید:",
            reply_markup=admin_sale_review(account.id),
        )
    except Exception:  # noqa: BLE001 - admin notification must not break user flow
        await notifier.notify_admin(caption, reply_markup=admin_sale_review(account.id))
    await notifier.log_event(
        "فروش اکانت",
        {"اکانت": f"#{account.id}", "فروشنده": user_ref(seller)},
    )
