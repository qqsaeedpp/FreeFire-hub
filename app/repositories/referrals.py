"""Referral repository."""
from __future__ import annotations

from sqlalchemy import func, select, update

from app.models.referral import Referral
from app.repositories.base import BaseRepository


class ReferralRepository(BaseRepository[Referral]):
    model = Referral

    async def get_by_referred(self, referred_id: int) -> Referral | None:
        # Deliberately unfiltered by ``counted`` — the double-reward guard must see
        # every relation row (a reset zeroes stats but must NOT re-open rewards).
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
            .where(Referral.referrer_id == referrer_id, Referral.counted.is_(True))
        )
        return int(result.scalar_one())

    async def total_rewarded(self, referrer_id: int) -> int:
        result = await self.session.execute(
            select(func.coalesce(func.sum(Referral.reward_amount), 0)).where(
                Referral.referrer_id == referrer_id,
                Referral.rewarded.is_(True),
                Referral.counted.is_(True),
            )
        )
        return int(result.scalar_one())

    async def list_referrers(
        self, *, offset: int = 0, limit: int = 10
    ) -> list[tuple[int, int]]:
        """``(referrer_id, invite_count)`` for everyone with ≥1 invite, busiest first."""
        result = await self.session.execute(
            select(Referral.referrer_id, func.count().label("invites"))
            .where(Referral.counted.is_(True))
            .group_by(Referral.referrer_id)
            .order_by(func.count().desc(), Referral.referrer_id.asc())
            .offset(offset)
            .limit(limit)
        )
        return [(int(rid), int(cnt)) for rid, cnt in result.all()]

    async def count_referrers(self) -> int:
        """Number of distinct users who have invited at least one person."""
        result = await self.session.execute(
            select(func.count(func.distinct(Referral.referrer_id))).where(
                Referral.counted.is_(True)
            )
        )
        return int(result.scalar_one())

    async def list_referred(
        self, referrer_id: int, *, offset: int = 0, limit: int = 10
    ) -> list[Referral]:
        """One referrer's invitee rows, newest first."""
        result = await self.session.execute(
            select(Referral)
            .where(Referral.referrer_id == referrer_id, Referral.counted.is_(True))
            .order_by(Referral.id.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all())

    # ---- stats reset (relations preserved) ----
    async def reset_counts_for_referrer(self, referrer_id: int) -> int:
        """Zero one referrer's *stats* by flipping their rows to ``counted=False``.

        No row is deleted, so the invite relations and the double-reward guard
        (:meth:`get_by_referred`) keep working. Returns how many rows were reset.
        """
        result = await self.session.execute(
            update(Referral)
            .where(Referral.referrer_id == referrer_id, Referral.counted.is_(True))
            .values(counted=False)
        )
        return int(result.rowcount or 0)

    async def reset_all_counts(self) -> int:
        """Global stats reset: flip every still-counted row to ``counted=False``.

        Deletes nothing — only the displayed counters/sums go to zero. Returns how
        many rows were reset.
        """
        result = await self.session.execute(
            update(Referral)
            .where(Referral.counted.is_(True))
            .values(counted=False)
        )
        return int(result.rowcount or 0)
