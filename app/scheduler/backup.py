"""Background backup orchestrator — build the archive and deliver it.

Runs *outside* any request: it opens its own DB session, reads the configured
destination, then builds the ZIP and sends it to the target (a user id or a
private channel). Every failure is caught and reported to the owner(s); the bot
is never affected and the temporary archive is always removed.

Used by both the manual «📥 بکاپ دستی» button and the APScheduler auto-backup
job (:func:`app.scheduler.tasks._run_backup_job`).
"""
from __future__ import annotations

from datetime import datetime

from app.core.config import settings
from app.core.database import get_sessionmaker
from app.core.logger import get_logger
from app.services.backup_service import BackupError, BackupService
from app.services.notification_service import NotificationService

log = get_logger("backup")


async def _notify_owners(bot, text: str) -> None:
    """Best-effort DM to every configured owner (env ``ADMIN_ID``)."""
    notifier = NotificationService(bot)
    for owner_id in settings.admin_ids:
        await notifier.notify_user(owner_id, text)


async def _gather_meta(services, setting) -> dict:
    """Collect a small, non-secret stats snapshot stored as ``settings.json``."""
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "users": await services.users.count(),
        "banned_users": await services.banned_repo.count_active(),
        "orders": await services.orders.count(),
        "schedule": setting.schedule_type.value,
        "target_type": setting.target_type.value if setting.target_type else None,
        "auto_enabled": setting.is_enabled,
    }


def _caption(meta: dict) -> str:
    return (
        "💾 <b>بکاپ دیتابیس FreeFire_Hub</b>\n"
        f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
        f"👥 کاربران: {meta.get('users', '—')}\n"
        f"🚫 کاربران مسدود: {meta.get('banned_users', '—')}\n"
        f"🧾 سفارش‌ها: {meta.get('orders', '—')}"
    )


async def run_backup(bot, requester_id: int | None = None) -> None:
    """Create a backup and deliver it to the configured target (and requester).

    ``requester_id`` is the admin who pressed «📥 بکاپ دستی»: they receive a copy
    *at that moment* in addition to the configured destination, so a manual backup
    always lands in the requesting admin's chat even before a target is set.

    Safe to fire-and-forget: the DB session only reads the destination + stats
    (primitive values are extracted before it closes), and the heavy file work
    (dump / zip / send) runs session-less so a slow archive never holds a
    connection. Any error notifies the owner(s); the archive is always cleaned up.
    """
    from app.container import Services  # local import keeps the import graph acyclic

    async with get_sessionmaker()() as session:
        services = Services(session)
        setting = await services.backup.get()
        has_target = setting.target_type is not None and setting.target_id is not None
        target_id = int(setting.target_id) if has_target else None
        meta = await _gather_meta(services, setting)

    # Deduplicated recipient list: configured target first, then the requester.
    recipients: list[int] = []
    if target_id is not None:
        recipients.append(target_id)
    if requester_id is not None and requester_id not in recipients:
        recipients.append(requester_id)

    if not recipients:
        await _notify_owners(bot, "⚠️ بکاپ انجام نشد: مقصد ارسال تنظیم نشده است.")
        return

    # File ops are stateless — a session-less service keeps them off the DB conn.
    backup = BackupService()
    zip_path = None
    try:
        zip_path = await backup.create_backup(meta)
        caption = _caption(meta)
        sent_to: list[int] = []
        for chat_id in recipients:
            try:
                await backup.send_backup(bot, zip_path, chat_id, caption=caption)
                sent_to.append(chat_id)
            except BackupError as exc:
                await _notify_owners(
                    bot,
                    f"🛑 ارسال بکاپ به <code>{chat_id}</code> ناموفق بود:\n"
                    f"<code>{exc}</code>",
                )
                log.warning("backup_send_failed", target=chat_id, error=str(exc))
        if sent_to:
            await NotificationService(bot).log_event(
                "بکاپ دیتابیس ارسال شد",
                {
                    "مقصدها": ", ".join(f"<code>{c}</code>" for c in sent_to),
                    "حجم": f"{zip_path.stat().st_size // 1024} KB",
                },
            )
            log.info("backup_sent", targets=sent_to)
    except BackupError as exc:
        await _notify_owners(bot, f"🛑 بکاپ ناموفق بود:\n<code>{exc}</code>")
        log.warning("backup_failed", error=str(exc))
    except Exception as exc:  # noqa: BLE001 - a background job must never crash
        await _notify_owners(bot, f"🛑 خطای غیرمنتظره در بکاپ:\n<code>{exc}</code>")
        log.error("backup_unexpected_error", error=str(exc))
    finally:
        if zip_path is not None:
            backup.cleanup_temp_files(zip_path)
