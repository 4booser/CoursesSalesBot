from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Attachment


class AttachmentRepository:
    """Data access for files attached to a group or a video.

    Each attachment has exactly one parent: ``group_id`` xor ``video_id``.
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, attachment_id: int) -> Attachment | None:
        return await self.session.get(Attachment, attachment_id)

    async def list_by_group(self, group_id: int, active_only: bool = True) -> list[Attachment]:
        return await self._list(Attachment.group_id == group_id, active_only)

    async def list_by_video(self, video_id: int, active_only: bool = True) -> list[Attachment]:
        return await self._list(Attachment.video_id == video_id, active_only)

    async def _list(self, where, active_only: bool) -> list[Attachment]:
        stmt = select(Attachment).where(where)
        if active_only:
            stmt = stmt.where(Attachment.is_active.is_(True))
        stmt = stmt.order_by(Attachment.position, Attachment.id)
        result = await self.session.scalars(stmt)
        return list(result.all())

    async def next_position(self, group_id: int | None, video_id: int | None) -> int:
        where = Attachment.group_id == group_id if group_id is not None else Attachment.video_id == video_id
        stmt = select(func.coalesce(func.max(Attachment.position), -1) + 1).where(where)
        return int(await self.session.scalar(stmt) or 0)

    async def create(
        self,
        *,
        group_id: int | None,
        video_id: int | None,
        title: str,
        media_type: str,
        file_id: str,
        file_unique_id: str | None,
        file_name: str | None,
        mime_type: str | None,
        file_size: int | None,
        min_tier: str,
    ) -> Attachment:
        attachment = Attachment(
            group_id=group_id,
            video_id=video_id,
            title=title,
            media_type=media_type,
            file_id=file_id,
            file_unique_id=file_unique_id,
            file_name=file_name,
            mime_type=mime_type,
            file_size=file_size,
            min_tier=min_tier,
            position=await self.next_position(group_id, video_id),
        )
        self.session.add(attachment)
        await self.session.flush()
        return attachment

    async def update(
        self,
        attachment: Attachment,
        title: str | None = None,
        min_tier: str | None = None,
        is_active: bool | None = None,
    ) -> Attachment:
        if title is not None:
            attachment.title = title
        if min_tier is not None:
            attachment.min_tier = min_tier
        if is_active is not None:
            attachment.is_active = is_active
        await self.session.flush()
        return attachment

    async def delete(self, attachment: Attachment) -> None:
        await self.session.delete(attachment)
        await self.session.flush()
