"""User's own order history & support entry."""
from __future__ import annotations

from aiogram import Router
from aiogram.types import Message

from app.container import Services
from app.core.constants import ORDER_STATUS_FA, OrderType
from app.filters.buttons import MainBtn
from app.services.button_service import BTN_KEY_MY_ORDERS
from app.models.user import User
from app.utils.helpers import format_toman

router = Router(name="user_orders")

_TYPE_FA = {
    OrderType.DIAMOND_UID: "جم (UID)",
    OrderType.DIAMOND_ACCOUNT: "جم (اطلاعات اکانت)",
    OrderType.ACCOUNT_PURCHASE: "خرید اکانت",
}


@router.message(MainBtn(BTN_KEY_MY_ORDERS))
async def my_orders(message: Message, services: Services, db_user: User) -> None:
    orders = await services.orders.list_visible_by_user(db_user.id, limit=10)
    if not orders:
        await message.answer("شما هنوز سفارشی ثبت نکرده‌اید. 📦")
        return
    lines = ["📦 <b>سفارش‌های اخیر شما:</b>\n"]
    for o in orders:
        lines.append(
            f"#{o.id} | {_TYPE_FA.get(o.order_type, o.order_type)} | "
            f"{format_toman(o.amount)} | {ORDER_STATUS_FA.get(o.status, o.status)}"
        )
    await message.answer("\n".join(lines))
