"""Read model for the in-bot video catalog, with tier gating.

A group or video is visible to a user when the user's tier rank is greater than
or equal to the item's ``min_tier`` rank. Admin handlers bypass this service and
use the repositories directly (they see everything).
"""

from app.database.models import ContentGroup, Video
from app.repositories.content_group_repository import ContentGroupRepository
from app.repositories.video_repository import VideoRepository
from app.tiers import tier_rank


class CatalogService:
    def __init__(
        self,
        content_group_repository: ContentGroupRepository,
        video_repository: VideoRepository,
    ):
        self.content_group_repository = content_group_repository
        self.video_repository = video_repository

    async def visible_groups(self, parent_id: int | None, user_tier: str) -> list[ContentGroup]:
        rank = tier_rank(user_tier)
        groups = await self.content_group_repository.list_children(parent_id, active_only=True)
        return [group for group in groups if tier_rank(group.min_tier) <= rank]

    async def visible_videos(self, group_id: int, user_tier: str) -> list[Video]:
        rank = tier_rank(user_tier)
        videos = await self.video_repository.list_by_group(group_id, active_only=True)
        return [video for video in videos if tier_rank(video.min_tier) <= rank]

    async def get_group_if_visible(self, group_id: int, user_tier: str) -> ContentGroup | None:
        group = await self.content_group_repository.get_by_id(group_id)
        if group is None or not group.is_active:
            return None
        if tier_rank(group.min_tier) > tier_rank(user_tier):
            return None
        return group

    async def get_video_if_visible(self, video_id: int, user_tier: str) -> Video | None:
        video = await self.video_repository.get_by_id(video_id)
        if video is None or not video.is_active:
            return None
        if tier_rank(video.min_tier) > tier_rank(user_tier):
            return None
        return video
