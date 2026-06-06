"""Diamond purchase flows — by UID and by account credentials."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.container import Services
from app.core.config import settings
from app.core.constants import PAYMENT_METHOD_FA, LoginMethod
from app.keyboards.callbacks import DiamondCB, LoginMethodCB, NavCB
from app.keyboards.inline import (
    cancel_only,
    diamond_method_menu,
    diamond_plans_menu,
    login_method_menu,
)
from app.keyboards.reply import BTN_BUY_DIAMOND, main_menu
from app.models.user import User
from app.handlers.user.payment import prompt_payment_method
from app.services.notification_service import NotificationService
from app.states.user_states import DiamondAccountFlow, DiamondUIDFlow
from app.utils.helpers import edit_or_answer, format_toman, user_ref
from app.utils.validators import is_valid_email, is_valid_uid

router = Router(name="user_diamond")


@router.message(F.text == BTN_BUY_DIAMOND)
async def entry(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "💎 <b>خرید جم</b>\nروش خرید را انتخاب کنید:",
        reply_markup=diamond_method_menu(),
    )


@router.callback_query(DiamondCB.filter(F.action == "method"))
async def choose_method(
    callback: CallbackQuery, callback_data: DiamondCB, services: Services, state: FSMContext
) -> None:
    plans = await services.diamond.list_plans()
    if callback_data.value == "uid":
        await state.set_state(DiamondUIDFlow.choosing_plan)
    else:
        await state.set_state(DiamondAccountFlow.choosing_plan)
    await callback.message.edit_text(
        "📦 پلن مورد نظر را انتخاب کنید:", reply_markup=diamond_plans_menu(plans)
    )
    await callback.answer()


@router.callback_query(NavCB.filter((F.action == "back") & (F.target == "diamond_method")))
async def back_to_method(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text(
        "💎 <b>خرید جم</b>\nروش خرید را انتخاب کنید:",
        reply_markup=diamond_method_menu(),
    )
    await callback.answer()


# ----------------------- UID flow -----------------------
@router.callback_query(DiamondUIDFlow.choosing_plan, DiamondCB.filter(F.action == "plan"))
async def uid_plan_chosen(
    callback: CallbackQuery, callback_data: DiamondCB, services: Services, state: FSMContext
) -> None:
    plan = await services.diamond.get_plan(callback_data.value)
    if not plan:
        await callback.answer("پلن یافت نشد.", show_alert=True)
        return
    await state.update_data(plan_code=plan.code)
    await state.set_state(DiamondUIDFlow.entering_uid)
    await callback.message.edit_text(
        f"پلن: {plan.name} — {format_toman(plan.price)}\n\n"
        f"🆔 لطفاً <b>UID</b> اکانت خود را ارسال کنید:",
        reply_markup=cancel_only(),
    )
    await callback.answer()


@router.message(DiamondUIDFlow.entering_uid, F.text)
async def uid_received(
    message: Message, services: Services, state: FSMContext, db_user: User
) -> None:
    uid = message.text.strip()
    if not is_valid_uid(uid):
        await message.answer("❌ UID نامعتبر است. یک عدد ۶ تا ۱۲ رقمی ارسال کنید.")
        return
    data = await state.get_data()
    plan = await services.diamond.get_plan(data["plan_code"])
    order = await services.diamond.create_uid_order(db_user.id, plan, uid)
    await services.commit()
    await state.update_data(order_id=order.id, uid=uid)
    await prompt_payment_method(
        message,
        state,
        order_id=order.id,
        amount=plan.price,
        receipt_state=DiamondUIDFlow.awaiting_receipt,
    )


@router.message(DiamondUIDFlow.awaiting_receipt, F.photo)
async def uid_receipt(
    message: Message, services: Services, state: FSMContext, db_user: User, bot
) -> None:
    await _finalize_receipt(message, services, state, db_user, bot)


# ----------------------- Account-credentials flow -----------------------
@router.callback_query(
    DiamondAccountFlow.choosing_plan, DiamondCB.filter(F.action == "plan")
)
async def acc_plan_chosen(
    callback: CallbackQuery, callback_data: DiamondCB, services: Services, state: FSMContext
) -> None:
    plan = await services.diamond.get_plan(callback_data.value)
    if not plan:
        await callback.answer("پلن یافت نشد.", show_alert=True)
        return
    await state.update_data(plan_code=plan.code)
    await state.set_state(DiamondAccountFlow.entering_email)
    await callback.message.edit_text(
        f"پلن: {plan.name} — {format_toman(plan.price)}\n\n"
        f"📧 ایمیل اکانت را ارسال کنید:",
        reply_markup=cancel_only(),
    )
    await callback.answer()


@router.message(DiamondAccountFlow.entering_email, F.text)
async def acc_email(message: Message, state: FSMContext) -> None:
    email = message.text.strip()
    if not is_valid_email(email):
        await message.answer("❌ ایمیل نامعتبر است. دوباره ارسال کنید.")
        return
    await state.update_data(email=email)
    await state.set_state(DiamondAccountFlow.entering_password)
    await message.answer("🔑 رمز عبور اکانت را ارسال کنید:", reply_markup=cancel_only())


@router.message(DiamondAccountFlow.entering_password, F.text)
async def acc_password(message: Message, state: FSMContext) -> None:
    await state.update_data(password=message.text.strip())
    await state.set_state(DiamondAccountFlow.entering_backup)
    await message.answer(
        "🧩 کد بکاپ را ارسال کنید (اگر ندارید بنویسید «ندارم»):",
        reply_markup=cancel_only(),
    )


@router.message(DiamondAccountFlow.entering_backup, F.text)
async def acc_backup(message: Message, state: FSMContext) -> None:
    backup = message.text.strip()
    await state.update_data(backup="" if backup in {"ندارم", "-"} else backup)
    await state.set_state(DiamondAccountFlow.choosing_login_method)
    await message.answer("🔐 روش ورود به اکانت را انتخاب کنید:", reply_markup=login_method_menu())


@router.callback_query(
    DiamondAccountFlow.choosing_login_method, LoginMethodCB.filter()
)
async def acc_login_method(
    callback: CallbackQuery,
    callback_data: LoginMethodCB,
    services: Services,
    state: FSMContext,
    db_user: User,
) -> None:
    data = await state.get_data()
    plan = await services.diamond.get_plan(data["plan_code"])
    order = await services.diamond.create_account_order(
        db_user.id,
        plan,
        email=data["email"],
        password=data["password"],
        backup_code=data.get("backup", ""),
        login_method=LoginMethod(callback_data.method),
    )
    await services.commit()
    await state.update_data(order_id=order.id)
    await prompt_payment_method(
        callback,
        state,
        order_id=order.id,
        amount=plan.price,
        receipt_state=DiamondAccountFlow.awaiting_receipt,
        prefix="اطلاعات ثبت شد. ✅\n\n",
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

    await message.answer(
        f"✅ رسید شما دریافت شد.\nشماره سفارش: <b>#{order.id}</b>\n"
        f"سفارش شما در حال بررسی توسط پشتیبانی است و به‌زودی نتیجه اعلام می‌شود.",
        reply_markup=main_menu(db_user.is_admin),
    )

    notifier = NotificationService(bot)
    from app.keyboards.inline import admin_order_review

    method_fa = PAYMENT_METHOD_FA.get(order.payment_method, "-")
    caption = (
        f"🆕 <b>سفارش جدید جم</b>\n"
        f"سفارش: #{order.id}\n"
        f"کاربر: {user_ref(db_user)}\n"
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
