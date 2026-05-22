from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.repositories.token_repository import TokenRepository
from app.services.token_service import TokenService


class DbMiddleware(BaseMiddleware):
    def __init__(
        self,
        session_maker: async_sessionmaker[AsyncSession],
    ):
        self.session_maker = session_maker

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        async with self.session_maker() as session:
            token_repository = TokenRepository(session)
            token_service = TokenService(token_repository)

            data["session"] = session
            data["token_service"] = token_service

            try:
                result = await handler(event, data)
                await session.commit()
                return result

            except Exception:
                await session.rollback()
                raise