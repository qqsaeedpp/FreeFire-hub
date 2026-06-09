"""Deposit-settings repository (one row per deposit type)."""
from __future__ import annotations

from sqlalchemy import select

from app.core.constants import DepositType
from app.models.deposit_setting import DepositSetting
from app.repositories.base import BaseRepository


class DepositSettingRepository(BaseRepository[DepositSetting]):
    model = DepositSetting

    async def get_by_type(self, deposit_type: DepositType) -> DepositSetting | None:
        result = await self.session.execute(
            select(DepositSetting).where(DepositSetting.deposit_type == deposit_type)
        )
        return result.scalar_one_or_none()
