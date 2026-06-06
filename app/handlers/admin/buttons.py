"""Admin: edit the main reply-keyboard buttons' text and emoji (item 5).

Each main button has a stable key (see :mod:`app.services.button_service`). The
rendered label is ``"{emoji} {text}"`` resolved from the DB override or the
hardcoded default, so an admin can rename a button without any code change.

Note: ``button_type`` (color) and premium-emoji fields exist on the model for a
later appearance system; this section only manages text/emoji today.
"""
from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.container import Services
from app.filters.admin import IsAdmin
from app.keyboards.callbacks import AdminCB, ButtonCB
from app.keyboards.inline import cancel_only
from app.services.button_service import BUTTON_LABELS
from app.states.admin_states import ButtonEditFlow
from app.utils.helpers import edit_or_answer

router = Router(name="admin_buttons")


def _buttons_list_kb():
    kb = InlineKeyboardBuilder()
    for key, label in BUTTON_LABELS.items():
        kb.button(text=f"🎨 {label}", callback_data=ButtonCB(action="view", key=key))
    kb.button(text="🔙 بازگشت", callback_data=AdminCB(action="back_home"))
    kb.adjust(1)
    return kb.as_markup()


def _button_detail_kb(key: str):
    kb = InlineKeyboardBuilder()
    kb.button(text="✏️ تغییر متن", callback_data=ButtonCB(action="edit_text", key=key))
    kb.button(text="😀 تغییر ایموجی", callback_data=ButtonCB(action="edit_emoji", key=key))
    kb.button(text="🔄 بازگردانی به پیش‌فرض", callback_data=ButtonCB(action="reset", key=key))
    kb.button(text="🔙 بازگشت", callback_data=ButtonCB(action="list"))
    kb.adjust(2, 1, 1)
    return kb.as_markup()


async def _detail_text(services: Services, key: str) -> str:
    label = BUTTON_LABELS.get(key, key)
    current = await services.button.label(key)
    return (
        f"🎨 <b>{label}</b>\n\n"
        f"نمایش فعلی دکمه: <b>{current}</b>\n\n"
        "می‌توانید متن یا ایموجی این دکمه را تغییر دهید."
    )


@router.callback_query(AdminCB.filter(F.action == "buttons"), IsAdmin())
async def buttons_home(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await edit_or_answer(
        callback.message,
        "🎨 <b>مدیریت دکمه‌ها</b>\nدکمه‌ای را برای ویرایش انتخاب کنید:",
        reply_markup=_buttons_list_kb(),
    )
    await callback.answer()


@router.callback_query(ButtonCB.filter(F.action == "list"), IsAdmin())
async def buttons_list(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await edit_or_answer(
        callback.message,
        "🎨 <b>مدیریت دکمه‌ها</b>\nدکمه‌ای را برای ویرایش انتخاب کنید:",
        reply_markup=_buttons_list_kb(),
    )
    await callback.answer()


@router.callback_query(ButtonCB.filter(F.action == "view"), IsAdmin())
async def button_view(
    callback: CallbackQuery, callback_data: ButtonCB, services: Services
) -> None:
    key = callback_data.key
    await edit_or_answer(
        callback.message,
        await _detail_text(services, key),
        reply_markup=_button_detail_kb(key),
    )
    await callback.answer()


@router.callback_query(ButtonCB.filter(F.action == "edit_text"), IsAdmin())
async def button_edit_text_start(
    callback: CallbackQuery, callback_data: ButtonCB, state: FSMContext
) -> None:
    label = BUTTON_LABELS.get(callback_data.key, callback_data.key)
    await state.set_state(ButtonEditFlow.entering_text)
    await state.update_data(button_key=callback_data.key)
    await edit_or_answer(
        callback.message,
        f"✏️ متن جدید دکمه «{label}» را ارسال کنید (بدون ایموجی).",
        reply_markup=cancel_only(),
    )
    await callback.answer()


@router.message(ButtonEditFlow.entering_text, F.text, IsAdmin())
async def button_edit_text_save(
    message: Message, services: Services, state: FSMContext
) -> None:
    data = await state.get_data()
    key = data.get("button_key")
    if not key:
        await state.clear()
        await message.answer("خطا: کلید دکمه یافت نشد.")
        return
    await services.button.set_text(key, message.text.strip())
    await services.commit()
    await state.clear()
    label = BUTTON_LABELS.get(key, key)
    current = await services.button.label(key)
    await message.answer(
        f"✅ متن دکمه «{label}» به‌روزرسانی شد.\nنمایش جدید: <b>{current}</b>\n\n"
        "برای اعمال در منوی اصلی، دستور /start را بزنید."
    )


@router.callback_query(ButtonCB.filter(F.action == "edit_emoji"), IsAdmin())
async def button_edit_emoji_start(
    callback: CallbackQuery, callback_data: ButtonCB, state: FSMContext
) -> None:
    label = BUTTON_LABELS.get(callback_data.key, callback_data.key)
    await state.set_state(ButtonEditFlow.entering_emoji)
    await state.update_data(button_key=callback_data.key)
    await edit_or_answer(
        callback.message,
        f"😀 ایموجی جدید دکمه «{label}» را ارسال کنید (فقط یک ایموجی).",
        reply_markup=cancel_only(),
    )
    await callback.answer()


@router.message(ButtonEditFlow.entering_emoji, F.text, IsAdmin())
async def button_edit_emoji_save(
    message: Message, services: Services, state: FSMContext
) -> None:
    data = await state.get_data()
    key = data.get("button_key")
    if not key:
        await state.clear()
        await message.answer("خطا: کلید دکمه یافت نشد.")
        return
    await services.button.set_emoji(key, message.text.strip())
    await services.commit()
    await state.clear()
    label = BUTTON_LABELS.get(key, key)
    current = await services.button.label(key)
    await message.answer(
        f"✅ ایموجی دکمه «{label}» به‌روزرسانی شد.\nنمایش جدید: <b>{current}</b>\n\n"
        "برای اعمال در منوی اصلی، دستور /start را بزنید."
    )


@router.callback_query(ButtonCB.filter(F.action == "reset"), IsAdmin())
async def button_reset(
    callback: CallbackQuery, callback_data: ButtonCB, services: Services
) -> None:
    key = callback_data.key
    await services.button.reset(key)
    await services.commit()
    await edit_or_answer(
        callback.message,
        await _detail_text(services, key),
        reply_markup=_button_detail_kb(key),
    )
    await callback.answer("به پیش‌فرض بازگردانده شد.")
