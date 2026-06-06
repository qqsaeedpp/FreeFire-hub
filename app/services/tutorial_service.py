"""Admin-managed tutorial videos, keyed by a stable ``key``.

Each tutorial is a Telegram ``file_id`` stored in the ``tutorial_media`` table.
Admins upload/replace the video from the panel (no code change needed) and the
same file_id is re-sent to users on demand.
"""
from __future__ import annotations

from app.models.tutorial_media import TutorialMedia
from app.repositories.tutorial_media import TutorialMediaRepository

# Stable key for the Google Backup-Code tutorial shown in the diamond-account flow.
GOOGLE_BACKUP_CODE_VIDEO = "GOOGLE_BACKUP_CODE_VIDEO"

# Human-readable Persian labels for each managed tutorial (shown in the admin list).
TUTORIAL_LABELS: dict[str, str] = {
    GOOGLE_BACKUP_CODE_VIDEO: "🎥 آموزش گرفتن Backup Code گوگل",
}


class TutorialService:
    def __init__(self, media: TutorialMediaRepository) -> None:
        self.media = media

    async def get(self, key: str) -> TutorialMedia | None:
        return await self.media.get_by_key(key)

    async def get_file_id(self, key: str) -> str | None:
        row = await self.media.get_by_key(key)
        return row.file_id if row else None

    async def set_file_id(
        self, key: str, file_id: str, caption: str | None = None
    ) -> None:
        """Create or update the stored video for ``key``."""
        row = await self.media.get_by_key(key)
        if row is None:
            await self.media.add(
                TutorialMedia(key=key, file_id=file_id, caption=caption)
            )
        else:
            row.file_id = file_id
            if caption is not None:
                row.caption = caption

    async def clear(self, key: str) -> bool:
        """Remove the stored video for ``key`` (keeps no file_id)."""
        row = await self.media.get_by_key(key)
        if row is None:
            return False
        row.file_id = None
        return True
