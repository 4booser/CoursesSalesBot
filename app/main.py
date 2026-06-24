import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar

from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramNetworkError
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import ErrorEvent
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.config import settings
from app.database.session import engine, session_maker
from app.handlers import routers
from app.middlewares.db import DbMiddleware

logger = logging.getLogger(__name__)
T = TypeVar("T")

TELEGRAM_NETWORK_RETRY_SECONDS = 10

# Fixed app-wide key for a Postgres session-level advisory lock. Only one bot
# process can hold it at a time, so a second instance refuses to start instead of
# fighting over getUpdates (the "every other message" duplicate-poller bug).
BOT_SINGLETON_LOCK_KEY = 0x42C0FFEE


async def retry_telegram_network_call(
    operation_name: str,
    operation: Callable[[], Awaitable[T]],
) -> T:
    while True:
        try:
            return await operation()
        except TelegramNetworkError:
            logger.exception(
                "Telegram network error during %s. Retrying in %s seconds.",
                operation_name,
                TELEGRAM_NETWORK_RETRY_SECONDS,
            )
            await asyncio.sleep(TELEGRAM_NETWORK_RETRY_SECONDS)


async def acquire_singleton_lock() -> AsyncConnection | None:
    """Take a process-wide advisory lock, or return None if another bot holds it.

    The lock lives on the returned connection's DB session; keep the connection
    open for the whole process lifetime and close it on shutdown to release.
    """
    connection = await engine.connect()
    locked = await connection.scalar(
        text("SELECT pg_try_advisory_lock(:key)"),
        {"key": BOT_SINGLETON_LOCK_KEY},
    )
    if not locked:
        await connection.close()
        return None
    return connection


def register_error_handler(dp: Dispatcher) -> None:
    @dp.errors()
    async def on_error(event: ErrorEvent) -> bool:
        logger.exception("Unhandled update error: %s", event.exception)
        update = event.update
        try:
            if update.callback_query is not None:
                await update.callback_query.answer(
                    "Сталася помилка, спробуй ще раз 🙏", show_alert=True
                )
            elif update.message is not None:
                await update.message.answer("Сталася помилка, спробуй ще раз 🙏")
        except Exception:
            logger.exception("Failed to notify user about an error")
        return True


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    lock_connection = await acquire_singleton_lock()
    if lock_connection is None:
        logger.error(
            "Another bot instance is already running (advisory lock held). Exiting."
        )
        await engine.dispose()
        return

    bot = Bot(token=settings.BOT_TOKEN)
    storage = RedisStorage.from_url(settings.REDIS_URL)
    dp = Dispatcher(storage=storage)

    dp.update.middleware(DbMiddleware(session_maker))
    register_error_handler(dp)
    dp.include_routers(*routers)

    try:
        await retry_telegram_network_call(
            "delete_webhook",
            lambda: bot.delete_webhook(drop_pending_updates=True),
        )

        while True:
            try:
                await dp.start_polling(bot)
                break
            except TelegramNetworkError:
                logger.exception(
                    "Telegram network error during polling. Retrying in %s seconds.",
                    TELEGRAM_NETWORK_RETRY_SECONDS,
                )
                await asyncio.sleep(TELEGRAM_NETWORK_RETRY_SECONDS)

    finally:
        await storage.close()
        await bot.session.close()
        await lock_connection.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
