import asyncio
import logging

from aiogram import Bot, Dispatcher

from app.config import settings
from app.database.session import create_tables, engine, session_maker
from app.handlers import routers
from app.middlewares.db import DbMiddleware


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    await create_tables()

    bot = Bot(token=settings.BOT_TOKEN)
    dp = Dispatcher()

    dp.update.middleware(DbMiddleware(session_maker))
    dp.include_routers(*routers)

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)

    finally:
        await bot.session.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())