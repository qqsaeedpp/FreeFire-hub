"""APScheduler background jobs: stale-reservation cleanup and DB backup."""
from __future__ import annotations

import subprocess
from datetime import datetime, timedelta
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select, update

from app.core.config import settings
from app.core.constants import AccountStatus, OrderStatus
from app.core.database import get_sessionmaker
from app.core.logger import get_logger
from app.models.account import Account
from app.models.order import AccountOrder, Order

log = get_logger("scheduler")
BACKUP_DIR = Path("backups")
BACKUP_DIR.mkdir(exist_ok=True)

RESERVATION_TTL = timedelta(hours=2)


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


def backup_database() -> None:
    """Dump the MySQL database with mysqldump into the backups directory."""
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = BACKUP_DIR / f"backup_{stamp}.sql"
    cmd = [
        "mysqldump",
        f"-h{settings.mysql_host}",
        f"-P{settings.mysql_port}",
        f"-u{settings.mysql_user}",
        f"-p{settings.mysql_password}",
        settings.mysql_database,
    ]
    try:
        with out.open("wb") as fh:
            subprocess.run(cmd, stdout=fh, stderr=subprocess.PIPE, check=True, timeout=300)
        log.info("db_backup_created", file=str(out))
    except Exception as exc:  # noqa: BLE001
        log.warning("db_backup_failed", error=str(exc))


def setup_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=settings.timezone)
    scheduler.add_job(
        release_stale_reservations,
        IntervalTrigger(minutes=15),
        id="release_reservations",
        replace_existing=True,
    )
    scheduler.add_job(
        backup_database,
        CronTrigger(hour=3, minute=0),  # daily 03:00
        id="db_backup",
        replace_existing=True,
    )
    return scheduler
