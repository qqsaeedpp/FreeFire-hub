"""Admin: edit user-facing bot texts, preserving premium (custom) emoji.

Texts are listed as inline buttons; selecting one shows its current value and
offers ✏️ edit / 🔄 reset-to-default. When the admin sends a replacement, the
message's entities (including ``custom_emoji``) are captured verbatim so the
text can later be re-sent with the exact same premium emoji.
"""
from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.container import Services
from app.filters.admin import IsAdmin
from app.keyboards.callbacks import AdminCB, BotTextCB
from app.keyboards.inline import cancel_only
from app.services.text_service import TEXT_LABELS
from app.states.admin_states import BotTextEditFlow
from app.utils.helpers import answer_managed, edit_or_answer

router = Router(name="admin_texts")


def _texts_list_kb():
    kb = InlineKeyboardBuilder()
    for key, label in TEXT_LABELS.items():
        kb.button(text=f"📝 {label}", callback_data=BotTextCB(action="view", key=key))
    kb.button(text="🔙 بازگشت", callback_data=AdminCB(action="back_home"))
    kb.adjust(1)
    return kb.as_markup()


def _text_detail_kb(key: str):
    kb = InlineKeyboardBuilder()
    kb.button(text="✏️ ویرایش متن", callback_data=BotTextCB(action="edit", key=key))
    kb.button(text="🔄 بازگردانی به پیش‌فرض", callback_data=BotTextCB(action="reset", key=key))
    kb.button(text="🔙 بازگشت", callback_data=BotTextCB(action="list"))
    kb.adjust(1)
    return kb.as_markup()


@router.callback_query(AdminCB.filter(F.action == "texts"), IsAdmin())
async def texts_home(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await edit_or_answer(
        callback.message,
        "📝 <b>مدیریت متن‌های ربات</b>\nمتن مورد نظر را برای ویرایش انتخاب کنید:",
        reply_markup=_texts_list_kb(),
    )
    await callback.answer()


@router.callback_query(BotTextCB.filter(F.action == "list"), IsAdmin())
async def texts_list(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await edit_or_answer(
        callback.message,
        "📝 <b>مدیریت متن‌های ربات</b>\nمتن مورد نظر را برای ویرایش انتخاب کنید:",
        reply_markup=_texts_list_kb(),
    )
    await callback.answer()


@router.callback_query(BotTextCB.filter(F.action == "view"), IsAdmin())
async def text_view(
    callback: CallbackQuery, callback_data: BotTextCB, services: Services
) -> None:
    key = callback_data.key
    label = TEXT_LABELS.get(key, key)
    rendered = await services.text.render(key)
    await edit_or_answer(
        callback.message,
        f"📝 <b>{label}</b>\n\nمتن فعلی در پیام بعدی نمایش داده می‌شود 👇",
        reply_markup=_text_detail_kb(key),
    )
    # Show the live text exactly as users see it (premium emoji included).
    await answer_managed(callback.message, rendered)
    await callback.answer()


@router.callback_query(BotTextCB.filter(F.action == "edit"), IsAdmin())
async def text_edit_start(
    callback: CallbackQuery, callback_data: BotTextCB, state: FSMContext
) -> None:
    label = TEXT_LABELS.get(callback_data.key, callback_data.key)
    await state.set_state(BotTextEditFlow.entering_text)
    await state.update_data(text_key=callback_data.key)
    await edit_or_answer(
        callback.message,
        f"✏️ متن جدید «{label}» را ارسال کنید.\n"
        "می‌توانید از ایموجی پرمیوم و قالب‌بندی تلگرام استفاده کنید.",
        reply_markup=cancel_only(),
    )
    await callback.answer()


@router.message(BotTextEditFlow.entering_text, F.text, IsAdmin())
async def text_edit_save(
    message: Message, services: Services, state: FSMContext
) -> None:
    data = await state.get_data()
    key = data.get("text_key")
    if not key:
        await state.clear()
        await message.answer("خطا: کلید متن یافت نشد.")
        return
    # Capture the entities the admin typed (custom_emoji, bold, links, …) so the
    # premium emoji round-trip exactly when the text is re-sent to users.
    entities = list(message.entities) if message.entities else None
    await services.text.set(key, message.text, entities)
    await services.commit()
    await state.clear()
    label = TEXT_LABELS.get(key, key)
    await message.answer(f"✅ متن «{label}» به‌روزرسانی شد.")


@router.callback_query(BotTextCB.filter(F.action == "reset"), IsAdmin())
async def text_reset(
    callback: CallbackQuery, callback_data: BotTextCB, services: Services
) -> None:
    key = callback_data.key
    row = await services.bot_texts_repo.get_by_key(key)
    if row is not None:
        await services.bot_texts_repo.delete(row)
        await services.commit()
    label = TEXT_LABELS.get(key, key)
    rendered = await services.text.render(key)
    await edit_or_answer(
        callback.message,
        f"🔄 متن «{label}» به حالت پیش‌فرض بازگردانده شد. نمونه 👇",
        reply_markup=_text_detail_kb(key),
    )
    await answer_managed(callback.message, rendered)
    await callback.answer("بازگردانی شد.")
