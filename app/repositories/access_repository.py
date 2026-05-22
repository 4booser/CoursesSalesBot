from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import UserCourseAccess


class AccessRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_user_and_course(
        self,
        telegram_id: int,
        course_id: str,
    ) -> UserCourseAccess | None:
        stmt = select(UserCourseAccess).where(
            UserCourseAccess.telegram_id == telegram_id,
            UserCourseAccess.course_id == course_id,
        )

        return await self.session.scalar(stmt)

    async def get_user_courses(
        self,
        telegram_id: int,
    ) -> list[UserCourseAccess]:
        stmt = (
            select(UserCourseAccess)
            .where(UserCourseAccess.telegram_id == telegram_id)
            .order_by(UserCourseAccess.created_at.desc())
        )

        result = await self.session.scalars(stmt)
        return list(result.all())

    async def create(
        self,
        telegram_id: int,
        course_id: str,
        token_id: int,
    ) -> UserCourseAccess:
        access = UserCourseAccess(
            telegram_id=telegram_id,
            course_id=course_id,
            token_id=token_id,
        )

        self.session.add(access)
        await self.session.flush()

        return access
