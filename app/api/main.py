from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.session import create_tables, engine, session_maker
from app.repositories.access_repository import AccessRepository
from app.repositories.token_repository import TokenRepository
from app.services.token_service import CreatedToken, TokenService


class CreateTokenRequest(BaseModel):
    course_id: str = Field(min_length=1, max_length=64)
    payment_id: str | None = Field(default=None, max_length=128)


class CreateTokenResponse(BaseModel):
    token: str
    course_id: str
    token_preview: str
    telegram_link: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_tables()
    yield
    await engine.dispose()


app = FastAPI(
    title="Courses Sales Bot API",
    version="0.1.0",
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
    if not settings.SITE_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="SITE_API_KEY is not configured",
        )

    if x_api_key != settings.SITE_API_KEY:
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

    # created_by_tg_id is 0 because the token is created by the external site API,
    # not by a Telegram admin command.
    created_token: CreatedToken = await service.create_token(
        created_by_tg_id=0,
        course_id=request.course_id.strip(),
    )

    return CreateTokenResponse(
        token=created_token.raw_token,
        course_id=created_token.course_id,
        token_preview=created_token.token_preview,
        telegram_link=build_telegram_link(created_token.raw_token),
    )
