"""Referral repository."""
from __future__ import annotations

from sqlalchemy import func, select

from app.models.referral import Referral
from app.repositories.base import BaseRepository


class ReferralRepository(BaseRepository[Referral]):
    model = Referral

    async def get_by_referred(self, referred_id: int) -> Referral | None:
        result = await self.session.execute(
            select(Referral).where(Referral.referred_id == referred_id)
        )
        return result.scalar_one_or_none()

    async def list_by_referrer(self, referrer_id: int) -> list[Referral]:
        result = await self.session.execute(
            select(Referral).where(Referral.referrer_id == referrer_id)
        )
        return list(result.scalars().all())

    async def count_by_referrer(self, referrer_id: int) -> int:
        result = await self.session.execute(
            select(func.count())
            .select_from(Referral)
            .where(Referral.referrer_id == referrer_id)
        )
        return int(result.scalar_one())

    async def total_rewarded(self, referrer_id: int) -> int:
        result = await self.session.execute(
            select(func.coalesce(func.sum(Referral.reward_amount), 0)).where(
                Referral.referrer_id == referrer_id, Referral.rewarded.is_(True)
            )
        )
        return int(result.scalar_one())

    async def list_referrers(
        self, *, offset: int = 0, limit: int = 10
    ) -> list[tuple[int, int]]:
        """``(referrer_id, invite_count)`` for everyone with ≥1 invite, busiest first."""
        result = await self.session.execute(
            select(Referral.referrer_id, func.count().label("invites"))
            .group_by(Referral.referrer_id)
            .order_by(func.count().desc(), Referral.referrer_id.asc())
            .offset(offset)
            .limit(limit)
        )
        return [(int(rid), int(cnt)) for rid, cnt in result.all()]

    async def count_referrers(self) -> int:
        """Number of distinct users who have invited at least one person."""
        result = await self.session.execute(
            select(func.count(func.distinct(Referral.referrer_id)))
        )
        return int(result.scalar_one())

    async def list_referred(
        self, referrer_id: int, *, offset: int = 0, limit: int = 10
    ) -> list[Referral]:
        """One referrer's invitee rows, newest first."""
        result = await self.session.execute(
            select(Referral)
            .where(Referral.referrer_id == referrer_id)
            .order_by(Referral.id.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all())
