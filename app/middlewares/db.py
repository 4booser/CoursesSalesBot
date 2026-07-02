from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.repositories.attachment_repository import AttachmentRepository
from app.repositories.content_group_repository import ContentGroupRepository
from app.repositories.payment_event_repository import PaymentEventRepository
from app.repositories.tier_access_repository import TierAccessRepository
from app.repositories.tier_flag_repository import TierFlagRepository
from app.repositories.token_repository import TokenRepository
from app.repositories.video_repository import VideoRepository
from app.services.catalog_service import CatalogService
from app.services.token_service import TokenService


class DbMiddleware(BaseMiddleware):
    def __init__(self, session_maker: async_sessionmaker[AsyncSession]):
        self.session_maker = session_maker

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        async with self.session_maker() as session:
            content_group_repository = ContentGroupRepository(session)
            video_repository = VideoRepository(session)
            attachment_repository = AttachmentRepository(session)
            tier_flag_repository = TierFlagRepository(session)

            token_service = TokenService(
                token_repository=TokenRepository(session),
                tier_access_repository=TierAccessRepository(session),
                payment_event_repository=PaymentEventRepository(session),
                tier_flag_repository=tier_flag_repository,
            )
            catalog_service = CatalogService(
                content_group_repository=content_group_repository,
                video_repository=video_repository,
                attachment_repository=attachment_repository,
            )

            data["session"] = session
            data["token_service"] = token_service
            data["catalog_service"] = catalog_service
            data["content_group_repository"] = content_group_repository
            data["video_repository"] = video_repository
            data["attachment_repository"] = attachment_repository
            data["tier_flag_repository"] = tier_flag_repository

            try:
                result = await handler(event, data)
                await session.commit()
                return result
            except Exception:
                await session.rollback()
                raise
