from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Course


class CourseRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, course_id: str) -> Course | None:
        return await self.session.get(Course, course_id)

    async def get_many_by_ids(self, course_ids: list[str]) -> list[Course]:
        if not course_ids:
            return []

        stmt = select(Course).where(Course.id.in_(course_ids))
        result = await self.session.scalars(stmt)
        return list(result.all())

    async def get_active_many_by_ids(self, course_ids: list[str]) -> list[Course]:
        if not course_ids:
            return []

        stmt = select(Course).where(
            Course.id.in_(course_ids),
            Course.is_active.is_(True),
        )
        result = await self.session.scalars(stmt)
        return list(result.all())

    async def list_active(self) -> list[Course]:
        stmt = select(Course).where(Course.is_active.is_(True)).order_by(Course.id)
        result = await self.session.scalars(stmt)
        return list(result.all())

    async def upsert(
        self,
        course_id: str,
        title: str,
        description: str | None = None,
        invite_link: str | None = None,
        is_active: bool = True,
    ) -> Course:
        course = await self.get_by_id(course_id)

        if course is None:
            course = Course(
                id=course_id,
                title=title,
                description=description,
                invite_link=invite_link,
                is_active=is_active,
            )
            self.session.add(course)
        else:
            course.title = title
            course.description = description
            course.invite_link = invite_link
            course.is_active = is_active

        await self.session.flush()
        return course
