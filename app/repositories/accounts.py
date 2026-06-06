"""Account / sale-request / requested-account repositories."""
from __future__ import annotations

from sqlalchemy import and_, func, select

from app.core.constants import SHOP_VISIBLE_STATUSES, AccountStatus, SaleRequestStatus
from app.models.account import Account, AccountSaleRequest, RequestedAccount
from app.repositories.base import BaseRepository

# Statuses an admin can act on in the sale-account management panel. Sold
# accounts are included so they can be hidden or soft-deleted; DELETED ones are
# excluded (soft-deleted, kept only for sales history).
_MANAGEABLE_STATUSES = (
    AccountStatus.AVAILABLE,
    AccountStatus.LISTED_FOR_SALE,
    AccountStatus.RESERVED,
    AccountStatus.HIDDEN,
    AccountStatus.SOLD,
    AccountStatus.SOLD_TO_ADMIN,
)


class AccountRepository(BaseRepository[Account]):
    model = Account

    async def list_available(
        self,
        *,
        offset: int = 0,
        limit: int = 5,
        min_price: int | None = None,
        max_price: int | None = None,
        query: str | None = None,
    ) -> list[Account]:
        conditions = [Account.status.in_(SHOP_VISIBLE_STATUSES)]
        if min_price is not None:
            conditions.append(Account.price >= min_price)
        if max_price is not None:
            conditions.append(Account.price <= max_price)
        if query:
            conditions.append(Account.title.ilike(f"%{query}%"))
        result = await self.session.execute(
            select(Account)
            .where(and_(*conditions))
            .order_by(Account.id.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def count_available(
        self,
        *,
        min_price: int | None = None,
        max_price: int | None = None,
        query: str | None = None,
    ) -> int:
        conditions = [Account.status.in_(SHOP_VISIBLE_STATUSES)]
        if min_price is not None:
            conditions.append(Account.price >= min_price)
        if max_price is not None:
            conditions.append(Account.price <= max_price)
        if query:
            conditions.append(Account.title.ilike(f"%{query}%"))
        result = await self.session.execute(
            select(func.count()).select_from(Account).where(and_(*conditions))
        )
        return int(result.scalar_one())

    async def list_manageable(
        self, *, offset: int = 0, limit: int = 5
    ) -> list[Account]:
        result = await self.session.execute(
            select(Account)
            .where(Account.status.in_(_MANAGEABLE_STATUSES))
            .order_by(Account.id.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def count_manageable(self) -> int:
        result = await self.session.execute(
            select(func.count())
            .select_from(Account)
            .where(Account.status.in_(_MANAGEABLE_STATUSES))
        )
        return int(result.scalar_one())


class AccountSaleRequestRepository(BaseRepository[AccountSaleRequest]):
    model = AccountSaleRequest

    async def list_pending(self, *, offset: int = 0, limit: int = 10):
        result = await self.session.execute(
            select(AccountSaleRequest)
            .where(AccountSaleRequest.status == SaleRequestStatus.PENDING)
            .order_by(AccountSaleRequest.id.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all())


class RequestedAccountRepository(BaseRepository[RequestedAccount]):
    model = RequestedAccount

    async def list_by_user(self, user_id: int):
        result = await self.session.execute(
            select(RequestedAccount)
            .where(RequestedAccount.user_id == user_id)
            .order_by(RequestedAccount.id.desc())
        )
        return list(result.scalars().all())

    async def list_by_status(
        self, status: SaleRequestStatus, *, offset: int = 0, limit: int = 10
    ):
        result = await self.session.execute(
            select(RequestedAccount)
            .where(RequestedAccount.status == status)
            .order_by(RequestedAccount.id.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def count_by_status(self, status: SaleRequestStatus) -> int:
        result = await self.session.execute(
            select(func.count())
            .select_from(RequestedAccount)
            .where(RequestedAccount.status == status)
        )
        return int(result.scalar_one())
