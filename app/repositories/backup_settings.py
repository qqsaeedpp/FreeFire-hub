"""Backup-settings repository (one global row, lazily created)."""
from __future__ import annotations

from sqlalchemy import select

from app.models.backup_setting import BackupSetting
from app.repositories.base import BaseRepository


class BackupSettingRepository(BaseRepository[BackupSetting]):
    model = BackupSetting

    async def get_or_create(self) -> BackupSetting:
        """Return the single settings row, creating a disabled default if absent."""
        result = await self.session.execute(
            select(BackupSetting).order_by(BackupSetting.id.asc()).limit(1)
        )
        row = result.scalars().first()
        if row is None:
            row = BackupSetting()
            self.session.add(row)
            await self.session.flush()
        return row
