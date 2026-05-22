from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from secrets import token_urlsafe

from app.repositories.access_repository import AccessRepository
from app.repositories.course_repository import CourseRepository
from app.repositories.payment_event_repository import PaymentEventRepository
from app.repositories.token_course_repository import TokenCourseRepository
from app.repositories.token_repository import TokenRepository


@dataclass(frozen=True)
class CourseInfo:
    id: str
    title: str
    description: str | None
    invite_link: str | None
    telegram_chat_id: int | None


@dataclass(frozen=True)
class CreatedToken:
    token_id: int
    raw_token: str
    token_preview: str
    courses: list[CourseInfo]
    payment_id: str | None

    @property
    def course_ids(self) -> list[str]:
        return [course.id for course in self.courses]


@dataclass(frozen=True)
class ActivatedAccess:
    telegram_id: int
    courses: list[CourseInfo]
    token_id: int

    @property
    def course_ids(self) -> list[str]:
        return [course.id for course in self.courses]


class TokenAlreadyExistsError(Exception):
    pass


class CoursesNotFoundError(Exception):
    def __init__(self, course_ids: list[str]):
        self.course_ids = course_ids
        super().__init__(f"Courses not found or inactive: {', '.join(course_ids)}")


class TokenService:
    TOKEN_BYTES = 32

    def __init__(
        self,
        token_repository: TokenRepository,
        access_repository: AccessRepository,
        token_course_repository: TokenCourseRepository,
        course_repository: CourseRepository,
        payment_event_repository: PaymentEventRepository | None = None,
    ):
        self.token_repository = token_repository
        self.access_repository = access_repository
        self.token_course_repository = token_course_repository
        self.course_repository = course_repository
        self.payment_event_repository = payment_event_repository

    async def create_token(
        self,
        created_by_tg_id: int,
        course_ids: list[str],
        payment_id: str | None = None,
    ) -> CreatedToken:
        normalized_course_ids = self.normalize_course_ids(course_ids)
        normalized_payment_id = payment_id.strip() if payment_id else None

        if normalized_payment_id is not None:
            existing_token = await self.token_repository.get_by_payment_id(
                normalized_payment_id
            )
            if existing_token is not None:
                await self.log_event(
                    event_type="token_create",
                    status="duplicate_payment",
                    payment_id=normalized_payment_id,
                    course_ids=normalized_course_ids,
                    message="Token for this payment_id already exists",
                )
                raise TokenAlreadyExistsError(
                    "Token for this payment_id already exists"
                )

        active_courses = await self.course_repository.get_active_many_by_ids(
            normalized_course_ids
        )
        active_course_ids = {course.id for course in active_courses}
        missing_course_ids = [
            course_id
            for course_id in normalized_course_ids
            if course_id not in active_course_ids
        ]
        if missing_course_ids:
            await self.log_event(
                event_type="token_create",
                status="courses_not_found",
                payment_id=normalized_payment_id,
                course_ids=normalized_course_ids,
                message=f"Missing courses: {', '.join(missing_course_ids)}",
            )
            raise CoursesNotFoundError(missing_course_ids)

        courses_by_id = {course.id: self.to_course_info(course) for course in active_courses}
        ordered_courses = [courses_by_id[course_id] for course_id in normalized_course_ids]

        for _ in range(5):
            raw_token = token_urlsafe(self.TOKEN_BYTES)
            token_hash = self.hash_token(raw_token)
            exists = await self.token_repository.exists_by_hash(token_hash)
            if exists:
                continue

            token_preview = self.make_preview(raw_token)
            token = await self.token_repository.create(
                token_hash=token_hash,
                token_preview=token_preview,
                created_by_tg_id=created_by_tg_id,
                course_id=normalized_course_ids[0],
                payment_id=normalized_payment_id,
            )
            await self.token_course_repository.create_many(
                token_id=token.id,
                course_ids=normalized_course_ids,
            )
            await self.log_event(
                event_type="token_create",
                status="success",
                payment_id=normalized_payment_id,
                course_ids=normalized_course_ids,
                token_id=token.id,
            )

            return CreatedToken(
                token_id=token.id,
                raw_token=raw_token,
                token_preview=token_preview,
                courses=ordered_courses,
                payment_id=token.payment_id,
            )

        raise RuntimeError("Failed to generate unique token")

    async def activate_token(
        self,
        raw_token: str,
        used_by_tg_id: int,
    ) -> ActivatedAccess | None:
        cleaned_token = raw_token.strip()
        if not cleaned_token:
            return None

        token_hash = self.hash_token(cleaned_token)
        token = await self.token_repository.get_by_hash_for_update(token_hash)

        if token is None or token.is_used:
            return None

        course_ids = await self.token_course_repository.get_course_ids_by_token_id(
            token.id
        )
        if not course_ids:
            course_ids = [token.course_id]

        courses = await self.course_repository.get_many_by_ids(course_ids)
        courses_by_id = {course.id: self.to_course_info(course) for course in courses}
        ordered_courses = [courses_by_id[course_id] for course_id in course_ids if course_id in courses_by_id]

        token.is_used = True
        token.used_by_tg_id = used_by_tg_id
        token.used_at = datetime.now(UTC)

        await self.access_repository.create_many_missing(
            telegram_id=used_by_tg_id,
            course_ids=course_ids,
            token_id=token.id,
        )
        await self.log_event(
            event_type="token_activate",
            status="success",
            payment_id=token.payment_id,
            course_ids=course_ids,
            telegram_id=used_by_tg_id,
            token_id=token.id,
        )

        return ActivatedAccess(
            telegram_id=used_by_tg_id,
            courses=ordered_courses,
            token_id=token.id,
        )

    async def get_user_courses(self, telegram_id: int) -> list[CourseInfo]:
        accesses = await self.access_repository.get_user_courses(telegram_id)
        course_ids = [access.course_id for access in accesses]
        courses = await self.course_repository.get_many_by_ids(course_ids)
        courses_by_id = {course.id: self.to_course_info(course) for course in courses}
        return [courses_by_id[course_id] for course_id in course_ids if course_id in courses_by_id]

    async def has_access(self, telegram_id: int, course_id: str) -> bool:
        normalized_course_id = self.normalize_course_id(course_id)
        access = await self.access_repository.get_by_user_and_course(
            telegram_id=telegram_id,
            course_id=normalized_course_id,
        )
        return access is not None

    async def log_event(
        self,
        event_type: str,
        status: str,
        payment_id: str | None = None,
        course_ids: list[str] | None = None,
        telegram_id: int | None = None,
        token_id: int | None = None,
        message: str | None = None,
    ) -> None:
        if self.payment_event_repository is None:
            return

        await self.payment_event_repository.create(
            event_type=event_type,
            status=status,
            payment_id=payment_id,
            course_ids=course_ids,
            telegram_id=telegram_id,
            token_id=token_id,
            message=message,
        )

    @staticmethod
    def hash_token(token: str) -> str:
        return sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def make_preview(token: str) -> str:
        return f"{token[:6]}...{token[-4:]}"

    @staticmethod
    def to_course_info(course) -> CourseInfo:
        return CourseInfo(
            id=course.id,
            title=course.title,
            description=course.description,
            invite_link=course.invite_link,
            telegram_chat_id=course.telegram_chat_id,
        )

    @staticmethod
    def normalize_course_id(course_id: str) -> str:
        normalized = course_id.strip()
        if not normalized:
            raise ValueError("course_id must not be empty")
        return normalized

    @classmethod
    def normalize_course_ids(cls, course_ids: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()

        for course_id in course_ids:
            normalized_course_id = cls.normalize_course_id(course_id)
            if normalized_course_id in seen:
                continue
            normalized.append(normalized_course_id)
            seen.add(normalized_course_id)

        if not normalized:
            raise ValueError("course_ids must not be empty")

        return normalized
