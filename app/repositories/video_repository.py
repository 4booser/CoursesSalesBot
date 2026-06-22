from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Video


class VideoRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, video_id: int) -> Video | None:
        return await self.session.get(Video, video_id)

    async def list_by_group(self, group_id: int, active_only: bool = True) -> list[Video]:
        stmt = select(Video).where(Video.group_id == group_id)
        if active_only:
            stmt = stmt.where(Video.is_active.is_(True))
        stmt = stmt.order_by(Video.position, Video.id)
        result = await self.session.scalars(stmt)
        return list(result.all())

    async def next_position(self, group_id: int) -> int:
        stmt = select(func.coalesce(func.max(Video.position), -1) + 1).where(Video.group_id == group_id)
        return int(await self.session.scalar(stmt) or 0)

    async def create(
        self,
        group_id: int,
        title: str,
        youtube_url: str,
        thumbnail_url: str | None,
        min_tier: str,
    ) -> Video:
        video = Video(
            group_id=group_id,
            title=title,
            youtube_url=youtube_url,
            thumbnail_url=thumbnail_url,
            min_tier=min_tier,
            position=await self.next_position(group_id),
        )
        self.session.add(video)
        await self.session.flush()
        return video

    async def update(
        self,
        video: Video,
        title: str | None = None,
        min_tier: str | None = None,
        is_active: bool | None = None,
    ) -> Video:
        if title is not None:
            video.title = title
        if min_tier is not None:
            video.min_tier = min_tier
        if is_active is not None:
            video.is_active = is_active
        await self.session.flush()
        return video

    async def delete(self, video: Video) -> None:
        await self.session.delete(video)
        await self.session.flush()
