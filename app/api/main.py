from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.session import create_tables, engine, session_maker
from app.repositories.access_repository import AccessRepository
from app.repositories.token_repository import TokenRepository
from app.services.token_service import (
    CreatedToken,
    TokenAlreadyExistsError,
    TokenService,
)


class CreateTokenRequest(BaseModel):
    course_id: str = Field(min_length=1, max_length=64)
    payment_id: str | None = Field(default=None, max_length=128)


class CreateTokenResponse(BaseModel):
    token: str
    course_id: str
    payment_id: str | None
    token_preview: str
    telegram_link: str


class AccessCheckResponse(BaseModel):
    has_access: bool
    telegram_id: int
    course_id: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_tables()
    yield
    await engine.dispose()


app = FastAPI(
    title="Courses Sales Bot API",
    version="1.0.0",
    lifespan=lifespan,
)


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
    )


def build_telegram_link(raw_token: str) -> str:
    if not settings.BOT_USERNAME:
        return ""

    username = settings.BOT_USERNAME.removeprefix("@")
    return f"https://t.me/{username}?start={raw_token}"


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post(
    "/api/tokens",
    response_model=CreateTokenResponse,
    dependencies=[Depends(authorize_site)],
)
async def create_token(
    request: CreateTokenRequest,
    session: AsyncSession = Depends(get_session),
) -> CreateTokenResponse:
    service = build_token_service(session)

    try:
        created_token: CreatedToken = await service.create_token(
            created_by_tg_id=0,
            course_id=request.course_id,
            payment_id=request.payment_id,
        )
    except TokenAlreadyExistsError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error

    return CreateTokenResponse(
        token=created_token.raw_token,
        course_id=created_token.course_id,
        payment_id=created_token.payment_id,
        token_preview=created_token.token_preview,
        telegram_link=build_telegram_link(created_token.raw_token),
    )


@app.get(
    "/api/access/check",
    response_model=AccessCheckResponse,
    dependencies=[Depends(authorize_site)],
)
async def check_access(
    telegram_id: int = Query(gt=0),
    course_id: str = Query(min_length=1, max_length=64),
    session: AsyncSession = Depends(get_session),
) -> AccessCheckResponse:
    service = build_token_service(session)
    has_access = await service.has_access(
        telegram_id=telegram_id,
        course_id=course_id,
    )

    return AccessCheckResponse(
        has_access=has_access,
        telegram_id=telegram_id,
        course_id=course_id.strip(),
    )
