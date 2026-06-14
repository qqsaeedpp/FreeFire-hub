"""Application entrypoint — builds the bot, dispatcher, middlewares and runs polling."""
from __future__ import annotations

import asyncio

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import BotCommand

from app.core.config import settings
from app.core.logger import configure_logging, get_logger
from app.core.redis import close_redis, redis_client
from app.handlers import register_routers
from app.middlewares.ban import BanMiddleware
from app.middlewares.channel_lock import ChannelLockMiddleware
from app.middlewares.database import DatabaseMiddleware
from app.middlewares.menu_reset import MenuResetMiddleware
from app.middlewares.throttling import ThrottlingMiddleware
from app.scheduler.tasks import setup_scheduler
from app.services.notification_service import NotificationService
from app.utils.notifications import router as errors_router

log = get_logger("main")


def build_dispatcher() -> Dispatcher:
    storage = RedisStorage(redis=redis_client)
    dp = Dispatcher(storage=storage)

    # Order matters: throttle -> db (load user) -> ban-check.
    dp.update.outer_middleware(ThrottlingMiddleware())
    dp.update.outer_middleware(DatabaseMiddleware())
    dp.update.outer_middleware(BanMiddleware())
    # Forced-channel-membership gate (after ban so db_user/services are loaded).
    dp.update.outer_middleware(ChannelLockMiddleware())

    # Drop a stale FSM state when a main-menu button is tapped, before the
    # message is routed (otherwise a flow's state handler swallows the press).
    dp.message.outer_middleware(MenuResetMiddleware())

    dp.include_router(errors_router)
    register_routers(dp)
    return dp


async def _load_backup_schedule(bot: Bot) -> None:
    """Apply the saved auto-backup cadence to the live scheduler at startup.

    Reads the single ``backup_settings`` row (created disabled on first run) and
    registers the APScheduler job only if auto-backup is enabled. Never blocks
    startup — a failure here just means no auto-backup until reconfigured.
    """
    from app.container import Services
    from app.core.database import get_sessionmaker
    from app.scheduler.tasks import apply_backup_schedule

    try:
        async with get_sessionmaker()() as session:
            setting = await Services(session).backup.get()
            await session.commit()
            schedule_type, is_enabled = setting.schedule_type, setting.is_enabled
        apply_backup_schedule(schedule_type, is_enabled, bot)
    except Exception as exc:  # noqa: BLE001 - startup must never fail on this
        log.warning("backup_schedule_load_failed", error=str(exc))


async def main() -> None:
    configure_logging()
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = build_dispatcher()

    scheduler = setup_scheduler(bot)
    scheduler.start()
    await _load_backup_schedule(bot)

    # Bot command menu — only «/start».
    await bot.set_my_commands([BotCommand(command="start", description="شروع")])

    notifier = NotificationService(bot)
    me = await bot.me()
    log.info("bot_starting", username=me.username, id=me.id)
    await notifier.log_event("ربات روشن شد", {"یوزرنیم": f"@{me.username}"})

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        scheduler.shutdown(wait=False)
        await close_redis()
        await bot.session.close()
        log.info("bot_stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        log.info("shutdown_requested")
