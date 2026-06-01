"""
app.py — Main entry point.
Starts aiogram bot, connects MongoDB, loads userbot sessions, starts scheduler.
"""

from __future__ import annotations
import asyncio
import sys

try:
    import uvloop
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
except ImportError:
    pass

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage

from config import config
from database import db
from services.userbot import userbot_manager
from services.notifier import notifier
from scheduler.tasks import task_scheduler
from utils.logger import logger, setup_python_logging

# Import routers
from handlers import start, setup, keywords, settings as settings_handler


async def on_startup(bot: Bot) -> None:
    """Run on bot startup."""
    logger.banner()

    # Connect to MongoDB
    logger.info("Connecting to MongoDB...")
    await db.connect()

    # Load userbot sessions from DB
    logger.info("Loading userbot sessions...")
    await userbot_manager.load_from_db()

    # Set bot reference in notifier
    notifier.set_bot(bot)

    # Start scheduler
    task_scheduler.start()
    task_scheduler.add_monitor_job(config.MONITOR_INTERVAL)

    # Register admins in DB
    for admin_id in config.ADMIN_IDS:
        await db.upsert_admin(admin_id)

    # Log startup
    await db.write_log("INFO", "Bot started successfully")

    me = await bot.get_me()
    logger.success(f"Bot started: @{me.username} (id={me.id})")
    logger.info(f"Admin IDs: {config.ADMIN_IDS}")
    logger.info(f"Monitor interval: {config.MONITOR_INTERVAL}s")

    # Notify admins
    for admin_id in config.ADMIN_IDS:
        try:
            has_session = userbot_manager.has_session(admin_id)
            status = "🟢 Userbot Connected" if has_session else "🔴 No Userbot Session (use /setup)"
            await bot.send_message(
                admin_id,
                f"<b>🚀 TG Monitor Started</b>\n\n{status}",
                parse_mode="HTML",
            )
        except Exception as exc:
            logger.warning(f"Could not notify admin {admin_id}: {exc}")


async def on_shutdown(bot: Bot) -> None:
    """Graceful shutdown."""
    logger.info("Shutting down...")
    task_scheduler.stop()
    await userbot_manager.shutdown()
    await db.disconnect()
    await db.write_log("INFO", "Bot stopped")
    logger.info("Shutdown complete.")


def build_dispatcher() -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())

    # Register startup/shutdown hooks
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    # Include routers
    dp.include_router(start.router)
    dp.include_router(setup.router)
    dp.include_router(keywords.router)
    dp.include_router(settings_handler.router)

    return dp


async def main() -> None:
    # Validate configuration
    try:
        config.validate()
    except ValueError as e:
        print(f"[ERROR] Config error: {e}")
        sys.exit(1)

    setup_python_logging()

    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = build_dispatcher()

    logger.info("Starting polling...")
    try:
        await dp.start_polling(bot, allowed_updates=["message", "callback_query"])
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
