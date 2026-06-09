"""Typed CallbackData factories (aiogram 3)."""
from __future__ import annotations

from aiogram.filters.callback_data import CallbackData


class MenuCB(CallbackData, prefix="menu"):
    action: str  # e.g. buy_diamond, buy_account, sell_account, wallet, ...


class DiamondCB(CallbackData, prefix="dia"):
    action: str  # method | category | plan
    value: str | None = None  # plan code, "uid"/"account", or "diamond"/"levelup"


class AccountCB(CallbackData, prefix="acc"):
    action: str  # view | buy | page
    account_id: int = 0
    page: int = 1


class NavCB(CallbackData, prefix="nav"):
    action: str  # back | cancel | page
    target: str | None = None
    page: int = 1


class AdminOrderCB(CallbackData, prefix="aord"):
    action: str  # approve | reject | complete | details | open | page
    order_id: int = 0
    page: int = 1
    # Which pending list this row belongs to: "diamond" | "account".
    # Nullable trailing field so an empty segment unpacks cleanly.
    kind: str | None = None


class AdminCB(CallbackData, prefix="adm"):
    action: str
    value: str | None = None
    page: int = 1


class TicketCB(CallbackData, prefix="tk"):
    action: str  # view | reply | close
    ticket_id: int = 0


class PayMethodCB(CallbackData, prefix="pay"):
    method: str  # online | card_to_card


class AdminSaleCB(CallbackData, prefix="asale"):
    action: str  # buy | list
    account_id: int


class DiscountCB(CallbackData, prefix="disc"):
    action: str  # have | skip (user) | view | edit_percent | edit_uses | edit_start | edit_expiry | toggle | delete | confirm_delete | list (admin)
    code_id: int = 0


class BotTextCB(CallbackData, prefix="btxt"):
    action: str  # view | edit | reset | list
    # Nullable so an empty trailing segment (e.g. action="list") unpacks cleanly;
    # aiogram converts an empty last field to None, which a bare ``str`` rejects.
    key: str | None = None


class TutorialCB(CallbackData, prefix="tut"):
    action: str  # view | edit | clear | list (admin) | watch (user)
    key: str | None = None


class ButtonCB(CallbackData, prefix="btn"):
    action: str  # view | edit_text | edit_emoji | color | set_color | toggle | premium | clear_premium | reset | list
    # Nullable trailing fields: aiogram unpacks an empty trailing segment as None,
    # which a bare ``str`` would reject (breaking every callback with empty value).
    key: str | None = None
    value: str | None = None  # color token (primary|success|danger|none) for set_color


class AdminCardCB(CallbackData, prefix="acard"):
    purpose: str  # diamond | account


class AdminAccountCB(CallbackData, prefix="amgr"):
    action: str  # page | view | hide | unhide | delete | confirm_delete | edit_price | edit_title
    account_id: int = 0
    page: int = 1


class AdminRequestedCB(CallbackData, prefix="areq"):
    action: str  # approve_deposit | reject_deposit | page | view | delete | confirm_delete
    req_id: int = 0
    page: int = 1


class ChannelCB(CallbackData, prefix="chlock"):
    action: str  # check (user) | view | toggle | delete | confirm_delete | test (admin)
    channel_id: int = 0


class DepositCB(CallbackData, prefix="dep"):
    action: str  # home | view | edit_amount | edit_card | edit_holder
    # Nullable trailing field: aiogram unpacks an empty trailing segment as None,
    # so a bare ``str`` would reject callbacks that omit the type (e.g. "home").
    dtype: str | None = None  # DepositType value: account_request | account_purchase


class AdminMgmtCB(CallbackData, prefix="admgr"):
    action: str  # home | add | remove | confirm_remove
    user_id: int = 0
