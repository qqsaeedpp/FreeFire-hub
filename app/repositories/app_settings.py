"""Repository for the durable key/value app-settings table."""
from __future__ import annotations

from sqlalchemy import select

from app.models.app_setting import AppSetting
from app.repositories.base import BaseRepository


class AppSettingRepository(BaseRepository[AppSetting]):
    model = AppSetting

    async def get_by_key(self, key: str) -> AppSetting | None:
        result = await self.session.execute(
            select(AppSetting).where(AppSetting.key == key)
        )
        return result.scalar_one_or_none()
