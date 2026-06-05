"""Typed CallbackData factories (aiogram 3)."""
from __future__ import annotations

from aiogram.filters.callback_data import CallbackData


class MenuCB(CallbackData, prefix="menu"):
    action: str  # e.g. buy_diamond, buy_account, sell_account, wallet, ...


class DiamondCB(CallbackData, prefix="dia"):
    action: str  # method | plan
    value: str | None = None  # plan code or "uid"/"account"


class AccountCB(CallbackData, prefix="acc"):
    action: str  # view | buy | page
    account_id: int = 0
    page: int = 1


class NavCB(CallbackData, prefix="nav"):
    action: str  # back | cancel | page
    target: str | None = None
    page: int = 1


class LoginMethodCB(CallbackData, prefix="login"):
    method: str


class AdminOrderCB(CallbackData, prefix="aord"):
    action: str  # approve | reject | complete | view
    order_id: int


class AdminCB(CallbackData, prefix="adm"):
    action: str
    value: str | None = None
    page: int = 1


class TicketCB(CallbackData, prefix="tk"):
    action: str  # view | reply | close
    ticket_id: int = 0
