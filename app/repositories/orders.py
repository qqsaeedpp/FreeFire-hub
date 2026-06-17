"""Order repository (works across polymorphic Order subtypes)."""
from __future__ import annotations

from sqlalchemy import func, select

from collections.abc import Sequence

from app.core.constants import OrderStatus, OrderType
from app.models.order import AccountOrder, DiamondOrder, Order
from app.repositories.base import BaseRepository


class OrderRepository(BaseRepository[Order]):
    model = Order

    async def list_by_user(
        self, user_id: int, *, offset: int = 0, limit: int = 10
    ) -> list[Order]:
        result = await self.session.execute(
            select(Order)
            .where(Order.user_id == user_id)
            .order_by(Order.id.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_visible_by_user(
        self, user_id: int, *, offset: int = 0, limit: int = 10
    ) -> list[Order]:
        """Orders a user should see in «my orders» — excludes drafts (PENDING,
        i.e. created but never paid/submitted) and cancelled orders."""
        result = await self.session.execute(
            select(Order)
            .where(
                Order.user_id == user_id,
                Order.status.notin_(
                    (OrderStatus.PENDING, OrderStatus.CANCELLED)
                ),
            )
            .order_by(Order.id.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_by_status(
        self, status: OrderStatus, *, offset: int = 0, limit: int = 10
    ) -> list[Order]:
        result = await self.session.execute(
            select(Order)
            .where(Order.status == status)
            .order_by(Order.id.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_by_status_and_types(
        self,
        status: OrderStatus,
        types: Sequence[OrderType],
        *,
        offset: int = 0,
        limit: int = 10,
    ) -> list[Order]:
        result = await self.session.execute(
            select(Order)
            .where(Order.status == status, Order.order_type.in_(tuple(types)))
            .order_by(Order.id.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def count_by_status_and_types(
        self, status: OrderStatus, types: Sequence[OrderType]
    ) -> int:
        result = await self.session.execute(
            select(func.count())
            .select_from(Order)
            .where(Order.status == status, Order.order_type.in_(tuple(types)))
        )
        return int(result.scalar_one())

    async def get_diamond(self, order_id: int) -> DiamondOrder | None:
        return await self.session.get(DiamondOrder, order_id)

    async def get_account_order(self, order_id: int) -> AccountOrder | None:
        return await self.session.get(AccountOrder, order_id)

    async def revenue(self) -> int:
        result = await self.session.execute(
            select(func.coalesce(func.sum(Order.amount), 0)).where(
                Order.status == OrderStatus.COMPLETED
            )
        )
        return int(result.scalar_one())

    async def count_by_status(self, status: OrderStatus) -> int:
        result = await self.session.execute(
            select(func.count()).select_from(Order).where(Order.status == status)
        )
        return int(result.scalar_one())

    # ---- per-user aggregates (for the admin user-info card) ----
    async def count_placed_by_user(self, user_id: int) -> int:
        """Orders a user actually submitted — excludes never-paid PENDING drafts."""
        result = await self.session.execute(
            select(func.count())
            .select_from(Order)
            .where(Order.user_id == user_id, Order.status != OrderStatus.PENDING)
        )
        return int(result.scalar_one())

    async def count_completed_by_user(self, user_id: int) -> int:
        result = await self.session.execute(
            select(func.count())
            .select_from(Order)
            .where(Order.user_id == user_id, Order.status == OrderStatus.COMPLETED)
        )
        return int(result.scalar_one())

    async def total_paid_by_user(self, user_id: int) -> int:
        """Sum (Toman) of the user's completed-order amounts."""
        result = await self.session.execute(
            select(func.coalesce(func.sum(Order.amount), 0)).where(
                Order.user_id == user_id, Order.status == OrderStatus.COMPLETED
            )
        )
        return int(result.scalar_one())
