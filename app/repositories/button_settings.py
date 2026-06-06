"""Button-settings repository."""
from __future__ import annotations

from sqlalchemy import select

from app.models.button_settings import ButtonSettings
from app.repositories.base import BaseRepository


class ButtonSettingsRepository(BaseRepository[ButtonSettings]):
    model = ButtonSettings

    async def get_by_key(self, key: str) -> ButtonSettings | None:
        result = await self.session.execute(
            select(ButtonSettings).where(ButtonSettings.key == key)
        )
        return result.scalar_one_or_none()

    async def all(self) -> list[ButtonSettings]:
        result = await self.session.execute(select(ButtonSettings))
        return list(result.scalars().all())
