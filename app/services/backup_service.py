"""Backup service — dump MySQL, package a ZIP, deliver it, clean up.

The archive bundles ``database.sql`` (a full ``mysqldump`` — i.e. users, orders,
wallets, transactions, referrals, discounts, button/text/channel settings, …),
``config.json`` (non-secret runtime info) and ``settings.json`` (a small stats /
config snapshot). Heavy work (the dump, the zip) is awaited so the event loop is
never blocked, and temporary files are removed after the ZIP is built. Delivery
retries a few times; the orchestrator notifies the owner on failure.

Secrets (bot token, DB password) are *never* written into the archive.
"""
from __future__ import annotations

import asyncio
import json
import zipfile
from datetime import datetime
from pathlib import Path

from app.core.config import settings
from app.core.constants import BackupScheduleType, BackupTargetType
from app.core.logger import get_logger
from app.models.backup_setting import BackupSetting
from app.repositories.backup_settings import BackupSettingRepository

log = get_logger("backup")

BACKUP_DIR = Path("backups")
# Telegram bot API caps document uploads at 50 MB.
MAX_BACKUP_BYTES = 50 * 1024 * 1024


class BackupError(Exception):
    """Raised when a backup step (dump / packaging / delivery) fails."""


class BackupService:
    def __init__(self, repo: BackupSettingRepository | None = None) -> None:
        # ``repo`` is only needed for the settings get/set methods. The file-op
        # methods (create/send/cleanup/restore) are stateless, so the background
        # job can use ``BackupService()`` without a DB session.
        self.repo = repo

    # ------------------------------ settings ------------------------------
    async def get(self) -> BackupSetting:
        return await self.repo.get_or_create()

    async def set_target(
        self, target_type: BackupTargetType, target_id: int
    ) -> BackupSetting:
        row = await self.repo.get_or_create()
        row.target_type = target_type
        row.target_id = target_id
        await self.repo.session.flush()
        return row

    async def set_schedule(self, schedule_type: BackupScheduleType) -> BackupSetting:
        row = await self.repo.get_or_create()
        row.schedule_type = schedule_type
        await self.repo.session.flush()
        return row

    async def set_enabled(self, enabled: bool) -> BackupSetting:
        row = await self.repo.get_or_create()
        row.is_enabled = enabled
        await self.repo.session.flush()
        return row

    # --------------------------- archive build ---------------------------
    async def create_backup(self, meta: dict | None = None) -> Path:
        """Produce a ZIP archive in :data:`BACKUP_DIR` and return its path."""
        BACKUP_DIR.mkdir(exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        sql_path = BACKUP_DIR / f"database_{stamp}.sql"
        config_path = BACKUP_DIR / f"config_{stamp}.json"
        settings_path = BACKUP_DIR / f"settings_{stamp}.json"
        zip_path = BACKUP_DIR / f"backup_{stamp}.zip"

        await self._dump_database(sql_path)
        self._write_json(config_path, self._config_snapshot(stamp))
        self._write_json(settings_path, meta or {})

        members = [
            (sql_path, "database.sql"),
            (config_path, "config.json"),
            (settings_path, "settings.json"),
        ]
        await asyncio.get_running_loop().run_in_executor(
            None, self._build_zip, zip_path, members
        )
        # Keep only the ZIP; drop the loose intermediates.
        self.cleanup_backup(sql_path, config_path, settings_path)
        log.info("backup_created", file=str(zip_path), size=zip_path.stat().st_size)
        return zip_path

    async def _dump_database(self, sql_path: Path) -> None:
        cmd = [
            "mysqldump",
            f"-h{settings.mysql_host}",
            f"-P{settings.mysql_port}",
            f"-u{settings.mysql_user}",
            f"-p{settings.mysql_password}",
            "--single-transaction",
            "--quick",
            "--default-character-set=utf8mb4",
            settings.mysql_database,
        ]
        with sql_path.open("wb") as fh:
            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=fh, stderr=asyncio.subprocess.PIPE
            )
            _, stderr = await proc.communicate()
        if proc.returncode != 0:
            detail = (stderr or b"").decode(errors="ignore").strip()[:500]
            raise BackupError(detail or "mysqldump با خطا متوقف شد.")

    @staticmethod
    def _config_snapshot(stamp: str) -> dict:
        """Non-secret runtime info (no token, no password)."""
        return {
            "app": "FreeFire_Hub",
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "stamp": stamp,
            "database": settings.mysql_database,
            "mysql_host": settings.mysql_host,
            "mysql_port": settings.mysql_port,
            "timezone": settings.timezone,
        }

    @staticmethod
    def _write_json(path: Path, data: dict) -> None:
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

    @staticmethod
    def _build_zip(zip_path: Path, members: list[tuple[Path, str]]) -> None:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for src, arcname in members:
                if src.exists():
                    zf.write(src, arcname)

    # ----------------------------- delivery ------------------------------
    async def send_backup(
        self, bot, path: Path, chat_id: int, caption: str | None = None
    ) -> None:
        """Send the archive, retrying a few times on transient failures."""
        size = path.stat().st_size
        if size > MAX_BACKUP_BYTES:
            raise BackupError(
                f"حجم فایل بکاپ ({size // 1024 // 1024}MB) از حد مجاز تلگرام (۵۰MB) بیشتر است."
            )
        from aiogram.types import FSInputFile

        last_exc: Exception | None = None
        for attempt in range(1, 4):
            try:
                await bot.send_document(
                    chat_id, FSInputFile(str(path)), caption=caption
                )
                return
            except Exception as exc:  # noqa: BLE001 - retry any send failure
                last_exc = exc
                log.warning("backup_send_retry", attempt=attempt, error=str(exc))
                await asyncio.sleep(2 * attempt)
        raise BackupError(f"ارسال بکاپ پس از چند تلاش ناموفق بود: {last_exc}")

    # ------------------------------ cleanup ------------------------------
    @staticmethod
    def cleanup_backup(*paths: Path) -> None:
        for p in paths:
            try:
                p.unlink(missing_ok=True)
            except OSError as exc:  # noqa: PERF203
                log.warning("backup_cleanup_failed", file=str(p), error=str(exc))

    # ------------------------------ restore ------------------------------
    async def restore_backup(self, sql_path: Path) -> None:
        """Import a ``database.sql`` dump back into MySQL (manual recovery).

        Destructive — intentionally not wired to any Telegram button. Exposed as
        a service method so recovery can be scripted/invoked deliberately.
        """
        cmd = [
            "mysql",
            f"-h{settings.mysql_host}",
            f"-P{settings.mysql_port}",
            f"-u{settings.mysql_user}",
            f"-p{settings.mysql_password}",
            settings.mysql_database,
        ]
        with sql_path.open("rb") as fh:
            proc = await asyncio.create_subprocess_exec(
                *cmd, stdin=fh, stderr=asyncio.subprocess.PIPE
            )
            _, stderr = await proc.communicate()
        if proc.returncode != 0:
            detail = (stderr or b"").decode(errors="ignore").strip()[:500]
            raise BackupError(detail or "بازگردانی دیتابیس با خطا متوقف شد.")

    # ----------------------------- scheduling -----------------------------
    def schedule_backup(
        self, schedule_type: BackupScheduleType, is_enabled: bool, bot=None
    ) -> None:
        """(Re)configure the live APScheduler auto-backup job. No-op if not running."""
        from app.scheduler.tasks import apply_backup_schedule

        apply_backup_schedule(schedule_type, is_enabled, bot)
