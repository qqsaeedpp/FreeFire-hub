"""APScheduler background jobs: stale-reservation cleanup + configurable backup.

The auto-backup job is (re)configured at runtime from the single ``backup_settings``
row: enabling/disabling it or changing its cadence reschedules the live job
without a restart (see :func:`apply_backup_schedule`). The actual archive build
and delivery live in :mod:`app.scheduler.backup`; this module only owns the
scheduler wiring so the heavy lifting stays testable and off the hot path.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select

from app.core.config import settings
from app.core.constants import AccountStatus, BackupScheduleType, OrderStatus
from app.core.database import get_sessionmaker
from app.core.logger import get_logger
from app.models.account import Account
from app.models.order import AccountOrder, Order

log = get_logger("scheduler")
BACKUP_DIR = Path("backups")
BACKUP_DIR.mkdir(exist_ok=True)

RESERVATION_TTL = timedelta(hours=2)

_BACKUP_JOB_ID = "auto_backup"

# Captured once at startup so a reschedule triggered from the admin panel can
# reach the live scheduler and a bot instance without threading them through
# every call site.
_scheduler: AsyncIOScheduler | None = None
_bot = None


async def release_stale_reservations() -> None:
    """Free accounts reserved for an order that never got paid within the TTL."""
    cutoff = datetime.utcnow() - RESERVATION_TTL
    async with get_sessionmaker()() as session:
        result = await session.execute(
            select(Account).where(
                Account.status == AccountStatus.RESERVED, Account.updated_at < cutoff
            )
        )
        stale = list(result.scalars().all())
        for account in stale:
            # keep reservation if its order is already under review / approved
            order_result = await session.execute(
                select(Order)
                .join(AccountOrder, AccountOrder.id == Order.id)
                .where(
                    AccountOrder.account_id == account.id,
                    Order.status.in_(
                        [OrderStatus.UNDER_REVIEW, OrderStatus.APPROVED]
                    ),
                )
            )
            if order_result.first():
                continue
            account.status = AccountStatus.AVAILABLE
            account.reserved_by_id = None
        if stale:
            await session.commit()
            log.info("released_stale_reservations", count=len(stale))


def _trigger_for(schedule_type: BackupScheduleType):
    """Map a configured cadence to an APScheduler trigger."""
    if schedule_type == BackupScheduleType.SIX_HOURS:
        return IntervalTrigger(hours=6)
    if schedule_type == BackupScheduleType.TWELVE_HOURS:
        return IntervalTrigger(hours=12)
    if schedule_type == BackupScheduleType.WEEKLY:
        return CronTrigger(day_of_week="fri", hour=3, minute=0)
    return CronTrigger(hour=3, minute=0)  # DAILY (default)


async def _run_backup_job() -> None:
    """Scheduler entrypoint — delegate to the orchestrator with the saved bot."""
    from app.scheduler.backup import run_backup

    if _bot is None:
        log.warning("auto_backup_no_bot")
        return
    await run_backup(_bot)


def apply_backup_schedule(
    schedule_type: BackupScheduleType, is_enabled: bool, bot=None
) -> None:
    """(Re)configure the live auto-backup job. No-op if the scheduler isn't running.

    Called at startup with the saved settings and again whenever the admin
    toggles auto-backup or changes its cadence. Removing the job first means a
    *disable* truly stops future runs, not just replaces the trigger.
    """
    global _bot
    if bot is not None:
        _bot = bot
    if _scheduler is None:
        return  # scheduler not started yet (e.g. imported in a non-runtime context)
    if _scheduler.get_job(_BACKUP_JOB_ID):
        _scheduler.remove_job(_BACKUP_JOB_ID)
    if not is_enabled:
        log.info("auto_backup_disabled")
        return
    _scheduler.add_job(
        _run_backup_job,
        _trigger_for(schedule_type),
        id=_BACKUP_JOB_ID,
        replace_existing=True,
    )
    log.info("auto_backup_scheduled", schedule=schedule_type.value)


def setup_scheduler(bot=None) -> AsyncIOScheduler:
    """Build the scheduler with the always-on reservation-cleanup job.

    The auto-backup job is added later by :func:`apply_backup_schedule` (called
    from startup once the saved settings are read), so a disabled backup never
    registers a job.
    """
    global _scheduler, _bot
    _bot = bot
    scheduler = AsyncIOScheduler(timezone=settings.timezone)
    scheduler.add_job(
        release_stale_reservations,
        IntervalTrigger(minutes=15),
        id="release_reservations",
        replace_existing=True,
    )
    _scheduler = scheduler
    return scheduler
