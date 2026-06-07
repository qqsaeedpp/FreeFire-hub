"""FSM state groups for user-facing flows."""
from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class DiamondFlow(StatesGroup):
    """Shared first steps of the diamond purchase.

    Old order (amount → method) is restored to the original (method first):
    pick the purchase method, then — for UID — pick a category (جم / لول اپ),
    and finally a concrete plan.
    """

    choosing_method = State()
    choosing_category = State()
    choosing_plan = State()


class DiamondUIDFlow(StatesGroup):
    choosing_plan = State()
    entering_uid = State()
    awaiting_receipt = State()


class DiamondAccountFlow(StatesGroup):
    choosing_plan = State()
    entering_email = State()          # ایمیل اکانت
    entering_gmail_password = State()  # رمز عبور جیمیل
    entering_backup = State()          # کد بکاپ
    awaiting_receipt = State()


class AccountPurchaseFlow(StatesGroup):
    browsing = State()
    confirming = State()
    awaiting_receipt = State()


class AccountFormFlow(StatesGroup):
    """Unified account-listing form, shared by the admin 'add account' entry and
    the user 'sell account' entry. ``mode`` in the FSM data is 'admin' or 'user'.

    Simplified: all account specs (level/elite/skins/guns/…) are written by the
    seller inside the free-text ``description`` step.
    """

    title = State()
    price = State()
    description = State()
    images = State()
    save_info = State()
    login_info = State()


class DiscountFlow(StatesGroup):
    """Optional 'do you have a discount code?' step before diamond payment."""

    deciding = State()
    entering_code = State()


class PaymentFlow(StatesGroup):
    """Generic 'choose a payment method' step inserted before payment details."""

    choosing_method = State()


class RequestedAccountFlow(StatesGroup):
    """Simplified: the requester writes all wanted specs (elite/sets/guns/level/…)
    inside the free-text ``description`` step."""

    entering_price = State()
    entering_description = State()
    awaiting_deposit_receipt = State()


class TicketFlow(StatesGroup):
    entering_subject = State()
    entering_message = State()
    replying = State()  # appending a follow-up message to an existing ticket


class WalletFlow(StatesGroup):
    entering_topup_amount = State()
    awaiting_topup_receipt = State()
