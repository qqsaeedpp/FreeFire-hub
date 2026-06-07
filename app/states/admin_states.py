"""FSM state groups for admin flows."""
from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


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


class CardFlow(StatesGroup):
    """Set the card-to-card destination for a sales channel."""

    entering_number = State()
    entering_holder = State()


class DiscountCreateFlow(StatesGroup):
    entering_code = State()
    entering_percent = State()
    entering_max_uses = State()
    entering_days = State()


class LotteryFlow(StatesGroup):
    entering_winner_count = State()


class AccountEditFlow(StatesGroup):
    entering_price = State()
    entering_title = State()


class DiscountEditFlow(StatesGroup):
    """Edit a single field of an existing discount code."""

    entering_percent = State()
    entering_max_uses = State()
    entering_start_days = State()
    entering_expiry_days = State()


class BotTextEditFlow(StatesGroup):
    """Capture a replacement for an admin-editable bot text (with entities)."""

    entering_text = State()


class TutorialMediaFlow(StatesGroup):
    """Capture a replacement video for an admin-managed tutorial."""

    awaiting_video = State()


class ButtonEditFlow(StatesGroup):
    """Capture a new text / emoji (normal or premium) for an editable main button."""

    entering_text = State()
    entering_emoji = State()
