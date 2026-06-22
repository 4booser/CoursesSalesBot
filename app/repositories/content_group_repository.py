from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import ContentGroup, Video


class ContentGroupRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, group_id: int) -> ContentGroup | None:
        return await self.session.get(ContentGroup, group_id)

    async def list_children(
        self,
        parent_id: int | None,
        active_only: bool = True,
    ) -> list[ContentGroup]:
        stmt = select(ContentGroup).where(ContentGroup.parent_id.is_(parent_id) if parent_id is None
                                          else ContentGroup.parent_id == parent_id)
        if active_only:
            stmt = stmt.where(ContentGroup.is_active.is_(True))
        stmt = stmt.order_by(ContentGroup.position, ContentGroup.id)
        result = await self.session.scalars(stmt)
        return list(result.all())

    async def next_position(self, parent_id: int | None) -> int:
        stmt = select(func.coalesce(func.max(ContentGroup.position), -1) + 1)
        stmt = stmt.where(ContentGroup.parent_id.is_(parent_id) if parent_id is None
                          else ContentGroup.parent_id == parent_id)
        return int(await self.session.scalar(stmt) or 0)

    async def create(
        self,
        title: str,
        parent_id: int | None,
        min_tier: str,
    ) -> ContentGroup:
        group = ContentGroup(
            title=title,
            parent_id=parent_id,
            min_tier=min_tier,
            position=await self.next_position(parent_id),
        )
        self.session.add(group)
        await self.session.flush()
        return group

    async def update(
        self,
        group: ContentGroup,
        title: str | None = None,
        min_tier: str | None = None,
        is_active: bool | None = None,
    ) -> ContentGroup:
        if title is not None:
            group.title = title
        if min_tier is not None:
            group.min_tier = min_tier
        if is_active is not None:
            group.is_active = is_active
        await self.session.flush()
        return group

    async def delete(self, group: ContentGroup) -> None:
        await self.session.delete(group)
        await self.session.flush()

    async def count_videos(self, group_id: int) -> int:
        stmt = select(func.count(Video.id)).where(Video.group_id == group_id)
        return int(await self.session.scalar(stmt) or 0)
