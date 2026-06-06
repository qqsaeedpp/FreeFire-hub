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


class AccountFormFlow(StatesGroup):
    """Unified account-listing form, shared by the admin 'add account' entry and
    the user 'sell account' entry. ``mode`` in the FSM data is 'admin' or 'user'."""

    title = State()
    price = State()
    level = State()
    elite = State()
    skins = State()
    gun_skins = State()
    description = State()
    images = State()
    save_info = State()
    login_info = State()
    special_items = State()


class DiscountFlow(StatesGroup):
    """Optional 'do you have a discount code?' step before diamond payment."""

    deciding = State()
    entering_code = State()


class PaymentFlow(StatesGroup):
    """Generic 'choose a payment method' step inserted before payment details."""

    choosing_method = State()


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
