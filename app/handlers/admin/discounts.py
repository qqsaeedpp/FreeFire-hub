"""Admin: create and list discount codes (diamond purchases only)."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.container import Services
from app.filters.admin import IsAdmin
from app.keyboards.callbacks import AdminCB
from app.keyboards.inline import cancel_only
from app.states.admin_states import DiscountCreateFlow
from app.utils.helpers import edit_or_answer
from app.utils.validators import parse_price

router = Router(name="admin_discounts")


@router.callback_query(AdminCB.filter(F.action == "discounts"), IsAdmin())
async def discounts_home(callback: CallbackQuery, services: Services) -> None:
    codes = await services.discount.list_codes()
    lines = ["🎟 <b>کدهای تخفیف</b> (فقط خرید جم)\n"]
    if codes:
        for c in codes:
            status = "فعال" if c.is_active else "غیرفعال"
            limit = "نامحدود" if c.max_uses == 0 else f"{c.used_count}/{c.max_uses}"
            exp = c.expires_at.strftime("%Y-%m-%d") if c.expires_at else "بدون انقضا"
            lines.append(
                f"<code>{c.code}</code> — {c.percent}% | مصرف: {limit} | "
                f"انقضا: {exp} | {status}"
            )
    else:
        lines.append("هنوز کدی ثبت نشده است.")
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ کد جدید", callback_data=AdminCB(action="discount_create"))
    await edit_or_answer(callback.message, "\n".join(lines), reply_markup=kb.as_markup())
    await callback.answer()


@router.callback_query(AdminCB.filter(F.action == "discount_create"), IsAdmin())
async def discount_create_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(DiscountCreateFlow.entering_code)
    await edit_or_answer(
        callback.message,
        "کد تخفیف را وارد کنید (مثلاً NOWRUZ):",
        reply_markup=cancel_only(),
    )
    await callback.answer()


@router.message(DiscountCreateFlow.entering_code, F.text, IsAdmin())
async def discount_code(message: Message, services: Services, state: FSMContext) -> None:
    code = message.text.strip()[:32]
    if await services.discount.codes.get_by_code(code):
        await message.answer("این کد قبلاً ثبت شده. کد دیگری وارد کنید.")
        return
    await state.update_data(code=code)
    await state.set_state(DiscountCreateFlow.entering_percent)
    await message.answer("درصد تخفیف را وارد کنید (۱ تا ۱۰۰):", reply_markup=cancel_only())


@router.message(DiscountCreateFlow.entering_percent, F.text, IsAdmin())
async def discount_percent(message: Message, state: FSMContext) -> None:
    percent = parse_price(message.text)
    if percent is None or not 1 <= percent <= 100:
        await message.answer("❌ درصد نامعتبر است. عددی بین ۱ تا ۱۰۰ وارد کنید.")
        return
    await state.update_data(percent=percent)
    await state.set_state(DiscountCreateFlow.entering_max_uses)
    await message.answer(
        "حداکثر تعداد دفعات استفاده را وارد کنید (۰ = نامحدود):",
        reply_markup=cancel_only(),
    )


@router.message(DiscountCreateFlow.entering_max_uses, F.text, IsAdmin())
async def discount_max_uses(message: Message, state: FSMContext) -> None:
    max_uses = parse_price(message.text)
    if max_uses is None or max_uses < 0:
        await message.answer("❌ عدد نامعتبر است.")
        return
    await state.update_data(max_uses=max_uses)
    await state.set_state(DiscountCreateFlow.entering_days)
    await message.answer(
        "مدت اعتبار را به روز وارد کنید (۰ = بدون محدودیت زمانی):",
        reply_markup=cancel_only(),
    )


@router.message(DiscountCreateFlow.entering_days, F.text, IsAdmin())
async def discount_days(message: Message, services: Services, state: FSMContext) -> None:
    days = parse_price(message.text)
    if days is None or days < 0:
        await message.answer("❌ عدد نامعتبر است.")
        return
    data = await state.get_data()
    await services.discount.create_code(
        data["code"],
        data["percent"],
        max_uses=data["max_uses"],
        valid_days=days or None,
    )
    await services.commit()
    await state.clear()
    await message.answer(
        f"✅ کد تخفیف <code>{data['code']}</code> با {data['percent']}% ساخته شد."
    )
