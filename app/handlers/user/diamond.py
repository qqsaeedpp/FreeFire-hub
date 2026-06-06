"""Diamond purchase flows — by UID and by account credentials."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.container import Services
from app.core.config import settings
from app.core.constants import PAYMENT_METHOD_FA
from app.keyboards.callbacks import DiamondCB, NavCB, TutorialCB
from app.keyboards.inline import (
    backup_code_menu,
    cancel_only,
    diamond_amount_menu,
    diamond_method_menu,
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
    # New flow: pick the diamond amount first, then the purchase method.
    await state.set_state(DiamondFlow.choosing_amount)
    plans = await services.diamond.list_plans()
    text, entities = await services.text.render("diamond_guide")
    if entities:
        await message.answer(
            text, entities=entities, parse_mode=None,
            reply_markup=diamond_amount_menu(plans),
        )
    else:
        await message.answer(text, reply_markup=diamond_amount_menu(plans))


@router.callback_query(DiamondFlow.choosing_amount, DiamondCB.filter(F.action == "plan"))
async def amount_chosen(
    callback: CallbackQuery, callback_data: DiamondCB, services: Services, state: FSMContext
) -> None:
    plan = await services.diamond.get_plan(callback_data.value)
    if not plan:
        await callback.answer("پلن یافت نشد.", show_alert=True)
        return
    await state.update_data(plan_code=plan.code)
    await state.set_state(DiamondFlow.choosing_method)
    await callback.message.edit_text(
        f"💎 پلن انتخابی: <b>{plan.name}</b> — {format_toman(plan.price)}\n\n"
        f"روش خرید را انتخاب کنید:",
        reply_markup=diamond_method_menu(),
    )
    await callback.answer()


@router.callback_query(DiamondFlow.choosing_method, DiamondCB.filter(F.action == "method"))
async def method_chosen(
    callback: CallbackQuery, callback_data: DiamondCB, services: Services, state: FSMContext
) -> None:
    data = await state.get_data()
    plan = await services.diamond.get_plan(data.get("plan_code"))
    if not plan:
        await callback.answer("ابتدا مقدار جم را انتخاب کنید.", show_alert=True)
        return
    if callback_data.value == "uid":
        await state.set_state(DiamondUIDFlow.entering_uid)
        await callback.message.edit_text(
            f"پلن: {plan.name} — {format_toman(plan.price)}\n\n"
            f"🆔 لطفاً <b>UID</b> اکانت خود را ارسال کنید:",
            reply_markup=cancel_only(),
        )
    else:
        await state.set_state(DiamondAccountFlow.entering_email)
        await callback.message.edit_text(
            f"پلن: {plan.name} — {format_toman(plan.price)}\n\n"
            f"📧 ایمیل اکانت را ارسال کنید:",
            reply_markup=cancel_only(),
        )
    await callback.answer()


@router.callback_query(NavCB.filter((F.action == "back") & (F.target == "diamond_amount")))
async def back_to_amount(
    callback: CallbackQuery, services: Services, state: FSMContext
) -> None:
    await state.set_state(DiamondFlow.choosing_amount)
    plans = await services.diamond.list_plans()
    await callback.message.edit_text(
        "💎 <b>خرید جم</b>\nمقدار جم مورد نظر را انتخاب کنید:",
        reply_markup=diamond_amount_menu(plans),
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
    order = await services.diamond.create_account_order(
        db_user.id,
        plan,
        email=data["email"],
        gmail_password=data["gmail_password"],
        backup_code=_optional(message.text),
    )
    await services.commit()
    await state.update_data(order_id=order.id)
    await prompt_discount(
        message,
        state,
        order_id=order.id,
        base_amount=plan.price,
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

    await safe_answer(
        message,
        f"✅ رسید شما دریافت شد.\nشماره سفارش: <b>#{order.id}</b>\n"
        f"سفارش شما در حال بررسی توسط پشتیبانی است و به‌زودی نتیجه اعلام می‌شود.",
        reply_markup=await build_main_menu(services, is_admin_user(message, db_user)),
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
