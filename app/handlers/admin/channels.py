"""Admin: «📢 مدیریت کانال‌ها» hub.

Groups the two channel features behind one panel button:

* 🔒 تنظیم کانال قفل — forced-membership channels (``channel_lock`` handlers);
* 📣 کانال‌های تبلیغ — channels every new listing is mirrored into
  (``ad_channels`` handlers).
"""
from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.filters.admin import IsAdmin
from app.keyboards.callbacks import AdminCB
from app.utils.helpers import edit_or_answer

router = Router(name="admin_channels")

HUB_TEXT = (
    "📢 <b>مدیریت کانال‌ها</b>\n\n"
    "🔒 <b>تنظیم کانال قفل:</b> کانال‌هایی که کاربر برای استفاده از ربات "
    "باید عضوشان باشد.\n"
    "📣 <b>کانال‌های تبلیغ:</b> هر آگهی اکانت جدید درجا در این کانال‌ها هم "
    "منتشر می‌شود.\n\n"
    "یک گزینه را انتخاب کنید:"
)


def channels_menu() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🔒 تنظیم کانال قفل", callback_data=AdminCB(action="channel_lock"))
    kb.button(text="📣 کانال‌های تبلیغ", callback_data=AdminCB(action="ad_channels"))
    kb.button(text="🔙 بازگشت", callback_data=AdminCB(action="back_home"))
    kb.adjust(1)
    return kb.as_markup()


@router.callback_query(AdminCB.filter(F.action == "channels"), IsAdmin())
async def channels_home(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await edit_or_answer(callback.message, HUB_TEXT, reply_markup=channels_menu())
    await callback.answer()
