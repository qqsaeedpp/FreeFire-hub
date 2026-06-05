"""FSM state groups for admin flows."""
from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class AddAccountFlow(StatesGroup):
    title = State()
    price = State()
    level = State()
    skins = State()
    elite = State()
    gun_skins = State()
    description = State()
    images = State()
    credentials = State()


class EditDiamondPrice(StatesGroup):
    choosing_plan = State()
    entering_price = State()


class BroadcastFlow(StatesGroup):
    entering_message = State()
    confirming = State()


class AdminReplyFlow(StatesGroup):
    entering_reply = State()


class WalletAdjustFlow(StatesGroup):
    entering_user = State()
    entering_amount = State()


class RejectReasonFlow(StatesGroup):
    entering_reason = State()
