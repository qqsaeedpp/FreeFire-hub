"""Account service — shop catalog, reservations, sale requests, requested accounts."""
from __future__ import annotations

from app.core.config import settings
from app.core.constants import AccountStatus, OrderType
from app.core.security import decrypt, encrypt
from app.models.account import Account, AccountSaleRequest, RequestedAccount
from app.models.order import AccountOrder
from app.repositories.accounts import (
    AccountRepository,
    AccountSaleRequestRepository,
    RequestedAccountRepository,
)
from app.repositories.orders import OrderRepository


class AccountReservationError(Exception):
    """Raised when an account can no longer be reserved (already taken)."""


class AccountService:
    def __init__(
        self,
        accounts: AccountRepository,
        sale_requests: AccountSaleRequestRepository,
        requested: RequestedAccountRepository,
        orders: OrderRepository,
    ) -> None:
        self.accounts = accounts
        self.sale_requests = sale_requests
        self.requested = requested
        self.orders = orders

    # ---- shop browsing ----
    async def list_available(self, *, page: int, page_size: int, **filters):
        offset = (page - 1) * page_size
        items = await self.accounts.list_available(
            offset=offset, limit=page_size, **filters
        )
        total = await self.accounts.count_available(**filters)
        return items, total

    async def get(self, account_id: int) -> Account | None:
        return await self.accounts.get(account_id)

    # ---- admin: create a listing ----
    async def create_listing(self, *, credentials: str | None = None, **fields) -> Account:
        account = Account(**fields)
        if credentials:
            account.credentials = encrypt(credentials)
        return await self.accounts.add(account)

    # ---- purchase flow ----
    async def reserve(self, account_id: int, buyer_user_id: int) -> Account:
        account = await self.accounts.get(account_id)
        if account is None or account.status != AccountStatus.AVAILABLE:
            raise AccountReservationError
        account.status = AccountStatus.RESERVED
        account.reserved_by_id = buyer_user_id
        return account

    async def release(self, account: Account) -> None:
        if account.status == AccountStatus.RESERVED:
            account.status = AccountStatus.AVAILABLE
            account.reserved_by_id = None

    async def create_purchase_order(
        self, user_id: int, account: Account
    ) -> AccountOrder:
        order = AccountOrder(
            user_id=user_id,
            order_type=OrderType.ACCOUNT_PURCHASE,
            amount=account.price,
            account_id=account.id,
        )
        return await self.orders.add(order)

    async def deliver(self, account: Account, order: AccountOrder) -> str:
        """Mark account sold and return its plaintext credentials for delivery."""
        account.status = AccountStatus.SOLD
        creds = decrypt(account.credentials or "")
        order.delivered_credentials = account.credentials
        return creds

    # ---- user sells an account to the shop ----
    async def create_sale_request(self, user_id: int, **fields) -> AccountSaleRequest:
        req = AccountSaleRequest(user_id=user_id, **fields)
        return await self.sale_requests.add(req)

    # ---- user requests the shop to find an account ----
    async def create_requested_account(self, user_id: int, **fields) -> RequestedAccount:
        req = RequestedAccount(
            user_id=user_id,
            deposit_amount=settings.requested_account_deposit,
            **fields,
        )
        return await self.requested.add(req)
