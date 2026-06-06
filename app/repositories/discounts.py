"""Discount-code repository."""
from __future__ import annotations

from sqlalchemy import select

from app.models.discount import DiscountCode
from app.repositories.base import BaseRepository


class DiscountCodeRepository(BaseRepository[DiscountCode]):
    model = DiscountCode

    async def get_by_code(self, code: str) -> DiscountCode | None:
        result = await self.session.execute(
            select(DiscountCode).where(DiscountCode.code == code)
        )
        return result.scalar_one_or_none()

    async def list_all(self, *, offset: int = 0, limit: int = 20) -> list[DiscountCode]:
        result = await self.session.execute(
            select(DiscountCode)
            .order_by(DiscountCode.id.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all())
