"""Support tickets — user creates/follows-up, admin replies/closes."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.container import Services
from app.core.config import settings
from app.core.constants import TICKET_STATUS_FA
from app.filters.admin import IsAdmin
from app.keyboards.callbacks import TicketCB
from app.keyboards.inline import cancel_only, ticket_actions
from app.keyboards.reply import BTN_SUPPORT, main_menu
from app.models.user import User
from app.services.notification_service import NotificationService
from app.states.admin_states import AdminReplyFlow
from app.states.user_states import TicketFlow

router = Router(name="support_tickets")


# ----------------------------- USER SIDE -----------------------------
@router.message(F.text == BTN_SUPPORT)
async def support_home(message: Message, services: Services, db_user: User) -> None:
    tickets = await services.ticket.tickets.list_by_user(db_user.id)
    lines = ["🎧 <b>پشتیبانی</b>\n"]
    if tickets:
        lines.append("تیکت‌های شما:")
        for t in tickets:
            lines.append(f"#{t.id} | {t.subject} | {TICKET_STATUS_FA.get(t.status, t.status)}")
        lines.append("")
    lines.append("برای ثبت تیکت جدید دستور /newticket را بزنید.")
    await message.answer("\n".join(lines))


@router.message(F.text == "/newticket")
async def new_ticket(message: Message, state: FSMContext) -> None:
    await state.set_state(TicketFlow.entering_subject)
    await message.answer("📝 موضوع تیکت را وارد کنید:", reply_markup=cancel_only())


@router.message(TicketFlow.entering_subject, F.text)
async def ticket_subject(message: Message, state: FSMContext) -> None:
    await state.update_data(subject=message.text.strip()[:255])
    await state.set_state(TicketFlow.entering_message)
    await message.answer(
        "💬 پیام خود را بنویسید. می‌توانید عکس یا فایل هم پیوست کنید:",
        reply_markup=cancel_only(),
    )


@router.message(TicketFlow.entering_message)
async def ticket_message(
    message: Message, services: Services, state: FSMContext, db_user: User, bot
) -> None:
    data = await state.get_data()
    text, file_id, file_type = _extract_content(message)
    if not text and not file_id:
        await message.answer("لطفاً متن، عکس یا فایل ارسال کنید.")
        return
    ticket = await services.ticket.create(
        db_user.id, data["subject"], text=text, file_id=file_id, file_type=file_type
    )
    await services.commit()
    await message.answer(
        f"✅ تیکت شما با شماره #{ticket.id} ثبت شد. پشتیبانی به‌زودی پاسخ می‌دهد.",
        reply_markup=main_menu(db_user.is_admin),
    )
    notifier = NotificationService(bot)
    await notifier.notify_admin(
        f"🎧 <b>تیکت جدید</b> #{ticket.id}\n"
        f"موضوع: {data['subject']}\n"
        f"کاربر: <code>{db_user.telegram_id}</code>\n"
        f"پیام: {text or '[فایل]'}",
        reply_markup=ticket_actions(ticket.id, is_admin=True),
    )
    await notifier.log_event(
        "ثبت تیکت", {"تیکت": f"#{ticket.id}", "کاربر": str(db_user.telegram_id)}
    )
    await state.clear()


# ----------------------------- ADMIN SIDE -----------------------------
@router.callback_query(TicketCB.filter(F.action == "reply"), IsAdmin())
async def admin_reply_start(
    callback: CallbackQuery, callback_data: TicketCB, state: FSMContext
) -> None:
    await state.set_state(AdminReplyFlow.entering_reply)
    await state.update_data(ticket_id=callback_data.ticket_id)
    await callback.message.answer(
        f"💬 پاسخ خود به تیکت #{callback_data.ticket_id} را بنویسید:",
        reply_markup=cancel_only(),
    )
    await callback.answer()


@router.message(AdminReplyFlow.entering_reply)
async def admin_reply_send(
    message: Message, services: Services, state: FSMContext, bot
) -> None:
    data = await state.get_data()
    ticket = await services.ticket.get_with_messages(data["ticket_id"])
    if ticket is None:
        await message.answer("تیکت یافت نشد.")
        await state.clear()
        return
    text, file_id, file_type = _extract_content(message)
    await services.ticket.add_admin_reply(
        ticket, text=text, file_id=file_id, file_type=file_type
    )
    await services.commit()

    owner = await services.users.get(ticket.user_id)
    if owner:
        notifier = NotificationService(bot)
        await notifier.notify_user(
            owner.telegram_id,
            f"💬 <b>پاسخ پشتیبانی به تیکت #{ticket.id}</b>\n\n{text or ''}",
        )
        if file_id and file_type == "photo":
            await bot.send_photo(owner.telegram_id, file_id)
        elif file_id:
            await bot.send_document(owner.telegram_id, file_id)
    await message.answer("✅ پاسخ ارسال شد.")
    await state.clear()


@router.callback_query(TicketCB.filter(F.action == "close"), IsAdmin())
async def admin_close(
    callback: CallbackQuery, callback_data: TicketCB, services: Services, bot
) -> None:
    ticket = await services.ticket.get_with_messages(callback_data.ticket_id)
    if ticket is None:
        await callback.answer("تیکت یافت نشد.", show_alert=True)
        return
    await services.ticket.close(ticket)
    await services.commit()
    owner = await services.users.get(ticket.user_id)
    if owner:
        await NotificationService(bot).notify_user(
            owner.telegram_id, f"🔒 تیکت #{ticket.id} شما بسته شد."
        )
    await callback.answer("تیکت بسته شد.")
    await callback.message.edit_reply_markup(reply_markup=None)


def _extract_content(message: Message) -> tuple[str | None, str | None, str | None]:
    if message.photo:
        return message.caption, message.photo[-1].file_id, "photo"
    if message.document:
        return message.caption, message.document.file_id, "document"
    return message.text, None, None
