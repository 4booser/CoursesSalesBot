from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import TokenCourse


class TokenCourseRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_many(self, token_id: int, course_ids: list[str]) -> list[TokenCourse]:
        token_courses = [
            TokenCourse(token_id=token_id, course_id=course_id)
            for course_id in course_ids
        ]

        self.session.add_all(token_courses)
        await self.session.flush()
        return token_courses

    async def get_course_ids_by_token_id(self, token_id: int) -> list[str]:
        stmt = select(TokenCourse.course_id).where(TokenCourse.token_id == token_id)
        result = await self.session.scalars(stmt)
        return list(result.all())
