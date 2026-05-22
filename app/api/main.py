from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.limiter import RedisRateLimiter
from app.config import settings
from app.database.session import engine, session_maker
from app.repositories.access_repository import AccessRepository
from app.repositories.course_repository import CourseRepository
from app.repositories.payment_event_repository import PaymentEventRepository
from app.repositories.token_course_repository import TokenCourseRepository
from app.repositories.token_repository import TokenRepository
from app.services.token_service import (
    CoursesNotFoundError,
    CreatedToken,
    TokenAlreadyExistsError,
    TokenService,
)


class CreateTokenRequest(BaseModel):
    course_id: str | None = Field(default=None, min_length=1, max_length=64)
    course_ids: list[str] | None = Field(default=None, min_length=1, max_length=50)
    payment_id: str | None = Field(default=None, max_length=128)

    @model_validator(mode="after")
    def validate_courses(self):
        if self.course_ids is None and self.course_id is None:
            raise ValueError("course_id or course_ids is required")
        return self

    def get_course_ids(self) -> list[str]:
        if self.course_ids is not None:
            return self.course_ids
        return [self.course_id or ""]


class CreateTokenResponse(BaseModel):
    token: str
    course_ids: list[str]
    payment_id: str | None
    token_preview: str
    telegram_link: str


class AccessCheckResponse(BaseModel):
    has_access: bool
    telegram_id: int
    course_id: str


class BulkAccessCheckRequest(BaseModel):
    telegram_id: int = Field(gt=0)
    course_ids: list[str] = Field(min_length=1, max_length=50)


class BulkAccessCheckResponse(BaseModel):
    telegram_id: int
    access: dict[str, bool]


class UpsertCourseRequest(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=2000)
    invite_link: str | None = Field(default=None, max_length=512)
    is_active: bool = True


class CourseResponse(BaseModel):
    id: str
    title: str
    description: str | None
    invite_link: str | None
    is_active: bool


rate_limiter = RedisRateLimiter(
    redis_url=settings.REDIS_URL,
    limit=settings.RATE_LIMIT_REQUESTS,
    window_seconds=settings.RATE_LIMIT_WINDOW_SECONDS,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await rate_limiter.close()
    await engine.dispose()


app = FastAPI(
    title="Courses Sales Bot API",
    version="1.0.0",
    lifespan=lifespan,
)


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    if request.url.path.startswith("/api/"):
        api_key = request.headers.get("x-api-key")
        client_host = request.client.host if request.client else "unknown"
        await rate_limiter.check(api_key or client_host)

    return await call_next(request)


async def get_session():
    async with session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def authorize_site(x_api_key: str | None = Header(default=None)) -> None:
    if not settings.site_api_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="SITE_API_KEY is not configured",
        )

    if x_api_key != settings.site_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )


def build_token_service(session: AsyncSession) -> TokenService:
    return TokenService(
        token_repository=TokenRepository(session),
        access_repository=AccessRepository(session),
        token_course_repository=TokenCourseRepository(session),
        course_repository=CourseRepository(session),
        payment_event_repository=PaymentEventRepository(session),
    )


def build_telegram_link(raw_token: str) -> str:
    if not settings.BOT_USERNAME:
        return ""

    username = settings.BOT_USERNAME.removeprefix("@")
    return f"https://t.me/{username}?start={raw_token}"


def to_course_response(course) -> CourseResponse:
    return CourseResponse(
        id=course.id,
        title=course.title,
        description=course.description,
        invite_link=course.invite_link,
        is_active=course.is_active,
    )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/courses", response_model=CourseResponse, dependencies=[Depends(authorize_site)])
async def upsert_course(request: UpsertCourseRequest, session: AsyncSession = Depends(get_session)) -> CourseResponse:
    course_repository = CourseRepository(session)
    course = await course_repository.upsert(
        course_id=request.id.strip(),
        title=request.title.strip(),
        description=request.description,
        invite_link=request.invite_link,
        is_active=request.is_active,
    )
    return to_course_response(course)


@app.get("/api/courses", response_model=list[CourseResponse], dependencies=[Depends(authorize_site)])
async def list_courses(session: AsyncSession = Depends(get_session)) -> list[CourseResponse]:
    course_repository = CourseRepository(session)
    courses = await course_repository.list_active()
    return [to_course_response(course) for course in courses]


@app.get("/api/courses/{course_id}", response_model=CourseResponse, dependencies=[Depends(authorize_site)])
async def get_course(course_id: str, session: AsyncSession = Depends(get_session)) -> CourseResponse:
    course_repository = CourseRepository(session)
    course = await course_repository.get_by_id(course_id.strip())
    if course is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")
    return to_course_response(course)


@app.post("/api/tokens", response_model=CreateTokenResponse, dependencies=[Depends(authorize_site)])
async def create_token(request: CreateTokenRequest, session: AsyncSession = Depends(get_session)) -> CreateTokenResponse:
    service = build_token_service(session)

    try:
        created_token: CreatedToken = await service.create_token(
            created_by_tg_id=0,
            course_ids=request.get_course_ids(),
            payment_id=request.payment_id,
        )
    except TokenAlreadyExistsError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    except CoursesNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error

    return CreateTokenResponse(
        token=created_token.raw_token,
        course_ids=created_token.course_ids,
        payment_id=created_token.payment_id,
        token_preview=created_token.token_preview,
        telegram_link=build_telegram_link(created_token.raw_token),
    )


@app.get("/api/access/check", response_model=AccessCheckResponse, dependencies=[Depends(authorize_site)])
async def check_access(
    telegram_id: int = Query(gt=0),
    course_id: str = Query(min_length=1, max_length=64),
    session: AsyncSession = Depends(get_session),
) -> AccessCheckResponse:
    service = build_token_service(session)
    has_access = await service.has_access(telegram_id=telegram_id, course_id=course_id)
    return AccessCheckResponse(has_access=has_access, telegram_id=telegram_id, course_id=course_id.strip())


@app.post("/api/access/check", response_model=BulkAccessCheckResponse, dependencies=[Depends(authorize_site)])
async def check_bulk_access(
    request: BulkAccessCheckRequest,
    session: AsyncSession = Depends(get_session),
) -> BulkAccessCheckResponse:
    service = build_token_service(session)
    access: dict[str, bool] = {}

    for course_id in request.course_ids:
        access[course_id] = await service.has_access(telegram_id=request.telegram_id, course_id=course_id)

    return BulkAccessCheckResponse(telegram_id=request.telegram_id, access=access)
