"""Admin: full appearance management for the main reply-keyboard buttons.

Per button the admin can set (all DB-backed, no code change needed):
* text & emoji (item 5);
* color — 🔵 primary / 🟢 success / 🔴 danger (Bot API 9.4 ``style``);
* enabled/disabled (a disabled button is hidden from the main menu);
* a premium (custom) emoji shown before the label (Bot API 9.4
  ``icon_custom_emoji_id``) — captured from a message the admin sends.

Premium emoji on buttons only renders for users if the bot's owner has Telegram
Premium (or the bot purchased a username on Fragment); otherwise Telegram keeps
the regular emoji. The setting is stored regardless.
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
from app.keyboards.style import STYLE_DOT, STYLE_LABELS, VALID_STYLES
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


def _button_detail_kb(key: str, *, is_enabled: bool, has_premium: bool):
    kb = InlineKeyboardBuilder()
    kb.button(text="✏️ تغییر متن", callback_data=ButtonCB(action="edit_text", key=key))
    kb.button(text="😀 تغییر ایموجی", callback_data=ButtonCB(action="edit_emoji", key=key))
    kb.button(text="🎨 رنگ دکمه", callback_data=ButtonCB(action="color", key=key))
    toggle_label = "🚫 غیرفعال‌کردن" if is_enabled else "✅ فعال‌کردن"
    kb.button(text=toggle_label, callback_data=ButtonCB(action="toggle", key=key))
    kb.button(text="⭐️ ایموجی پرمیوم", callback_data=ButtonCB(action="premium", key=key))
    if has_premium:
        kb.button(text="❎ حذف ایموجی پرمیوم", callback_data=ButtonCB(action="clear_premium", key=key))
    kb.button(text="🔄 بازگردانی به پیش‌فرض", callback_data=ButtonCB(action="reset", key=key))
    kb.button(text="🔙 بازگشت", callback_data=ButtonCB(action="list"))
    kb.adjust(2, 2, 1, 1, 1)
    return kb.as_markup()


def _color_picker_kb(key: str):
    kb = InlineKeyboardBuilder()
    for style in VALID_STYLES:
        kb.button(
            text=STYLE_LABELS[style],
            callback_data=ButtonCB(action="set_color", key=key, value=style),
        )
    kb.button(text="⚪️ بدون رنگ", callback_data=ButtonCB(action="set_color", key=key, value="none"))
    kb.button(text="🔙 بازگشت", callback_data=ButtonCB(action="view", key=key))
    kb.adjust(1)
    return kb.as_markup()


async def _detail_text(services: Services, key: str) -> str:
    label = BUTTON_LABELS.get(key, key)
    ap = await services.button.appearance(key)
    color_fa = STYLE_LABELS.get(ap.style, "⚪️ بدون رنگ (پیش‌فرض)")
    enabled_fa = "✅ فعال" if ap.is_enabled else "🚫 غیرفعال (پنهان)"
    premium_fa = f"⭐️ {ap.emoji_text or 'دارد'}" if ap.custom_emoji_id else "—"
    return (
        f"🎨 <b>{label}</b>\n\n"
        f"نمایش فعلی: <b>{ap.label}</b>\n"
        f"رنگ: {color_fa}\n"
        f"وضعیت: {enabled_fa}\n"
        f"ایموجی پرمیوم: {premium_fa}\n\n"
        "یکی از گزینه‌های زیر را انتخاب کنید:"
    )


async def _show_detail(callback: CallbackQuery, services: Services, key: str) -> None:
    ap = await services.button.appearance(key)
    await edit_or_answer(
        callback.message,
        await _detail_text(services, key),
        reply_markup=_button_detail_kb(
            key, is_enabled=ap.is_enabled, has_premium=bool(ap.custom_emoji_id)
        ),
    )


@router.callback_query(AdminCB.filter(F.action == "buttons"), IsAdmin())
async def buttons_home(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await edit_or_answer(
        callback.message,
        "🎨 <b>مدیریت ظاهر دکمه‌ها</b>\nدکمه‌ای را برای ویرایش انتخاب کنید:",
        reply_markup=_buttons_list_kb(),
    )
    await callback.answer()


@router.callback_query(ButtonCB.filter(F.action == "list"), IsAdmin())
async def buttons_list(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await edit_or_answer(
        callback.message,
        "🎨 <b>مدیریت ظاهر دکمه‌ها</b>\nدکمه‌ای را برای ویرایش انتخاب کنید:",
        reply_markup=_buttons_list_kb(),
    )
    await callback.answer()


@router.callback_query(ButtonCB.filter(F.action == "view"), IsAdmin())
async def button_view(
    callback: CallbackQuery, callback_data: ButtonCB, services: Services, state: FSMContext
) -> None:
    await state.clear()
    await _show_detail(callback, services, callback_data.key)
    await callback.answer()


# ----------------------------- TEXT -----------------------------
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


# ----------------------------- EMOJI -----------------------------
@router.callback_query(ButtonCB.filter(F.action == "edit_emoji"), IsAdmin())
async def button_edit_emoji_start(
    callback: CallbackQuery, callback_data: ButtonCB, state: FSMContext
) -> None:
    label = BUTTON_LABELS.get(callback_data.key, callback_data.key)
    await state.set_state(ButtonEditFlow.entering_emoji)
    await state.update_data(button_key=callback_data.key)
    await edit_or_answer(
        callback.message,
        f"😀 ایموجی جدید دکمه «{label}» را ارسال کنید (فقط یک ایموجی معمولی).",
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


# ----------------------------- COLOR -----------------------------
@router.callback_query(ButtonCB.filter(F.action == "color"), IsAdmin())
async def button_color_picker(
    callback: CallbackQuery, callback_data: ButtonCB
) -> None:
    label = BUTTON_LABELS.get(callback_data.key, callback_data.key)
    await edit_or_answer(
        callback.message,
        f"🎨 رنگ دکمه «{label}» را انتخاب کنید:\n\n"
        "🔵 آبی برای دکمه‌های اصلی، 🟢 سبز برای تایید، 🔴 قرمز برای حذف/خطر.",
        reply_markup=_color_picker_kb(callback_data.key),
    )
    await callback.answer()


@router.callback_query(ButtonCB.filter(F.action == "set_color"), IsAdmin())
async def button_set_color(
    callback: CallbackQuery, callback_data: ButtonCB, services: Services
) -> None:
    key = callback_data.key
    style = callback_data.value if callback_data.value in VALID_STYLES else None
    await services.button.set_color(key, style)
    await services.commit()
    await _show_detail(callback, services, key)
    dot = STYLE_DOT.get(style, "⚪️")
    await callback.answer(f"رنگ تنظیم شد {dot}")


# --------------------------- ENABLE/DISABLE ---------------------------
@router.callback_query(ButtonCB.filter(F.action == "toggle"), IsAdmin())
async def button_toggle(
    callback: CallbackQuery, callback_data: ButtonCB, services: Services
) -> None:
    key = callback_data.key
    ap = await services.button.appearance(key)
    await services.button.set_enabled(key, not ap.is_enabled)
    await services.commit()
    await _show_detail(callback, services, key)
    await callback.answer("فعال شد ✅" if not ap.is_enabled else "غیرفعال شد 🚫")


# --------------------------- PREMIUM EMOJI ---------------------------
@router.callback_query(ButtonCB.filter(F.action == "premium"), IsAdmin())
async def button_premium_start(
    callback: CallbackQuery, callback_data: ButtonCB, state: FSMContext
) -> None:
    label = BUTTON_LABELS.get(callback_data.key, callback_data.key)
    await state.set_state(ButtonEditFlow.entering_premium_emoji)
    await state.update_data(button_key=callback_data.key)
    await edit_or_answer(
        callback.message,
        f"⭐️ یک <b>ایموجی پرمیوم</b> برای دکمه «{label}» ارسال کنید.\n\n"
        "فقط یک ایموجی پرمیوم بفرستید (نیازمند اشتراک تلگرام پرمیوم).",
        reply_markup=cancel_only(),
    )
    await callback.answer()


@router.message(ButtonEditFlow.entering_premium_emoji, IsAdmin())
async def button_premium_save(
    message: Message, services: Services, state: FSMContext
) -> None:
    data = await state.get_data()
    key = data.get("button_key")
    if not key:
        await state.clear()
        await message.answer("خطا: کلید دکمه یافت نشد.")
        return
    # A premium emoji can arrive in the message text or in a media caption, so
    # inspect both entity lists. The matching slice of text/caption is kept as a
    # human-readable placeholder (``emoji_text``).
    source = message.text or message.caption or ""
    entities = list(message.entities or []) + list(message.caption_entities or [])
    custom_emoji_id = None
    emoji_text = source.strip()
    for ent in entities:
        if ent.type == "custom_emoji" and ent.custom_emoji_id:
            custom_emoji_id = ent.custom_emoji_id
            emoji_text = source[ent.offset : ent.offset + ent.length] or emoji_text
            break
    if not custom_emoji_id:
        await message.answer(
            "❌ ایموجی پرمیوم یافت نشد.\n\n"
            "لطفاً یک <b>ایموجی پرمیوم</b> (Custom Emoji) ارسال کنید — همان ایموجی‌های "
            "متحرک/ویژه‌ای که فقط با اشتراک تلگرام پرمیوم قابل ارسال‌اند. "
            "ایموجی معمولی پذیرفته نمی‌شود (برای ایموجی معمولی از «😀 تغییر ایموجی» استفاده کنید)."
        )
        return
    await services.button.set_premium_emoji(key, custom_emoji_id, emoji_text or None)
    await services.commit()
    await state.clear()
    label = BUTTON_LABELS.get(key, key)
    await message.answer(
        f"✅ ایموجی پرمیوم برای دکمه «{label}» تنظیم شد.\n\n"
        "اگر مالک ربات اشتراک پرمیوم داشته باشد، روی دکمه نمایش داده می‌شود. "
        "برای اعمال، دستور /start را بزنید."
    )


@router.callback_query(ButtonCB.filter(F.action == "clear_premium"), IsAdmin())
async def button_clear_premium(
    callback: CallbackQuery, callback_data: ButtonCB, services: Services
) -> None:
    await services.button.clear_premium_emoji(callback_data.key)
    await services.commit()
    await _show_detail(callback, services, callback_data.key)
    await callback.answer("ایموجی پرمیوم حذف شد.")


# ----------------------------- RESET -----------------------------
@router.callback_query(ButtonCB.filter(F.action == "reset"), IsAdmin())
async def button_reset(
    callback: CallbackQuery, callback_data: ButtonCB, services: Services
) -> None:
    await services.button.reset(callback_data.key)
    await services.commit()
    await _show_detail(callback, services, callback_data.key)
    await callback.answer("به پیش‌فرض بازگردانده شد.")
