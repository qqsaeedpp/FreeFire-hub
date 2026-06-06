"""Tutorial-media repository."""
from __future__ import annotations

from sqlalchemy import select

from app.models.tutorial_media import TutorialMedia
from app.repositories.base import BaseRepository


class TutorialMediaRepository(BaseRepository[TutorialMedia]):
    model = TutorialMedia

    async def get_by_key(self, key: str) -> TutorialMedia | None:
        result = await self.session.execute(
            select(TutorialMedia).where(TutorialMedia.key == key)
        )
        return result.scalar_one_or_none()
