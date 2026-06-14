"""Backup service — dump MySQL, package a ZIP, deliver it, restore it, clean up.

The archive bundles ``database.sql`` (a full ``mysqldump`` — i.e. users, orders,
wallets, transactions, referrals, discounts, button/text/channel settings, …),
``metadata.json`` (backup time, bot version, db name/type, row counts and the
SHA-256 of ``database.sql``), ``settings.json`` (a non-secret config snapshot)
and ``README_restore.txt`` (how to recover). Heavy work (the dump, the zip, the
restore) is awaited so the event loop is never blocked, and temporary files are
removed after use. Delivery retries a few times; the orchestrator notifies the
owner on failure.

SSL handling — the bot's MySQL CLIs run against the server over the internal
Docker network. The Debian ``default-mysql-client`` package ships the **MariaDB**
client, whose ``mysqldump``/``mysql`` reject MySQL-8's ``--ssl-mode`` flag, while
an MySQL-8 server with a self-signed cert rejects an unconfigured client with
error 2026 ("TLS/SSL error: self-signed certificate in certificate chain"). So we
try the MySQL syntax (``--ssl-mode=<MYSQL_SSL_MODE>``, default ``DISABLED``) and,
if the client doesn't understand it, transparently fall back to the MariaDB
syntax (``--ssl=0``/``--ssl=1``). This makes backups work on both clients with no
per-host configuration.

Secrets (bot token, DB password) are *never* written into the archive.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
import zipfile
from datetime import datetime
from pathlib import Path

from app import __version__
from app.core.config import settings
from app.core.constants import BackupScheduleType, BackupTargetType
from app.core.logger import get_logger
from app.models.backup_setting import BackupSetting
from app.repositories.backup_settings import BackupSettingRepository

log = get_logger("backup")

BACKUP_DIR = Path("backups")
# Telegram bot API caps document uploads at 50 MB…
MAX_BACKUP_BYTES = 50 * 1024 * 1024
# …and caps ``getFile`` downloads (used by restore) at 20 MB.
MAX_RESTORE_BYTES = 20 * 1024 * 1024

# SSL modes that mean "no TLS" — used to pick the MariaDB ``--ssl=0`` fallback.
_SSL_DISABLED_VALUES = {"", "0", "DISABLE", "DISABLED", "OFF", "FALSE", "NO"}


class BackupError(Exception):
    """Raised when a backup step (dump / packaging / delivery / restore) fails."""


class BackupService:
    def __init__(self, repo: BackupSettingRepository | None = None) -> None:
        # ``repo`` is only needed for the settings get/set methods. The file-op
        # methods (create/send/cleanup/restore/validate) are stateless, so the
        # background job can use ``BackupService()`` without a DB session.
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

    # ------------------------------- SSL args -----------------------------
    def get_ssl_args(self) -> list[str]:
        """Primary SSL flag in MySQL-8 syntax (``--ssl-mode=…``).

        Empty when ``MYSQL_SSL_MODE`` is unset, which lets the client use its own
        default (and disables the fallback path).
        """
        mode = (settings.mysql_ssl_mode or "").strip()
        return [f"--ssl-mode={mode}"] if mode else []

    @staticmethod
    def _ssl_fallback_args() -> list[str]:
        """Fallback SSL flag in MariaDB-client syntax (``--ssl=0``/``--ssl=1``).

        Mirrors the requested ``MYSQL_SSL_MODE`` intent: a "disabled" mode maps to
        ``--ssl=0`` (no TLS); anything else maps to ``--ssl=1`` (TLS on), so an
        operator who actually wants TLS isn't silently downgraded by the fallback.
        """
        mode = (settings.mysql_ssl_mode or "").strip().upper()
        return ["--ssl=0"] if mode in _SSL_DISABLED_VALUES else ["--ssl=1"]

    @staticmethod
    def _is_unknown_ssl_option(stderr: str) -> bool:
        """True when the client rejected ``--ssl-mode`` (i.e. it's a MariaDB CLI)."""
        low = stderr.lower()
        return "ssl-mode" in low and (
            "unknown variable" in low or "unknown option" in low
        )

    def _connection_args(self) -> list[str]:
        return [
            f"-h{settings.mysql_host}",
            f"-P{settings.mysql_port}",
            f"-u{settings.mysql_user}",
            f"-p{settings.mysql_password}",
        ]

    def _dump_cmd(self, ssl_args: list[str]) -> list[str]:
        return [
            "mysqldump",
            *self._connection_args(),
            *ssl_args,
            "--single-transaction",
            "--quick",
            "--default-character-set=utf8mb4",
            settings.mysql_database,
        ]

    def _restore_cmd(self, ssl_args: list[str]) -> list[str]:
        return [
            "mysql",
            *self._connection_args(),
            *ssl_args,
            settings.mysql_database,
        ]

    @staticmethod
    def _friendly_error(stderr: str) -> str:
        """Map a raw CLI stderr to a clear Persian message for the owner."""
        low = stderr.lower()
        detail = stderr.strip()[:400]
        if ("ssl" in low or "tls" in low) and (
            "certificate" in low or "self-signed" in low or "self signed" in low
        ):
            return (
                "خطای SSL/TLS هنگام اتصال به دیتابیس. مقدار MYSQL_SSL_MODE را روی "
                f"DISABLED بگذارید.\n{detail}"
            )
        if "access denied" in low:
            return f"دسترسی به دیتابیس رد شد (نام‌کاربری/رمز اشتباه است).\n{detail}"
        if (
            "can't connect" in low
            or "cannot connect" in low
            or "connection refused" in low
            or "unknown mysql server host" in low
            or "unknown server host" in low
        ):
            return f"اتصال به سرور دیتابیس ناموفق بود (هاست/پورت را بررسی کنید).\n{detail}"
        if "unknown database" in low:
            return f"دیتابیس موردنظر یافت نشد.\n{detail}"
        return detail or "عملیات دیتابیس با خطا متوقف شد."

    # --------------------------- dump (mysqldump) -------------------------
    async def run_mysqldump_with_fallback(self, sql_path: Path) -> None:
        """Dump the database, trying ``--ssl-mode`` then falling back to ``--ssl``."""
        rc, stderr = await self._exec_dump(self._dump_cmd(self.get_ssl_args()), sql_path)
        if rc == 0:
            return
        if self._is_unknown_ssl_option(stderr) and self.get_ssl_args():
            log.info("mysqldump_ssl_fallback")
            rc, stderr = await self._exec_dump(
                self._dump_cmd(self._ssl_fallback_args()), sql_path
            )
            if rc == 0:
                return
        raise BackupError(self._friendly_error(stderr))

    async def _exec_dump(self, cmd: list[str], sql_path: Path) -> tuple[int | None, str]:
        try:
            with sql_path.open("wb") as fh:
                proc = await asyncio.create_subprocess_exec(
                    *cmd, stdout=fh, stderr=asyncio.subprocess.PIPE
                )
                _, stderr = await proc.communicate()
        except FileNotFoundError as exc:  # mysqldump binary not installed
            raise BackupError(
                "ابزار mysqldump روی سرور نصب نیست. بسته default-mysql-client "
                "(یا mysql-client) را نصب کنید."
            ) from exc
        return proc.returncode, (stderr or b"").decode(errors="ignore").strip()

    async def create_database_dump(self, sql_path: Path) -> None:
        """Public alias: produce a full SQL dump at ``sql_path``."""
        await self.run_mysqldump_with_fallback(sql_path)

    # ------------------------- restore (mysql CLI) ------------------------
    async def run_mysql_restore_with_fallback(self, sql_path: Path) -> None:
        """Import a ``database.sql`` dump, with the same SSL fallback as the dump."""
        rc, stderr = await self._exec_restore(
            self._restore_cmd(self.get_ssl_args()), sql_path
        )
        if rc == 0:
            return
        if self._is_unknown_ssl_option(stderr) and self.get_ssl_args():
            log.info("mysql_restore_ssl_fallback")
            rc, stderr = await self._exec_restore(
                self._restore_cmd(self._ssl_fallback_args()), sql_path
            )
            if rc == 0:
                return
        raise BackupError(self._friendly_error(stderr))

    async def _exec_restore(
        self, cmd: list[str], sql_path: Path
    ) -> tuple[int | None, str]:
        try:
            with sql_path.open("rb") as fh:
                proc = await asyncio.create_subprocess_exec(
                    *cmd, stdin=fh, stderr=asyncio.subprocess.PIPE
                )
                _, stderr = await proc.communicate()
        except FileNotFoundError as exc:  # mysql binary not installed
            raise BackupError(
                "ابزار mysql روی سرور نصب نیست. بسته default-mysql-client "
                "(یا mysql-client) را نصب کنید."
            ) from exc
        return proc.returncode, (stderr or b"").decode(errors="ignore").strip()

    async def restore_backup(self, sql_path: Path) -> None:
        """Import a ``database.sql`` dump back into MySQL (destructive)."""
        await self.run_mysql_restore_with_fallback(sql_path)

    # --------------------------- archive build ---------------------------
    async def create_backup(self, meta: dict | None = None) -> Path:
        """Produce a ZIP archive in :data:`BACKUP_DIR` and return its path.

        The ZIP always contains ``database.sql``, ``metadata.json``,
        ``settings.json`` and ``README_restore.txt``.
        """
        BACKUP_DIR.mkdir(exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        sql_path = BACKUP_DIR / f"database_{stamp}.sql"
        metadata_path = BACKUP_DIR / f"metadata_{stamp}.json"
        settings_path = BACKUP_DIR / f"settings_{stamp}.json"
        readme_path = BACKUP_DIR / f"README_restore_{stamp}.txt"
        zip_path = BACKUP_DIR / f"backup_{stamp}.zip"

        await self.create_database_dump(sql_path)
        metadata = self._build_metadata(stamp, sql_path, meta or {})
        self._write_json(metadata_path, metadata)
        self._write_json(settings_path, self._settings_snapshot(meta or {}))
        readme_path.write_text(self._readme_text(metadata), encoding="utf-8")

        members = [
            (sql_path, "database.sql"),
            (metadata_path, "metadata.json"),
            (settings_path, "settings.json"),
            (readme_path, "README_restore.txt"),
        ]
        await asyncio.get_running_loop().run_in_executor(
            None, self._build_zip, zip_path, members
        )
        # Keep only the ZIP; drop the loose intermediates.
        self.cleanup_temp_files(sql_path, metadata_path, settings_path, readme_path)
        log.info("backup_created", file=str(zip_path), size=zip_path.stat().st_size)
        return zip_path

    async def create_emergency_backup(self, meta: dict | None = None) -> Path:
        """Build a pre-restore safety backup of the *current* database."""
        return await self.create_backup(meta)

    def _build_metadata(self, stamp: str, sql_path: Path, meta: dict) -> dict:
        """Backup descriptor embedded as ``metadata.json`` (point 5 of the spec)."""
        return {
            "backup_time": datetime.now().isoformat(timespec="seconds"),
            "stamp": stamp,
            "bot_version": __version__,
            "app": "FreeFire_Hub",
            "database_name": settings.mysql_database,
            "database_type": "mysql",
            "users_count": meta.get("users"),
            "orders_count": meta.get("orders"),
            "banned_users_count": meta.get("banned_users"),
            "database_size_bytes": sql_path.stat().st_size,
            "database_sha256": self._sha256(sql_path),
        }

    @staticmethod
    def _settings_snapshot(meta: dict) -> dict:
        """Non-secret, exportable config snapshot (no token, no password)."""
        return {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "timezone": settings.timezone,
            "database": settings.mysql_database,
            "mysql_host": settings.mysql_host,
            "mysql_port": settings.mysql_port,
            "auto_backup_enabled": meta.get("auto_enabled"),
            "backup_schedule": meta.get("schedule"),
            "backup_target_type": meta.get("target_type"),
            "referral_reward": settings.referral_reward,
            "requested_account_deposit": settings.requested_account_deposit,
        }

    @staticmethod
    def _readme_text(metadata: dict) -> str:
        return (
            "راهنمای بازگردانی بکاپ FreeFire_Hub\n"
            "=====================================\n\n"
            f"زمان تهیه بکاپ : {metadata.get('backup_time', '-')}\n"
            f"نسخه ربات      : {metadata.get('bot_version', '-')}\n"
            f"نام دیتابیس    : {metadata.get('database_name', '-')}\n"
            f"تعداد کاربران  : {metadata.get('users_count', '-')}\n"
            f"تعداد سفارش‌ها : {metadata.get('orders_count', '-')}\n"
            f"SHA-256 فایل database.sql:\n{metadata.get('database_sha256', '-')}\n\n"
            "محتویات این بکاپ:\n"
            "  - database.sql        دامپ کامل دیتابیس\n"
            "  - metadata.json       اطلاعات و هش بکاپ\n"
            "  - settings.json       تنظیمات غیرحساس\n"
            "  - README_restore.txt  همین راهنما\n\n"
            "روش بازگردانی از داخل ربات:\n"
            "  پنل مدیریت > 💾 مدیریت بکاپ > ♻️ ریستور بکاپ > ارسال همین فایل ZIP\n\n"
            "روش بازگردانی دستی روی سرور:\n"
            "  unzip backup.zip\n"
            "  mysql -h<HOST> -P<PORT> -u<USER> -p <DATABASE> < database.sql\n"
            "  (در صورت خطای SSL از سوییچ --ssl=0 استفاده کنید)\n\n"
            "هشدار: بازگردانی، داده‌های فعلی دیتابیس را به‌طور کامل جایگزین می‌کند.\n"
        )

    @staticmethod
    def _sha256(path: Path) -> str:
        h = hashlib.sha256()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()

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

    # ------------------------- restore from a ZIP -------------------------
    def validate_zip(self, zip_path: Path) -> dict:
        """Validate a restore ZIP and return its ``metadata.json`` (or ``{}``).

        Raises :class:`BackupError` if it isn't a ZIP or has no ``database.sql``.
        """
        if not zipfile.is_zipfile(zip_path):
            raise BackupError("فایل ارسالی یک ZIP معتبر نیست.")
        with zipfile.ZipFile(zip_path) as zf:
            names = zf.namelist()
            if "database.sql" not in names:
                raise BackupError(
                    "فایل database.sql در ZIP یافت نشد؛ این یک بکاپ معتبر نیست."
                )
            metadata: dict = {}
            if "metadata.json" in names:
                try:
                    metadata = json.loads(zf.read("metadata.json").decode("utf-8"))
                except (ValueError, KeyError, UnicodeDecodeError):
                    metadata = {}
        return metadata

    def extract_sql(self, zip_path: Path) -> Path:
        """Extract ``database.sql`` from the ZIP to a temp file; return its path."""
        BACKUP_DIR.mkdir(exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out = BACKUP_DIR / f"restore_{stamp}.sql"
        with zipfile.ZipFile(zip_path) as zf, zf.open("database.sql") as src, out.open(
            "wb"
        ) as dst:
            shutil.copyfileobj(src, dst)
        return out

    async def restore_from_zip(self, zip_path: Path) -> dict:
        """Validate + extract + restore from a backup ZIP. Returns its metadata.

        Destructive: replaces the current database. The caller is responsible for
        taking the pre-restore emergency backup first.
        """
        metadata = self.validate_zip(zip_path)
        sql_path = self.extract_sql(zip_path)
        try:
            await self.run_mysql_restore_with_fallback(sql_path)
        finally:
            self.cleanup_temp_files(sql_path)
        return metadata

    # --------------------------- target check ----------------------------
    async def validate_backup_target(
        self, bot, target_type: BackupTargetType, target_id: int
    ) -> tuple[bool, str]:
        """Check the bot can actually deliver a backup to ``target_id``.

        Channel → the bot must be an admin of the channel. User → the user must
        have started the bot (so the bot may message them). Returns
        ``(ok, message)`` with a Persian explanation either way.
        """
        from aiogram.enums import ChatMemberStatus
        from aiogram.exceptions import (
            TelegramAPIError,
            TelegramBadRequest,
            TelegramForbiddenError,
        )

        try:
            if target_type == BackupTargetType.CHANNEL:
                chat = await bot.get_chat(target_id)
                member = await bot.get_chat_member(target_id, bot.id)
                if member.status not in (
                    ChatMemberStatus.ADMINISTRATOR,
                    ChatMemberStatus.CREATOR,
                ):
                    return False, (
                        "ربات باید در کانال ادمین باشد تا بتواند بکاپ ارسال کند."
                    )
                title = getattr(chat, "title", None) or str(target_id)
                return True, f"کانال «{title}» تایید شد."
            # USER target — a chat action proves we're allowed to message them.
            await bot.send_chat_action(target_id, "upload_document")
            return True, "کاربر مقصد تایید شد."
        except TelegramForbiddenError:
            return False, (
                "ارسال ممکن نیست: کاربر ربات را استارت نکرده یا ربات را بلاک کرده است."
            )
        except TelegramBadRequest as exc:
            return False, (
                "مقصد نامعتبر است یا ربات به آن دسترسی ندارد "
                f"({exc.message})."
            )
        except TelegramAPIError as exc:
            return False, f"بررسی مقصد ناموفق بود: {exc}"

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

    @staticmethod
    def cleanup_temp_files(*paths: Path) -> None:
        """Alias for :meth:`cleanup_backup` (spec naming)."""
        BackupService.cleanup_backup(*paths)

    # ----------------------------- scheduling -----------------------------
    def schedule_backup(
        self, schedule_type: BackupScheduleType, is_enabled: bool, bot=None
    ) -> None:
        """(Re)configure the live APScheduler auto-backup job. No-op if not running."""
        from app.scheduler.tasks import apply_backup_schedule

        apply_backup_schedule(schedule_type, is_enabled, bot)
