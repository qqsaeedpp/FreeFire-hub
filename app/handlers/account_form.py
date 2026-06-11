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
from app.core.constants import AccountStatus
from app.filters.admin import IsAdmin
from app.keyboards.callbacks import AdminCB
from app.keyboards.inline import admin_sale_review, cancel_only
from app.keyboards.reply import build_main_menu
from app.filters.buttons import MainBtn
from app.services.account_service import is_account_visible_for_users
from app.services.button_service import BTN_KEY_SELL_ACCOUNT
from app.models.user import User
from app.services.notification_service import NotificationService
from app.states.user_states import AccountFormFlow
from app.utils.helpers import (
    edit_or_answer,
    is_admin_user,
    parse_images,
    safe_answer,
    sale_request_caption,
    send_listing_card,
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
    await state.set_state(AccountFormFlow.description)
    await message.answer(
        "📝 <b>توضیحات اکانت</b>\n"
        "تمام مشخصات اکانت (لول، تعداد الیت، اسکین‌ها، گان‌ها، آیتم‌های خاص و …) "
        "را در همین یک پیام بنویسید:",
        reply_markup=cancel_only(),
    )


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
async def step_images_done(
    message: Message, services: Services, state: FSMContext, db_user: User, bot
) -> None:
    data = await state.get_data()
    # Only the admin path collects the (encrypted) save/login credentials the shop
    # will deliver after a sale. A user selling their own account is never asked
    # for a password or login info here — that's arranged with the admin outside
    # this flow after agreement — so the user listing is finalized right away.
    if data.get("mode") == "admin":
        await state.set_state(AccountFormFlow.save_info)
        await message.answer(
            "💾 اطلاعات سیو اکانت را وارد کنید (رمزنگاری‌شده ذخیره می‌شود).\n"
            "اگر ندارید «-» بفرستید.",
            reply_markup=cancel_only(),
        )
        return
    await _finalize_listing(message, services, state, db_user, bot)


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
async def step_login_info(
    message: Message, services: Services, state: FSMContext, db_user: User, bot
) -> None:
    await state.update_data(login_info=_opt(message.text))
    await _finalize_listing(message, services, state, db_user, bot)


async def _finalize_listing(
    message: Message, services: Services, state: FSMContext, db_user: User, bot
) -> None:
    """Create the ``Account`` row and notify/ack, shared by both finish points.

    Admin finishes after the credential steps (``credentials``/``save_info`` set);
    the user finishes right after the images step (both stay ``None``). The status
    differs — admin listings go live (``AVAILABLE``), user listings wait for review
    (``PENDING_REVIEW``).
    """
    data = await state.get_data()
    is_admin = data.get("mode") == "admin"

    account = await services.account.create_listing(
        title=data["title"],
        price=data["price"],
        description=data["description"],
        images=",".join(data.get("images", [])),
        credentials=data.get("login_info"),
        save_info=data.get("save_info"),
        status=AccountStatus.AVAILABLE if is_admin else AccountStatus.PENDING_REVIEW,
        seller_user_id=None if is_admin else db_user.id,
    )
    await services.commit()
    await state.clear()

    if is_admin:
        # Confirm exactly whether the new listing is buyer-visible, using the same
        # predicate the shop query honors — so the admin is never left guessing why
        # an account did or didn't reach the buy-account list.
        if is_account_visible_for_users(account):
            await message.answer(
                f"✅ اکانت #{account.id} با موفقیت ثبت شد و در لیست خرید کاربران قابل مشاهده است."
            )
        else:
            await message.answer(
                f"⚠️ اکانت #{account.id} ثبت شد اما به دلیل نداشتن قیمت معتبر "
                "در لیست کاربران نمایش داده نمی‌شود."
            )
        return

    await safe_answer(
        message,
        f"✅ اکانت شما با شماره #{account.id} ثبت شد و برای بررسی به پشتیبانی ارسال شد.",
        reply_markup=await build_main_menu(services, is_admin_user(message, db_user)),
    )
    await _notify_admin_new_listing(bot, services, account, db_user)


async def _notify_admin_new_listing(bot, services: Services, account, seller: User) -> None:
    """Broadcast the new listing to every authorized admin (instant notification).

    Mirrors the diamond-order notification: each admin gets the «🔔 درخواست جدید
    فروش اکانت» card with images (album when multiple) plus the shared decision
    buttons. The buttons reuse :func:`admin_sale_review` so acting here is
    identical to acting from the «📦 سفارشات فروش اکانت کاربران» list. One admin
    failing (e.g. blocked the bot) must never break the others or the user flow.
    """
    notifier = NotificationService(bot)
    caption = sale_request_caption(account, seller)
    images = parse_images(account.images)
    keyboard = admin_sale_review(account.id)
    admin_ids = await services.admin.all_admin_ids()
    for admin_id in admin_ids:
        try:
            await send_listing_card(
                bot, admin_id, caption=caption, images=images, keyboard=keyboard
            )
        except Exception:  # noqa: BLE001 - one admin's failure must not affect others
            continue
    await notifier.log_event(
        "فروش اکانت",
        {"اکانت": f"#{account.id}", "فروشنده": user_ref(seller)},
    )
