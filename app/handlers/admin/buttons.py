"""Admin: full appearance management for the main reply-keyboard buttons.

Per button the admin can set (all DB-backed, no code change needed):
* text;
* emoji — a single unified flow: send a NORMAL emoji and it's shown normally,
  send a PREMIUM (custom) emoji and it's stored as ``icon_custom_emoji_id``
  (Bot API 9.4) and shown as premium; send «حذف» to remove the current emoji.
  Setting one kind clears the other, and there is a dedicated «حذف ایموجی» action;
* color — 🔵 primary / 🟢 success / 🔴 danger (Bot API 9.4 ``style``);
* enabled/disabled (a disabled button is hidden from the main menu).

A premium emoji is validated with ``Bot.get_custom_emoji_stickers`` before saving.
It only renders for users if the bot's owner has Telegram Premium (or the bot
purchased a username on Fragment).
"""
from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
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


def _button_detail_kb(key: str, *, is_enabled: bool):
    kb = InlineKeyboardBuilder()
    kb.button(text="✏️ تغییر متن", callback_data=ButtonCB(action="edit_text", key=key))
    kb.button(text="😀 تغییر ایموجی", callback_data=ButtonCB(action="edit_emoji", key=key))
    kb.button(text="🎨 رنگ دکمه", callback_data=ButtonCB(action="color", key=key))
    toggle_label = "🚫 غیرفعال‌کردن" if is_enabled else "✅ فعال‌کردن"
    kb.button(text=toggle_label, callback_data=ButtonCB(action="toggle", key=key))
    kb.button(text="🧹 حذف ایموجی", callback_data=ButtonCB(action="clear_emoji", key=key))
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
    if ap.custom_emoji_id:
        emoji_fa = f"⭐️ پرمیوم ({ap.emoji_text or 'دارد'})"
    elif ap.emoji:
        emoji_fa = f"{ap.emoji} (عادی)"
    else:
        emoji_fa = "— (بدون ایموجی)"
    return (
        f"🎨 <b>{label}</b>\n\n"
        f"نمایش فعلی: <b>{ap.label}</b>\n"
        f"ایموجی: {emoji_fa}\n"
        f"رنگ: {color_fa}\n"
        f"وضعیت: {enabled_fa}\n\n"
        "یکی از گزینه‌های زیر را انتخاب کنید:"
    )


async def _show_detail(callback: CallbackQuery, services: Services, key: str) -> None:
    ap = await services.button.appearance(key)
    await edit_or_answer(
        callback.message,
        await _detail_text(services, key),
        reply_markup=_button_detail_kb(key, is_enabled=ap.is_enabled),
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


# ----------------------------- EMOJI (normal + premium, unified) -----------------------------
@router.callback_query(ButtonCB.filter(F.action == "edit_emoji"), IsAdmin())
async def button_edit_emoji_start(
    callback: CallbackQuery, callback_data: ButtonCB, state: FSMContext
) -> None:
    label = BUTTON_LABELS.get(callback_data.key, callback_data.key)
    await state.set_state(ButtonEditFlow.entering_emoji)
    await state.update_data(button_key=callback_data.key)
    await edit_or_answer(
        callback.message,
        f"😀 برای دکمه «{label}» یک ایموجی بفرستید:\n\n"
        "• ایموجی <b>عادی</b> ← عادی نمایش داده می‌شود.\n"
        "• ایموجی <b>پرمیوم</b> (Custom Emoji) ← پرمیوم نمایش داده می‌شود "
        "(نیازمند اشتراک پرمیوم مالک ربات).\n"
        "• برای <b>حذف</b> ایموجی فعلی، کلمهٔ «حذف» را بفرستید.",
        reply_markup=cancel_only(),
    )
    await callback.answer()


@router.message(ButtonEditFlow.entering_emoji, IsAdmin())
async def button_edit_emoji_save(
    message: Message, services: Services, state: FSMContext, bot: Bot
) -> None:
    """Unified emoji setter: normal OR premium (auto-detected), plus «حذف».

    A premium (custom) emoji is detected via a ``custom_emoji`` entity and stored
    as ``icon_custom_emoji_id`` (validated first). Anything else is treated as a
    plain emoji. Setting one kind clears the other so only the chosen emoji shows.
    """
    data = await state.get_data()
    key = data.get("button_key")
    if not key:
        await state.clear()
        await message.answer("خطا: کلید دکمه یافت نشد.")
        return
    label = BUTTON_LABELS.get(key, key)
    source = message.text or message.caption or ""

    # «حذف» — remove the current emoji entirely (both normal and premium).
    if source.strip() == "حذف":
        await services.button.set_emoji(key, "")
        await services.button.clear_premium_emoji(key)
        await services.commit()
        await state.clear()
        await message.answer(
            f"✅ ایموجی دکمه «{label}» حذف شد.\nبرای اعمال، دستور /start را بزنید."
        )
        return

    # Detect a premium (custom) emoji in the text or caption entities.
    entities = list(message.entities or []) + list(message.caption_entities or [])
    custom_emoji_id = None
    emoji_text = source.strip()
    for ent in entities:
        if ent.type == "custom_emoji" and ent.custom_emoji_id:
            custom_emoji_id = ent.custom_emoji_id
            emoji_text = source[ent.offset : ent.offset + ent.length] or emoji_text
            break

    if custom_emoji_id:
        # Validate the bot can actually USE this custom emoji before storing it,
        # otherwise it would never render on the button.
        try:
            stickers = await bot.get_custom_emoji_stickers(
                custom_emoji_ids=[custom_emoji_id]
            )
        except TelegramBadRequest:
            stickers = []
        if not stickers:
            await message.answer(
                "❌ این ایموجی پرمیوم برای ربات قابل استفاده نیست و ذخیره نشد.\n\n"
                "نمایش ایموجی پرمیوم نیازمند آن است که <b>مالک ربات</b> اشتراک تلگرام "
                "پرمیوم داشته باشد (یا یوزرنیم ربات از Fragment خریداری شده باشد). "
                "یک ایموجی دیگر امتحان کنید یا «حذف» را بفرستید."
            )
            return
        # Premium replaces any normal emoji so the button shows only the premium one.
        await services.button.set_premium_emoji(key, custom_emoji_id, emoji_text or None)
        await services.button.set_emoji(key, "")
        await services.commit()
        await state.clear()
        await message.answer(
            f"✅ ایموجی <b>پرمیوم</b> برای دکمه «{label}» تنظیم و اعتبارسنجی شد.\n\n"
            "برای اعمال در منوی اصلی، دستور /start را بزنید."
        )
        return

    # Plain (normal) emoji — replaces any premium emoji.
    normal = source.strip()
    if not normal:
        await message.answer(
            "❌ ایموجی نامعتبر. یک ایموجی (عادی یا پرمیوم) بفرستید یا «حذف» را ارسال کنید."
        )
        return
    await services.button.set_emoji(key, normal)
    await services.button.clear_premium_emoji(key)
    await services.commit()
    await state.clear()
    current = await services.button.label(key)
    await message.answer(
        f"✅ ایموجی <b>عادی</b> دکمه «{label}» به‌روزرسانی شد.\nنمایش جدید: <b>{current}</b>"
        "\n\nبرای اعمال در منوی اصلی، دستور /start را بزنید."
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


# --------------------------- CLEAR EMOJI ---------------------------
@router.callback_query(ButtonCB.filter(F.action == "clear_emoji"), IsAdmin())
async def button_clear_emoji(
    callback: CallbackQuery, callback_data: ButtonCB, services: Services
) -> None:
    """Remove the current emoji (normal and/or premium) from the button."""
    await services.button.set_emoji(callback_data.key, "")
    await services.button.clear_premium_emoji(callback_data.key)
    await services.commit()
    await _show_detail(callback, services, callback_data.key)
    await callback.answer("ایموجی حذف شد.")


# ----------------------------- RESET -----------------------------
@router.callback_query(ButtonCB.filter(F.action == "reset"), IsAdmin())
async def button_reset(
    callback: CallbackQuery, callback_data: ButtonCB, services: Services
) -> None:
    await services.button.reset(callback_data.key)
    await services.commit()
    await _show_detail(callback, services, callback_data.key)
    await callback.answer("به پیش‌فرض بازگردانده شد.")
