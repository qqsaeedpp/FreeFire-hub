"""Admin: manage discount codes (diamond purchases only).

Codes are listed as inline buttons; selecting one opens a detail card with
buttons to edit each field (percent, usage cap, start/expiry dates), toggle
active state, or delete the code.
"""
from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.container import Services
from app.filters.admin import IsAdmin
from app.keyboards.callbacks import AdminCB, DiscountCB
from app.keyboards.inline import cancel_only
from app.models.discount import DiscountCode
from app.states.admin_states import DiscountCreateFlow, DiscountEditFlow
from app.utils.helpers import edit_or_answer
from app.utils.validators import parse_price

router = Router(name="admin_discounts")


def _codes_list_kb(codes: list[DiscountCode]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for c in codes:
        mark = "✅" if c.is_active else "🚫"
        kb.button(
            text=f"{mark} {c.code} — {c.percent}%",
            callback_data=DiscountCB(action="view", code_id=c.id),
        )
    kb.button(text="➕ کد جدید", callback_data=AdminCB(action="discount_create"))
    kb.button(text="🔙 بازگشت", callback_data=AdminCB(action="back_home"))
    kb.adjust(1)
    return kb.as_markup()


def _code_detail_kb(code_id: int, is_active: bool) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✏️ درصد تخفیف", callback_data=DiscountCB(action="edit_percent", code_id=code_id))
    kb.button(text="✏️ سقف مصرف", callback_data=DiscountCB(action="edit_uses", code_id=code_id))
    kb.button(text="📅 تاریخ شروع", callback_data=DiscountCB(action="edit_start", code_id=code_id))
    kb.button(text="📅 تاریخ انقضا", callback_data=DiscountCB(action="edit_expiry", code_id=code_id))
    toggle = "🚫 غیرفعال‌کردن" if is_active else "✅ فعال‌کردن"
    kb.button(text=toggle, callback_data=DiscountCB(action="toggle", code_id=code_id))
    kb.button(text="🗑 حذف کد تخفیف", callback_data=DiscountCB(action="delete", code_id=code_id))
    kb.button(text="🔙 بازگشت", callback_data=DiscountCB(action="list"))
    kb.adjust(2, 2, 1, 1, 1)
    return kb.as_markup()


def _detail_text(c: DiscountCode) -> str:
    status = "فعال" if c.is_active else "غیرفعال"
    limit = "نامحدود" if c.max_uses == 0 else f"{c.used_count}/{c.max_uses}"
    start = c.starts_at.strftime("%Y-%m-%d") if c.starts_at else "بدون محدودیت"
    exp = c.expires_at.strftime("%Y-%m-%d") if c.expires_at else "بدون انقضا"
    return (
        f"🎟 <b>کد تخفیف</b> <code>{c.code}</code>\n\n"
        f"درصد: {c.percent}%\n"
        f"مصرف: {limit}\n"
        f"تاریخ شروع: {start}\n"
        f"تاریخ انقضا: {exp}\n"
        f"وضعیت: {status}"
    )


async def _show_list(callback: CallbackQuery, services: Services) -> None:
    codes = await services.discount.list_codes()
    text = "🎟 <b>کدهای تخفیف</b> (فقط خرید جم)\n\nیک کد را برای مدیریت انتخاب کنید:"
    if not codes:
        text = "🎟 <b>کدهای تخفیف</b>\n\nهنوز کدی ثبت نشده است."
    await edit_or_answer(callback.message, text, reply_markup=_codes_list_kb(codes))


async def _show_detail(callback: CallbackQuery, c: DiscountCode) -> None:
    await edit_or_answer(
        callback.message, _detail_text(c), reply_markup=_code_detail_kb(c.id, c.is_active)
    )


@router.callback_query(AdminCB.filter(F.action == "discounts"), IsAdmin())
async def discounts_home(callback: CallbackQuery, services: Services, state: FSMContext) -> None:
    await state.clear()
    await _show_list(callback, services)
    await callback.answer()


@router.callback_query(DiscountCB.filter(F.action == "list"), IsAdmin())
async def discounts_list(callback: CallbackQuery, services: Services, state: FSMContext) -> None:
    await state.clear()
    await _show_list(callback, services)
    await callback.answer()


@router.callback_query(DiscountCB.filter(F.action == "view"), IsAdmin())
async def code_detail(
    callback: CallbackQuery, callback_data: DiscountCB, services: Services
) -> None:
    c = await services.discount.get_code(callback_data.code_id)
    if c is None:
        await callback.answer("کد یافت نشد.", show_alert=True)
        return
    await _show_detail(callback, c)
    await callback.answer()


@router.callback_query(DiscountCB.filter(F.action == "toggle"), IsAdmin())
async def code_toggle(
    callback: CallbackQuery, callback_data: DiscountCB, services: Services
) -> None:
    c = await services.discount.get_code(callback_data.code_id)
    if c is None:
        await callback.answer("کد یافت نشد.", show_alert=True)
        return
    await services.discount.toggle_active(c)
    await services.commit()
    await _show_detail(callback, c)
    await callback.answer("وضعیت تغییر کرد.")


@router.callback_query(DiscountCB.filter(F.action == "delete"), IsAdmin())
async def code_delete_confirm(
    callback: CallbackQuery, callback_data: DiscountCB, services: Services
) -> None:
    c = await services.discount.get_code(callback_data.code_id)
    if c is None:
        await callback.answer("کد یافت نشد.", show_alert=True)
        return
    kb = InlineKeyboardBuilder()
    kb.button(
        text="✅ بله، حذف شود",
        callback_data=DiscountCB(action="confirm_delete", code_id=c.id),
    )
    kb.button(text="❌ انصراف", callback_data=DiscountCB(action="view", code_id=c.id))
    kb.adjust(1)
    await edit_or_answer(
        callback.message,
        f"آیا از حذف کد <code>{c.code}</code> مطمئن هستید؟",
        reply_markup=kb.as_markup(),
    )
    await callback.answer()


@router.callback_query(DiscountCB.filter(F.action == "confirm_delete"), IsAdmin())
async def code_delete(
    callback: CallbackQuery, callback_data: DiscountCB, services: Services
) -> None:
    c = await services.discount.get_code(callback_data.code_id)
    if c is not None:
        await services.discount.delete_code(c)
        await services.commit()
    await _show_list(callback, services)
    await callback.answer("حذف شد.")


# ---- field-edit flows ----
_EDIT_PROMPTS = {
    "edit_percent": ("درصد تخفیف جدید را وارد کنید (۱ تا ۱۰۰):", DiscountEditFlow.entering_percent),
    "edit_uses": ("سقف مصرف جدید را وارد کنید (۰ = نامحدود):", DiscountEditFlow.entering_max_uses),
    "edit_start": ("شروع اعتبار از چند روز بعد؟ (۰ = از همین حالا):", DiscountEditFlow.entering_start_days),
    "edit_expiry": ("اعتبار تا چند روز دیگر؟ (۰ = بدون انقضا):", DiscountEditFlow.entering_expiry_days),
}


@router.callback_query(
    DiscountCB.filter(F.action.in_(list(_EDIT_PROMPTS))), IsAdmin()
)
async def code_edit_start(
    callback: CallbackQuery, callback_data: DiscountCB, state: FSMContext
) -> None:
    prompt, target = _EDIT_PROMPTS[callback_data.action]
    await state.set_state(target)
    await state.update_data(code_id=callback_data.code_id)
    await edit_or_answer(callback.message, prompt, reply_markup=cancel_only())
    await callback.answer()


async def _apply_edit(
    message: Message, services: Services, state: FSMContext, value: int, apply
) -> None:
    data = await state.get_data()
    c = await services.discount.get_code(data.get("code_id", 0))
    if c is None:
        await state.clear()
        await message.answer("کد یافت نشد.")
        return
    await apply(c, value)
    await services.commit()
    await state.clear()
    await message.answer(_detail_text(c), reply_markup=_code_detail_kb(c.id, c.is_active))


@router.message(DiscountEditFlow.entering_percent, F.text, IsAdmin())
async def edit_percent(message: Message, services: Services, state: FSMContext) -> None:
    percent = parse_price(message.text)
    if percent is None or not 1 <= percent <= 100:
        await message.answer("❌ درصد نامعتبر است. عددی بین ۱ تا ۱۰۰ وارد کنید.")
        return
    await _apply_edit(message, services, state, percent, services.discount.set_percent)


@router.message(DiscountEditFlow.entering_max_uses, F.text, IsAdmin())
async def edit_max_uses(message: Message, services: Services, state: FSMContext) -> None:
    max_uses = parse_price(message.text)
    if max_uses is None or max_uses < 0:
        await message.answer("❌ عدد نامعتبر است.")
        return
    await _apply_edit(message, services, state, max_uses, services.discount.set_max_uses)


@router.message(DiscountEditFlow.entering_start_days, F.text, IsAdmin())
async def edit_start_days(message: Message, services: Services, state: FSMContext) -> None:
    days = parse_price(message.text)
    if days is None or days < 0:
        await message.answer("❌ عدد نامعتبر است.")
        return
    await _apply_edit(message, services, state, days, services.discount.set_start_in_days)


@router.message(DiscountEditFlow.entering_expiry_days, F.text, IsAdmin())
async def edit_expiry_days(message: Message, services: Services, state: FSMContext) -> None:
    days = parse_price(message.text)
    if days is None or days < 0:
        await message.answer("❌ عدد نامعتبر است.")
        return
    await _apply_edit(message, services, state, days, services.discount.set_expiry_in_days)


# ---- create flow ----
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
