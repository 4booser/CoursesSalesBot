"""Tier-based purchase tokens and access.

Flow:
- Site calls ``create_token(tier, payment_id)`` after a successful payment.
- A one-time opaque token is issued; only its sha256 hash is stored.
- User opens ``https://t.me/<bot>?start=<token>``; ``activate_token`` grants the
  tier for ``duration_days`` (expiry stored on ``user_tier_accesses``).
- Content gating reads the user's highest active tier via ``get_active_access``.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from secrets import token_urlsafe

from app.repositories.payment_event_repository import PaymentEventRepository
from app.repositories.tier_access_repository import TierAccessRepository
from app.repositories.token_repository import TokenRepository
from app.tiers import duration_days_for_tier, normalize_tier, tier_rank


@dataclass(frozen=True)
class CreatedToken:
    token_id: int
    raw_token: str
    token_preview: str
    tier: str
    duration_days: int
    payment_id: str | None


@dataclass(frozen=True)
class ActivatedAccess:
    telegram_id: int
    tier: str
    expires_at: datetime
    token_id: int


@dataclass(frozen=True)
class ActiveAccess:
    tier: str
    expires_at: datetime


class TokenAlreadyExistsError(Exception):
    pass


class InvalidTierError(Exception):
    pass


class TokenService:
    TOKEN_BYTES = 32

    def __init__(
        self,
        token_repository: TokenRepository,
        tier_access_repository: TierAccessRepository,
        payment_event_repository: PaymentEventRepository | None = None,
    ):
        self.token_repository = token_repository
        self.tier_access_repository = tier_access_repository
        self.payment_event_repository = payment_event_repository

    async def create_token(
        self,
        created_by_tg_id: int,
        tier: str,
        payment_id: str | None = None,
        duration_days: int | None = None,
    ) -> CreatedToken:
        try:
            normalized_tier = normalize_tier(tier)
        except ValueError as error:
            raise InvalidTierError(str(error)) from error

        resolved_duration = duration_days if duration_days and duration_days > 0 else duration_days_for_tier(normalized_tier)
        normalized_payment_id = payment_id.strip() if payment_id else None

        if normalized_payment_id is not None:
            existing_token = await self.token_repository.get_by_payment_id(normalized_payment_id)
            if existing_token is not None:
                await self.log_event(
                    event_type="token_create",
                    status="duplicate_payment",
                    payment_id=normalized_payment_id,
                    tier=normalized_tier,
                    message="Token for this payment_id already exists",
                )
                raise TokenAlreadyExistsError("Token for this payment_id already exists")

        for _ in range(5):
            raw_token = token_urlsafe(self.TOKEN_BYTES)
            token_hash = self.hash_token(raw_token)
            if await self.token_repository.exists_by_hash(token_hash):
                continue

            token_preview = self.make_preview(raw_token)
            token = await self.token_repository.create(
                token_hash=token_hash,
                token_preview=token_preview,
                created_by_tg_id=created_by_tg_id,
                tier=normalized_tier,
                duration_days=resolved_duration,
                payment_id=normalized_payment_id,
            )
            await self.log_event(
                event_type="token_create",
                status="success",
                payment_id=normalized_payment_id,
                tier=normalized_tier,
                token_id=token.id,
            )
            return CreatedToken(
                token_id=token.id,
                raw_token=raw_token,
                token_preview=token_preview,
                tier=normalized_tier,
                duration_days=resolved_duration,
                payment_id=token.payment_id,
            )

        raise RuntimeError("Failed to generate unique token")

    async def activate_token(self, raw_token: str, used_by_tg_id: int) -> ActivatedAccess | None:
        cleaned_token = raw_token.strip()
        if not cleaned_token:
            return None

        token_hash = self.hash_token(cleaned_token)
        token = await self.token_repository.get_by_hash_for_update(token_hash)

        if token is None or token.is_used or not token.tier:
            return None

        tier = token.tier
        duration_days = token.duration_days or duration_days_for_tier(tier)
        now = datetime.now(UTC)
        expires_at = now + timedelta(days=duration_days)

        token.is_used = True
        token.used_by_tg_id = used_by_tg_id
        token.used_at = now

        await self.tier_access_repository.create(
            telegram_id=used_by_tg_id,
            tier=tier,
            expires_at=expires_at,
            token_id=token.id,
            payment_id=token.payment_id,
        )
        await self.log_event(
            event_type="token_activate",
            status="success",
            payment_id=token.payment_id,
            tier=tier,
            telegram_id=used_by_tg_id,
            token_id=token.id,
        )

        return ActivatedAccess(
            telegram_id=used_by_tg_id,
            tier=tier,
            expires_at=expires_at,
            token_id=token.id,
        )

    async def get_active_access(self, telegram_id: int) -> ActiveAccess | None:
        """Highest-rank non-expired tier for a user, or None."""
        now = datetime.now(UTC)
        grants = await self.tier_access_repository.list_active(telegram_id, now)
        if not grants:
            return None

        best = max(grants, key=lambda grant: (tier_rank(grant.tier), grant.expires_at))
        return ActiveAccess(tier=best.tier, expires_at=best.expires_at)

    async def log_event(
        self,
        event_type: str,
        status: str,
        payment_id: str | None = None,
        tier: str | None = None,
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
            course_ids=[tier] if tier else None,
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
