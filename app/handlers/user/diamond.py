"""Diamond purchase flows — by UID and by account credentials."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.container import Services
from app.core.config import settings
from app.core.constants import LOGIN_METHOD_FA, PAYMENT_METHOD_FA, LoginMethod
from app.keyboards.callbacks import DiamondCB, NavCB, TutorialCB
from app.keyboards.inline import (
    backup_code_menu,
    cancel_only,
    diamond_category_menu,
    diamond_levelup_menu,
    diamond_method_menu,
    diamond_plan_menu,
    diamond_save_type_menu,
)
from app.services.diamond_service import (
    CAT_ACCOUNT,
    CAT_DIAMOND,
    CAT_LEVELUP,
    DiamondPlan,
)
from app.services.tutorial_service import GOOGLE_BACKUP_CODE_VIDEO
from app.keyboards.reply import build_main_menu
from app.filters.buttons import MainBtn
from app.services.button_service import BTN_KEY_BUY_DIAMOND
from app.models.user import User
from app.handlers.user.discount import prompt_discount
from app.services.notification_service import NotificationService
from app.states.user_states import DiamondAccountFlow, DiamondFlow, DiamondUIDFlow
from app.utils.helpers import format_toman, is_admin_user, safe_answer, user_ref
from app.utils.validators import is_valid_email, is_valid_uid

router = Router(name="user_diamond")


@router.message(MainBtn(BTN_KEY_BUY_DIAMOND))
async def entry(message: Message, services: Services, state: FSMContext) -> None:
    # Original flow restored: first pick the purchase method (UID vs account).
    await state.set_state(DiamondFlow.choosing_method)
    text, entities = await services.text.render("diamond_guide")
    if entities:
        await message.answer(
            text, entities=entities, parse_mode=None,
            reply_markup=diamond_method_menu(),
        )
    else:
        await message.answer(text, reply_markup=diamond_method_menu())


# Category emoji used in the plan list per category.
_CAT_EMOJI = {CAT_DIAMOND: "💎", CAT_LEVELUP: "💫", CAT_ACCOUNT: "💸"}


# Per-category row layout (buttons-per-row). Account uses an exact arrangement:
# [weekly][monthly] / [weekly lite] / [offer1$][offer2$] / [520][2180] / [1060][5600].
_CAT_SIZES = {
    CAT_DIAMOND: (2,),
    CAT_ACCOUNT: (2, 1, 2, 2, 2),
}


async def _show_plans(callback: CallbackQuery, services: Services, category: str) -> None:
    plans = await services.diamond.list_plans_by_category(category)
    back_target = "diamond_category" if category in (CAT_DIAMOND, CAT_LEVELUP) else "diamond_method"
    titles = {
        CAT_DIAMOND: "💎 <b>خرید جم</b>\nمقدار جم موردنظر را انتخاب کنید:",
        CAT_ACCOUNT: "💸 <b>خرید با اطلاعات اکانت</b>\nبسته موردنظر را انتخاب کنید:",
    }
    await callback.message.edit_text(
        titles[category],
        reply_markup=diamond_plan_menu(
            plans,
            back_target=back_target,
            emoji=_CAT_EMOJI.get(category, "💎"),
            sizes=_CAT_SIZES.get(category),
            short_price=category == CAT_ACCOUNT,
        ),
    )


async def _show_levelup(callback: CallbackQuery, services: Services, state: FSMContext) -> None:
    """Render the Level-Up multi-select menu reflecting the current selection."""
    data = await state.get_data()
    selected = set(data.get("levelup_selected", []))
    plans = await services.diamond.list_plans_by_category(CAT_LEVELUP)
    all_price = await services.diamond.get_levelup_all_price()
    await callback.message.edit_text(
        "💫 <b>لول اپ</b>\n"
        "می‌توانید چند آفر را همزمان انتخاب کنید و سپس «خرید انتخاب‌شده‌ها» را بزنید،\n"
        "یا با «خرید همه» تمام آفرها را یکجا خریداری کنید:",
        reply_markup=diamond_levelup_menu(
            plans, selected, all_price=all_price, back_target="diamond_category"
        ),
    )


@router.callback_query(DiamondFlow.choosing_method, DiamondCB.filter(F.action == "method"))
async def method_chosen(
    callback: CallbackQuery, callback_data: DiamondCB, services: Services, state: FSMContext
) -> None:
    if callback_data.value == "uid":
        await state.update_data(method="uid")
        await state.set_state(DiamondFlow.choosing_category)
        await callback.message.edit_text(
            "🆔 <b>خرید با UID</b>\nنوع خرید را انتخاب کنید:",
            reply_markup=diamond_category_menu(),
        )
    else:
        await state.update_data(method="account", category=CAT_ACCOUNT)
        await state.set_state(DiamondFlow.choosing_plan)
        await _show_plans(callback, services, CAT_ACCOUNT)
    await callback.answer()


@router.callback_query(DiamondFlow.choosing_category, DiamondCB.filter(F.action == "category"))
async def category_chosen(
    callback: CallbackQuery, callback_data: DiamondCB, services: Services, state: FSMContext
) -> None:
    if callback_data.value == "levelup":
        await state.update_data(
            method="uid", category=CAT_LEVELUP, levelup_selected=[],
            levelup_mode=None,
        )
        await state.set_state(DiamondFlow.choosing_plan)
        await _show_levelup(callback, services, state)
    else:
        await state.update_data(method="uid", category=CAT_DIAMOND)
        await state.set_state(DiamondFlow.choosing_plan)
        await _show_plans(callback, services, CAT_DIAMOND)
    await callback.answer()


# ----------------------- Level-Up multi-select -----------------------
@router.callback_query(DiamondFlow.choosing_plan, DiamondCB.filter(F.action == "lvl_toggle"))
async def levelup_toggle(
    callback: CallbackQuery, callback_data: DiamondCB, services: Services, state: FSMContext
) -> None:
    data = await state.get_data()
    selected = set(data.get("levelup_selected", []))
    code = callback_data.value
    if code in selected:
        selected.discard(code)
    else:
        selected.add(code)
    await state.update_data(levelup_selected=list(selected))
    await _show_levelup(callback, services, state)
    await callback.answer()


@router.callback_query(DiamondFlow.choosing_plan, DiamondCB.filter(F.action == "lvl_done"))
async def levelup_done(
    callback: CallbackQuery, services: Services, state: FSMContext
) -> None:
    data = await state.get_data()
    selected = set(data.get("levelup_selected", []))
    if not selected:
        await callback.answer("هیچ آفری انتخاب نشده است.", show_alert=True)
        return
    plans = [
        p for p in await services.diamond.list_plans_by_category(CAT_LEVELUP)
        if p.code in selected
    ]
    total = sum(p.price for p in plans)
    names = "، ".join(p.name for p in plans)
    await state.update_data(
        levelup_mode="selected", levelup_name=names[:200], levelup_price=total
    )
    await state.set_state(DiamondUIDFlow.entering_uid)
    await callback.message.edit_text(
        f"پلن: {names} — {format_toman(total)}\n\n"
        f"🆔 لطفاً <b>UID</b> اکانت خود را ارسال کنید:",
        reply_markup=cancel_only(),
    )
    await callback.answer()


@router.callback_query(DiamondFlow.choosing_plan, DiamondCB.filter(F.action == "lvl_all"))
async def levelup_all(
    callback: CallbackQuery, services: Services, state: FSMContext
) -> None:
    plans = await services.diamond.list_plans_by_category(CAT_LEVELUP)
    all_price = await services.diamond.get_levelup_all_price()
    names = "، ".join(p.name for p in plans)
    await state.update_data(
        levelup_mode="all",
        levelup_name=f"خرید همه لول‌اپ‌ها ({names})"[:200],
        levelup_price=all_price,
    )
    await state.set_state(DiamondUIDFlow.entering_uid)
    await callback.message.edit_text(
        f"پلن: خرید همه لول‌اپ‌ها — {format_toman(all_price)}\n\n"
        f"🆔 لطفاً <b>UID</b> اکانت خود را ارسال کنید:",
        reply_markup=cancel_only(),
    )
    await callback.answer()


@router.callback_query(DiamondFlow.choosing_plan, DiamondCB.filter(F.action == "plan"))
async def plan_chosen(
    callback: CallbackQuery, callback_data: DiamondCB, services: Services, state: FSMContext
) -> None:
    plan = await services.diamond.get_plan(callback_data.value)
    if not plan:
        await callback.answer("پلن یافت نشد.", show_alert=True)
        return
    await state.update_data(plan_code=plan.code)
    data = await state.get_data()
    if data.get("method") == "account":
        await state.set_state(DiamondAccountFlow.choosing_save_type)
        await callback.message.edit_text(
            f"پلن: {plan.name} — {format_toman(plan.price)}\n\n"
            f"🎮 سیو بازی شما روی کدام سرویس است؟",
            reply_markup=diamond_save_type_menu(),
        )
    else:
        await state.set_state(DiamondUIDFlow.entering_uid)
        await callback.message.edit_text(
            f"پلن: {plan.name} — {format_toman(plan.price)}\n\n"
            f"🆔 لطفاً <b>UID</b> اکانت خود را ارسال کنید:",
            reply_markup=cancel_only(),
        )
    await callback.answer()


@router.callback_query(
    DiamondAccountFlow.choosing_save_type, DiamondCB.filter(F.action == "save_type")
)
async def save_type_chosen(
    callback: CallbackQuery, callback_data: DiamondCB, services: Services, state: FSMContext
) -> None:
    """Store the chosen game save type, then ask for the account email/login id."""
    try:
        method = LoginMethod(callback_data.value)
    except ValueError:
        await callback.answer("گزینه نامعتبر است.", show_alert=True)
        return
    await state.update_data(save_type=method.value)
    plan = await services.diamond.get_plan((await state.get_data())["plan_code"])
    save_fa = LOGIN_METHOD_FA.get(method, method.value)
    await state.set_state(DiamondAccountFlow.entering_email)
    await callback.message.edit_text(
        f"پلن: {plan.name} — {format_toman(plan.price)}\n"
        f"🎮 نوع سیو: {save_fa}\n\n"
        f"📧 ایمیل / آیدی لاگین اکانت را ارسال کنید:",
        reply_markup=cancel_only(),
    )
    await callback.answer()


@router.callback_query(NavCB.filter((F.action == "back") & (F.target == "diamond_method")))
async def back_to_method(
    callback: CallbackQuery, services: Services, state: FSMContext
) -> None:
    await state.set_state(DiamondFlow.choosing_method)
    text, entities = await services.text.render("diamond_guide")
    if entities:
        await callback.message.edit_text(
            text, entities=entities, parse_mode=None, reply_markup=diamond_method_menu()
        )
    else:
        await callback.message.edit_text(text, reply_markup=diamond_method_menu())
    await callback.answer()


@router.callback_query(NavCB.filter((F.action == "back") & (F.target == "diamond_category")))
async def back_to_category(
    callback: CallbackQuery, services: Services, state: FSMContext
) -> None:
    await state.set_state(DiamondFlow.choosing_category)
    await callback.message.edit_text(
        "🆔 <b>خرید با UID</b>\nنوع خرید را انتخاب کنید:",
        reply_markup=diamond_category_menu(),
    )
    await callback.answer()


# ----------------------- UID flow -----------------------
@router.message(DiamondUIDFlow.entering_uid, F.text)
async def uid_received(
    message: Message, services: Services, state: FSMContext, db_user: User
) -> None:
    uid = message.text.strip()
    if not is_valid_uid(uid):
        await message.answer("❌ UID نامعتبر است. یک عدد ۶ تا ۱۲ رقمی ارسال کنید.")
        return
    data = await state.get_data()
    if data.get("levelup_mode"):
        # Multi-select / buy-all Level-Up: a synthetic plan carries the combined
        # name and total price (built in levelup_done / levelup_all).
        plan = DiamondPlan(
            code="levelup_bundle",
            name=data["levelup_name"],
            diamonds=0,
            price=data["levelup_price"],
            category=CAT_LEVELUP,
        )
    else:
        plan = await services.diamond.get_plan(data["plan_code"])
    order = await services.diamond.create_uid_order(db_user.id, plan, uid)
    await services.commit()
    await state.update_data(order_id=order.id, uid=uid)
    await prompt_discount(
        message,
        state,
        order_id=order.id,
        base_amount=plan.price,
        receipt_state=DiamondUIDFlow.awaiting_receipt,
    )


@router.message(DiamondUIDFlow.awaiting_receipt, F.photo)
async def uid_receipt(
    message: Message, services: Services, state: FSMContext, db_user: User, bot
) -> None:
    await _finalize_receipt(message, services, state, db_user, bot)


# ----------------------- Account-credentials flow -----------------------
@router.message(DiamondAccountFlow.entering_email, F.text)
async def acc_email(message: Message, state: FSMContext) -> None:
    email = message.text.strip()
    if not is_valid_email(email):
        await message.answer("❌ ایمیل نامعتبر است. دوباره ارسال کنید.")
        return
    await state.update_data(email=email)
    await state.set_state(DiamondAccountFlow.entering_gmail_password)
    await message.answer("🔑 رمز عبور جیمیل را ارسال کنید:", reply_markup=cancel_only())


@router.message(DiamondAccountFlow.entering_gmail_password, F.text)
async def acc_gmail_password(message: Message, state: FSMContext) -> None:
    await state.update_data(gmail_password=message.text.strip())
    await state.set_state(DiamondAccountFlow.entering_backup)
    await message.answer(
        "🧩 کد بکاپ را ارسال کنید (اگر ندارید بنویسید «ندارم»):\n"
        "برای آموزش گرفتن کد بکاپ گوگل، دکمه زیر را بزنید 👇",
        reply_markup=backup_code_menu(GOOGLE_BACKUP_CODE_VIDEO),
    )


@router.callback_query(
    TutorialCB.filter(F.action == "watch"),
    StateFilter(DiamondAccountFlow.entering_backup),
)
async def watch_backup_tutorial(
    callback: CallbackQuery, callback_data: TutorialCB, services: Services
) -> None:
    """Send the tutorial video; the user stays in the backup-code step."""
    file_id = await services.tutorial.get_file_id(callback_data.key)
    if file_id:
        try:
            await callback.message.answer_video(
                file_id, caption="🎥 آموزش گرفتن Backup Code گوگل"
            )
        except Exception:  # noqa: BLE001 - file_id may be stale
            await callback.answer(
                "ارسال ویدیو ناموفق بود. لطفاً بعداً تلاش کنید.", show_alert=True
            )
            return
        await callback.message.answer(
            "🧩 پس از تماشای آموزش، کد بکاپ را ارسال کنید (اگر ندارید بنویسید «ندارم»):",
            reply_markup=backup_code_menu(callback_data.key),
        )
        await callback.answer()
    else:
        await callback.answer(
            "هنوز ویدیوی آموزشی ثبت نشده است. لطفاً با پشتیبانی در ارتباط باشید.",
            show_alert=True,
        )


def _optional(text: str) -> str:
    """Normalize an optional free-text answer; «ندارم»/«-» mean «not provided»."""
    value = text.strip()
    return "" if value in {"ندارم", "-"} else value


@router.message(DiamondAccountFlow.entering_backup, F.text)
async def acc_backup(
    message: Message, services: Services, state: FSMContext, db_user: User
) -> None:
    data = await state.get_data()
    plan = await services.diamond.get_plan(data["plan_code"])
    save_value = data.get("save_type")
    login_method = LoginMethod(save_value) if save_value else None
    order = await services.diamond.create_account_order(
        db_user.id,
        plan,
        email=data["email"],
        gmail_password=data["gmail_password"],
        backup_code=_optional(message.text),
        login_method=login_method,
    )
    await services.commit()
    await state.update_data(order_id=order.id)
    save_fa = LOGIN_METHOD_FA.get(login_method, "-") if login_method else "-"
    await prompt_discount(
        message,
        state,
        order_id=order.id,
        base_amount=plan.price,
        receipt_state=DiamondAccountFlow.awaiting_receipt,
        prefix=f"اطلاعات ثبت شد. ✅\n🎮 نوع سیو: {save_fa}\n\n",
    )


@router.message(DiamondAccountFlow.awaiting_receipt, F.photo)
async def acc_receipt(
    message: Message, services: Services, state: FSMContext, db_user: User, bot
) -> None:
    await _finalize_receipt(message, services, state, db_user, bot)


# ----------------------- shared receipt finalization -----------------------
async def _finalize_receipt(
    message: Message, services: Services, state: FSMContext, db_user: User, bot
) -> None:
    data = await state.get_data()
    order = await services.order.get(data["order_id"])
    if order is None:
        await message.answer("سفارش یافت نشد. لطفاً دوباره تلاش کنید.")
        await state.clear()
        return
    file_id = message.photo[-1].file_id
    await services.order.attach_receipt(order, file_id)
    await services.commit()

    await safe_answer(
        message,
        f"✅ رسید شما دریافت شد.\nشماره سفارش: <b>#{order.id}</b>\n"
        f"سفارش شما در حال بررسی توسط پشتیبانی است و به‌زودی نتیجه اعلام می‌شود.",
        reply_markup=await build_main_menu(services, is_admin_user(message, db_user)),
    )

    notifier = NotificationService(bot)
    from app.keyboards.inline import admin_order_review

    method_fa = PAYMENT_METHOD_FA.get(order.payment_method, "-")
    save_value = data.get("save_type")
    save_line = ""
    if save_value:
        try:
            save_line = f"🎮 نوع سیو: {LOGIN_METHOD_FA.get(LoginMethod(save_value), '-')}\n"
        except ValueError:
            save_line = ""
    caption = (
        f"🆕 <b>سفارش جدید جم</b>\n"
        f"سفارش: #{order.id}\n"
        f"کاربر: {user_ref(db_user)}\n"
        f"{save_line}"
        f"روش پرداخت: {method_fa}\n"
        f"مبلغ: {format_toman(order.amount)}"
    )
    try:
        await bot.send_photo(
            settings.admin_id,
            file_id,
            caption=caption,
            reply_markup=admin_order_review(order.id),
        )
    except Exception:  # noqa: BLE001 - admin notification must not break user flow
        await notifier.notify_admin(caption, reply_markup=admin_order_review(order.id))

    # Additive layer: also alert every other authorized admin (the legacy send
    # above already covered settings.admin_id). Pending Orders is unaffected.
    await notifier.notify_admins(
        await services.admin.all_admin_ids(),
        caption,
        reply_markup=admin_order_review(order.id),
        photo=file_id,
        exclude={settings.admin_id},
    )

    await notifier.log_event(
        "سفارش جم",
        {"سفارش": f"#{order.id}", "کاربر": user_ref(db_user), "مبلغ": format_toman(order.amount)},
    )
    await state.clear()


@router.message(
    StateFilter(
        DiamondUIDFlow.awaiting_receipt,
        DiamondAccountFlow.awaiting_receipt,
    )
)
async def receipt_not_photo(message: Message) -> None:
    await message.answer("لطفاً <b>تصویر</b> رسید را ارسال کنید. 📸")
