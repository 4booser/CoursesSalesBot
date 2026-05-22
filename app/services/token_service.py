from dataclasses import dataclass
from hashlib import sha256
from secrets import token_urlsafe

from app.repositories.token_repository import TokenRepository


@dataclass(frozen=True)
class CreatedToken:
    token_id: int
    raw_token: str
    token_preview: str
    course_id: str


class TokenService:
    TOKEN_BYTES = 32

    def __init__(self, token_repository: TokenRepository):
        self.token_repository = token_repository

    async def create_token(
        self,
        created_by_tg_id: int,
        course_id: str = "default",
    ) -> CreatedToken:
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
                course_id=course_id,
            )
            return CreatedToken(
                token_id=token.id,
                raw_token=raw_token,
                token_preview=token_preview,
                course_id=token.course_id,
            )
        raise RuntimeError("Failed to generate unique token")

    async def activate_token(self, raw_token: str, used_by_tg_id: int):
        token_hash = self.hash_token(raw_token.strip())
        token = await self.token_repository.get_by_hash(token_hash)
        if token is None or token.is_used:
            return None
        token.is_used = True
        token.used_by_tg_id = used_by_tg_id
        return token

    @staticmethod
    def hash_token(token: str) -> str:
        return sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def make_preview(token: str) -> str:
        return f"{token[:6]}...{token[-4:]}"
