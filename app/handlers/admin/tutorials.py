"""Admin: manage tutorial videos (file_id stored in DB, re-sent to users).

Tutorials are listed as inline buttons; selecting one shows its current video
(if any) and offers 🎬 replace / 🗑 clear. When the admin sends a video, its
``file_id`` is captured and stored so the exact same video can be re-sent to
users on demand — no code change required to swap a tutorial.
"""
from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.container import Services
from app.filters.admin import IsAdmin
from app.keyboards.callbacks import AdminCB, TutorialCB
from app.keyboards.inline import cancel_only
from app.services.tutorial_service import TUTORIAL_LABELS
from app.states.admin_states import TutorialMediaFlow
from app.utils.helpers import edit_or_answer

router = Router(name="admin_tutorials")


def _tutorials_list_kb():
    kb = InlineKeyboardBuilder()
    for key, label in TUTORIAL_LABELS.items():
        kb.button(text=label, callback_data=TutorialCB(action="view", key=key))
    kb.button(text="🔙 بازگشت", callback_data=AdminCB(action="back_home"))
    kb.adjust(1)
    return kb.as_markup()


def _tutorial_detail_kb(key: str, has_video: bool):
    kb = InlineKeyboardBuilder()
    kb.button(text="🎬 آپلود/جایگزینی ویدیو", callback_data=TutorialCB(action="edit", key=key))
    if has_video:
        kb.button(text="🗑 حذف ویدیو", callback_data=TutorialCB(action="clear", key=key))
    kb.button(text="🔙 بازگشت", callback_data=TutorialCB(action="list"))
    kb.adjust(1)
    return kb.as_markup()


async def _show_list(message, state: FSMContext) -> None:
    await state.clear()
    await edit_or_answer(
        message,
        "🎥 <b>مدیریت ویدیوهای آموزشی</b>\nویدیوی موردنظر را برای مدیریت انتخاب کنید:",
        reply_markup=_tutorials_list_kb(),
    )


@router.callback_query(AdminCB.filter(F.action == "tutorials"), IsAdmin())
async def tutorials_home(callback: CallbackQuery, state: FSMContext) -> None:
    await _show_list(callback.message, state)
    await callback.answer()


@router.callback_query(TutorialCB.filter(F.action == "list"), IsAdmin())
async def tutorials_list(callback: CallbackQuery, state: FSMContext) -> None:
    await _show_list(callback.message, state)
    await callback.answer()


@router.callback_query(TutorialCB.filter(F.action == "view"), IsAdmin())
async def tutorial_view(
    callback: CallbackQuery, callback_data: TutorialCB, services: Services
) -> None:
    key = callback_data.key
    label = TUTORIAL_LABELS.get(key, key)
    file_id = await services.tutorial.get_file_id(key)
    status = "✅ ویدیو ثبت شده است." if file_id else "⚠️ هنوز ویدیویی ثبت نشده است."
    await edit_or_answer(
        callback.message,
        f"🎥 <b>{label}</b>\n\n{status}",
        reply_markup=_tutorial_detail_kb(key, bool(file_id)),
    )
    if file_id:
        try:
            await callback.message.answer_video(
                file_id, caption=f"🎬 ویدیوی فعلی: {label}"
            )
        except Exception:  # noqa: BLE001 - file_id may be stale
            await callback.message.answer(
                "⚠️ ارسال ویدیوی ذخیره‌شده ناموفق بود؛ لطفاً دوباره آپلود کنید."
            )
    await callback.answer()


@router.callback_query(TutorialCB.filter(F.action == "edit"), IsAdmin())
async def tutorial_edit_start(
    callback: CallbackQuery, callback_data: TutorialCB, state: FSMContext
) -> None:
    label = TUTORIAL_LABELS.get(callback_data.key, callback_data.key)
    await state.set_state(TutorialMediaFlow.awaiting_video)
    await state.update_data(tutorial_key=callback_data.key)
    await edit_or_answer(
        callback.message,
        f"🎬 ویدیوی جدید «{label}» را همینجا ارسال کنید (به‌صورت ویدیو).",
        reply_markup=cancel_only(),
    )
    await callback.answer()


@router.callback_query(TutorialCB.filter(F.action == "clear"), IsAdmin())
async def tutorial_clear(
    callback: CallbackQuery, callback_data: TutorialCB, services: Services
) -> None:
    key = callback_data.key
    label = TUTORIAL_LABELS.get(key, key)
    await services.tutorial.clear(key)
    await services.commit()
    await edit_or_answer(
        callback.message,
        f"🗑 ویدیوی «{label}» حذف شد.",
        reply_markup=_tutorial_detail_kb(key, has_video=False),
    )
    await callback.answer("حذف شد.")


def _extract_file_id(message: Message) -> str | None:
    """Accept either a real video or a video sent as a document."""
    if message.video:
        return message.video.file_id
    if message.document:
        return message.document.file_id
    return None


@router.message(TutorialMediaFlow.awaiting_video, IsAdmin())
async def tutorial_save_video(
    message: Message, services: Services, state: FSMContext
) -> None:
    file_id = _extract_file_id(message)
    if not file_id:
        await message.answer("لطفاً یک ویدیو ارسال کنید.")
        return
    data = await state.get_data()
    key = data.get("tutorial_key")
    if not key:
        await state.clear()
        await message.answer("خطا: کلید ویدیو یافت نشد.")
        return
    await services.tutorial.set_file_id(key, file_id)
    await services.commit()
    await state.clear()
    label = TUTORIAL_LABELS.get(key, key)
    await message.answer(
        f"✅ ویدیوی «{label}» ذخیره شد و از این پس به کاربران نمایش داده می‌شود.",
        reply_markup=_tutorials_list_kb(),
    )
