"""FSM state groups for user-facing flows."""
from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class DiamondUIDFlow(StatesGroup):
    choosing_plan = State()
    entering_uid = State()
    awaiting_receipt = State()


class DiamondAccountFlow(StatesGroup):
    choosing_plan = State()
    entering_email = State()
    entering_password = State()
    entering_backup = State()
    choosing_login_method = State()
    awaiting_receipt = State()


class AccountPurchaseFlow(StatesGroup):
    browsing = State()
    confirming = State()
    awaiting_receipt = State()


class SellAccountFlow(StatesGroup):
    entering_price = State()
    entering_elite = State()
    entering_skins = State()
    entering_description = State()
    sending_images = State()


class RequestedAccountFlow(StatesGroup):
    entering_price = State()
    entering_elite = State()
    entering_sets = State()
    entering_guns = State()
    entering_description = State()
    awaiting_deposit_receipt = State()


class TicketFlow(StatesGroup):
    entering_subject = State()
    entering_message = State()
    replying = State()  # appending a follow-up message to an existing ticket


class WalletFlow(StatesGroup):
    entering_topup_amount = State()
    awaiting_topup_receipt = State()
