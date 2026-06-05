"""Router aggregation — registers every feature router on the dispatcher."""
from __future__ import annotations

from aiogram import Dispatcher

from app.handlers.admin import accounts as admin_accounts
from app.handlers.admin import broadcast as admin_broadcast
from app.handlers.admin import orders as admin_orders
from app.handlers.admin import panel as admin_panel
from app.handlers.support import tickets as support_tickets
from app.handlers.user import account as user_account
from app.handlers.user import common as user_common
from app.handlers.user import diamond as user_diamond
from app.handlers.user import orders as user_orders
from app.handlers.user import referral as user_referral
from app.handlers.user import sell as user_sell
from app.handlers.user import wallet as user_wallet


def register_routers(dp: Dispatcher) -> None:
    # Admin first so admin-only filters take precedence.
    dp.include_router(admin_panel.router)
    dp.include_router(admin_orders.router)
    dp.include_router(admin_accounts.router)
    dp.include_router(admin_broadcast.router)

    dp.include_router(support_tickets.router)

    dp.include_router(user_common.router)
    dp.include_router(user_diamond.router)
    dp.include_router(user_account.router)
    dp.include_router(user_sell.router)
    dp.include_router(user_wallet.router)
    dp.include_router(user_referral.router)
    dp.include_router(user_orders.router)
