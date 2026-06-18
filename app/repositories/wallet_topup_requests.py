"""WalletTopUpRequest repository — paginated reads by status for the admin panel."""
from __future__ import annotations

from sqlalchemy import func, select

from app.core.constants import WalletTopUpStatus
from app.models.wallet_topup_request import WalletTopUpRequest
from app.repositories.base import BaseRepository


class WalletTopUpRequestRepository(BaseRepository[WalletTopUpRequest]):
    model = WalletTopUpRequest

    async def list_by_status(
        self, status: WalletTopUpStatus, *, offset: int = 0, limit: int = 10
    ) -> list[WalletTopUpRequest]:
        result = await self.session.execute(
            select(WalletTopUpRequest)
            .where(WalletTopUpRequest.status == status)
            .order_by(WalletTopUpRequest.id.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def count_by_status(self, status: WalletTopUpStatus) -> int:
        result = await self.session.execute(
            select(func.count())
            .select_from(WalletTopUpRequest)
            .where(WalletTopUpRequest.status == status)
        )
        return int(result.scalar_one())
