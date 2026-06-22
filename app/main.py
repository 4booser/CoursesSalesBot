import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar

from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramNetworkError

from app.config import settings
from app.database.session import engine, session_maker
from app.handlers import routers
from app.middlewares.db import DbMiddleware

logger = logging.getLogger(__name__)
T = TypeVar("T")

TELEGRAM_NETWORK_RETRY_SECONDS = 10


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


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    bot = Bot(token=settings.BOT_TOKEN)
    dp = Dispatcher()

    dp.update.middleware(DbMiddleware(session_maker))
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
        await bot.session.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
