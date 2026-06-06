"""Admin: manage the card-to-card destination for each sales channel."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.container import Services
from app.core.constants import CARD_PURPOSE_FA, CardPurpose
from app.filters.admin import IsAdmin
from app.keyboards.callbacks import AdminCardCB, AdminCB
from app.keyboards.inline import cancel_only
from app.states.admin_states import CardFlow
from app.utils.helpers import edit_or_answer

router = Router(name="admin_cards")


async def _cards_overview(services: Services) -> tuple[str, InlineKeyboardBuilder]:
    lines = ["💳 <b>مدیریت کارت‌ها</b>\n"]
    kb = InlineKeyboardBuilder()
    for purpose in CardPurpose:
        card = await services.card.get_card(purpose)
        current = (
            f"<code>{card.card_number}</code> — {card.holder_name}"
            if card
            else "ثبت‌نشده"
        )
        lines.append(f"{CARD_PURPOSE_FA[purpose]}:\n{current}\n")
        kb.button(
            text=f"✏️ {CARD_PURPOSE_FA[purpose]}",
            callback_data=AdminCardCB(purpose=purpose.value),
        )
    kb.adjust(1)
    return "\n".join(lines), kb


@router.callback_query(AdminCB.filter(F.action == "cards"), IsAdmin())
async def cards_home(callback: CallbackQuery, services: Services) -> None:
    text, kb = await _cards_overview(services)
    await edit_or_answer(callback.message, text, reply_markup=kb.as_markup())
    await callback.answer()


@router.callback_query(AdminCardCB.filter(), IsAdmin())
async def card_edit_start(
    callback: CallbackQuery, callback_data: AdminCardCB, state: FSMContext
) -> None:
    purpose = CardPurpose(callback_data.purpose)
    await state.set_state(CardFlow.entering_number)
    await state.update_data(card_purpose=purpose.value)
    await edit_or_answer(
        callback.message,
        f"شماره کارت برای «{CARD_PURPOSE_FA[purpose]}» را وارد کنید:",
        reply_markup=cancel_only(),
    )
    await callback.answer()


@router.message(CardFlow.entering_number, F.text, IsAdmin())
async def card_number_entered(message: Message, state: FSMContext) -> None:
    await state.update_data(card_number=message.text.strip()[:32])
    await state.set_state(CardFlow.entering_holder)
    await message.answer("نام صاحب کارت را وارد کنید:", reply_markup=cancel_only())


@router.message(CardFlow.entering_holder, F.text, IsAdmin())
async def card_holder_entered(
    message: Message, services: Services, state: FSMContext
) -> None:
    data = await state.get_data()
    purpose = CardPurpose(data["card_purpose"])
    await services.card.set_card(
        purpose, data["card_number"], message.text.strip()[:128]
    )
    await services.commit()
    await state.clear()
    await message.answer(f"✅ کارت «{CARD_PURPOSE_FA[purpose]}» ذخیره شد.")
