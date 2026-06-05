"""Application entrypoint — builds the bot, dispatcher, middlewares and runs polling."""
from __future__ import annotations

import asyncio

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage

from app.core.config import settings
from app.core.logger import configure_logging, get_logger
from app.core.redis import close_redis, redis_client
from app.handlers import register_routers
from app.middlewares.ban import BanMiddleware
from app.middlewares.database import DatabaseMiddleware
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

    dp.include_router(errors_router)
    register_routers(dp)
    return dp


async def main() -> None:
    configure_logging()
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = build_dispatcher()

    scheduler = setup_scheduler()
    scheduler.start()

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
