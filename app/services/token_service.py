from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from secrets import token_urlsafe

from app.repositories.access_repository import AccessRepository
from app.repositories.token_repository import TokenRepository


@dataclass(frozen=True)
class CreatedToken:
    token_id: int
    raw_token: str
    token_preview: str
    course_id: str
    payment_id: str | None


@dataclass(frozen=True)
class ActivatedAccess:
    telegram_id: int
    course_id: str
    token_id: int


class TokenAlreadyExistsError(Exception):
    pass


class TokenService:
    TOKEN_BYTES = 32

    def __init__(
        self,
        token_repository: TokenRepository,
        access_repository: AccessRepository,
    ):
        self.token_repository = token_repository
        self.access_repository = access_repository

    async def create_token(
        self,
        created_by_tg_id: int,
        course_id: str,
        payment_id: str | None = None,
    ) -> CreatedToken:
        normalized_course_id = self.normalize_course_id(course_id)
        normalized_payment_id = payment_id.strip() if payment_id else None

        if normalized_payment_id is not None:
            existing_token = await self.token_repository.get_by_payment_id(
                normalized_payment_id
            )
            if existing_token is not None:
                raise TokenAlreadyExistsError(
                    "Token for this payment_id already exists"
                )

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
                course_id=normalized_course_id,
                payment_id=normalized_payment_id,
            )
            return CreatedToken(
                token_id=token.id,
                raw_token=raw_token,
                token_preview=token_preview,
                course_id=token.course_id,
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

        existing_access = await self.access_repository.get_by_user_and_course(
            telegram_id=used_by_tg_id,
            course_id=token.course_id,
        )
        if existing_access is not None:
            return ActivatedAccess(
                telegram_id=existing_access.telegram_id,
                course_id=existing_access.course_id,
                token_id=existing_access.token_id,
            )

        token.is_used = True
        token.used_by_tg_id = used_by_tg_id
        token.used_at = datetime.now(UTC)

        access = await self.access_repository.create(
            telegram_id=used_by_tg_id,
            course_id=token.course_id,
            token_id=token.id,
        )

        return ActivatedAccess(
            telegram_id=access.telegram_id,
            course_id=access.course_id,
            token_id=token.id,
        )

    async def get_user_courses(self, telegram_id: int) -> list[str]:
        accesses = await self.access_repository.get_user_courses(telegram_id)
        return [access.course_id for access in accesses]

    async def has_access(self, telegram_id: int, course_id: str) -> bool:
        normalized_course_id = self.normalize_course_id(course_id)
        access = await self.access_repository.get_by_user_and_course(
            telegram_id=telegram_id,
            course_id=normalized_course_id,
        )
        return access is not None

    @staticmethod
    def hash_token(token: str) -> str:
        return sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def make_preview(token: str) -> str:
        return f"{token[:6]}...{token[-4:]}"

    @staticmethod
    def normalize_course_id(course_id: str) -> str:
        normalized = course_id.strip()
        if not normalized:
            raise ValueError("course_id must not be empty")
        return normalized
