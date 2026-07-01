import hmac
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.limiter import RedisRateLimiter
from app.config import settings
from app.database.session import engine, session_maker
from app.repositories.payment_event_repository import PaymentEventRepository
from app.repositories.tier_access_repository import TierAccessRepository
from app.repositories.tier_flag_repository import TierFlagRepository
from app.repositories.token_repository import TokenRepository
from app.services.token_service import (
    CreatedToken,
    InvalidTierError,
    TokenAlreadyExistsError,
    TokenService,
)
from app.tiers import ALL_TIERS, ASSIGNABLE_TIERS


class CreateTokenRequest(BaseModel):
    tier: str = Field(min_length=1, max_length=16)
    duration_days: int | None = Field(default=None, gt=0, le=3650)
    payment_id: str | None = Field(default=None, max_length=128)


class CreateTokenResponse(BaseModel):
    token: str
    tier: str
    duration_days: int
    payment_id: str | None
    token_preview: str
    telegram_link: str


class AccessCheckResponse(BaseModel):
    telegram_id: int
    has_access: bool
    tier: str | None
    expires_at: datetime | None
    frozen: bool = False


class FreezeTierRequest(BaseModel):
    frozen: bool


class FreezeTierResponse(BaseModel):
    tier: str
    frozen: bool


class FrozenTiersResponse(BaseModel):
    frozen: list[str]


class SetUserTierRequest(BaseModel):
    tier: str = Field(min_length=1, max_length=16)


class SetUserTierResponse(BaseModel):
    telegram_id: int
    tier: str | None
    expires_at: datetime | None


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


app = FastAPI(title="Courses Sales Bot API", version="2.0.0", lifespan=lifespan)


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
    if not hmac.compare_digest(x_api_key or "", settings.site_api_key):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")


def build_token_service(session: AsyncSession) -> TokenService:
    return TokenService(
        token_repository=TokenRepository(session),
        tier_access_repository=TierAccessRepository(session),
        payment_event_repository=PaymentEventRepository(session),
        tier_flag_repository=TierFlagRepository(session),
    )


def build_telegram_link(raw_token: str) -> str:
    if not settings.BOT_USERNAME:
        return ""
    username = settings.BOT_USERNAME.removeprefix("@")
    return f"https://t.me/{username}?start={raw_token}"


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/tokens", response_model=CreateTokenResponse, dependencies=[Depends(authorize_site)])
async def create_token(request: CreateTokenRequest, session: AsyncSession = Depends(get_session)) -> CreateTokenResponse:
    service = build_token_service(session)

    try:
        created: CreatedToken = await service.create_token(
            created_by_tg_id=0,
            tier=request.tier,
            payment_id=request.payment_id,
            duration_days=request.duration_days,
        )
    except TokenAlreadyExistsError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    except InvalidTierError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{error}. Allowed tiers: {', '.join(ALL_TIERS)}",
        ) from error

    return CreateTokenResponse(
        token=created.raw_token,
        tier=created.tier,
        duration_days=created.duration_days,
        payment_id=created.payment_id,
        token_preview=created.token_preview,
        telegram_link=build_telegram_link(created.raw_token),
    )


@app.get("/api/access/check", response_model=AccessCheckResponse, dependencies=[Depends(authorize_site)])
async def check_access(
    telegram_id: int = Query(gt=0),
    session: AsyncSession = Depends(get_session),
) -> AccessCheckResponse:
    service = build_token_service(session)
    access = await service.get_active_access(telegram_id)
    frozen = await service.is_tier_frozen(access.tier) if access else False
    return AccessCheckResponse(
        telegram_id=telegram_id,
        has_access=access is not None,
        tier=access.tier if access else None,
        expires_at=access.expires_at if access else None,
        frozen=frozen,
    )


@app.post("/api/tiers/{tier}/freeze", response_model=FreezeTierResponse, dependencies=[Depends(authorize_site)])
async def set_tier_freeze(
    tier: str,
    request: FreezeTierRequest,
    session: AsyncSession = Depends(get_session),
) -> FreezeTierResponse:
    normalized = tier.strip().lower()
    if normalized not in ALL_TIERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown tier '{tier}'. Allowed tiers: {', '.join(ALL_TIERS)}",
        )
    await TierFlagRepository(session).set_frozen(normalized, request.frozen)
    return FreezeTierResponse(tier=normalized, frozen=request.frozen)


@app.get("/api/tiers/freeze", response_model=FrozenTiersResponse, dependencies=[Depends(authorize_site)])
async def list_frozen_tiers(session: AsyncSession = Depends(get_session)) -> FrozenTiersResponse:
    frozen = await TierFlagRepository(session).frozen_tiers()
    return FrozenTiersResponse(frozen=sorted(frozen))


@app.post(
    "/api/users/{telegram_id}/tier",
    response_model=SetUserTierResponse,
    dependencies=[Depends(authorize_site)],
)
async def set_user_tier(
    telegram_id: int,
    request: SetUserTierRequest,
    session: AsyncSession = Depends(get_session),
) -> SetUserTierResponse:
    normalized = request.tier.strip().lower()
    if normalized not in ASSIGNABLE_TIERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown tier '{request.tier}'. Allowed: {', '.join(ASSIGNABLE_TIERS)}",
        )
    service = build_token_service(session)
    try:
        access = await service.set_tier(telegram_id=telegram_id, tier=normalized)
    except InvalidTierError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    return SetUserTierResponse(
        telegram_id=telegram_id,
        tier=access.tier if access else None,
        expires_at=access.expires_at if access else None,
    )
