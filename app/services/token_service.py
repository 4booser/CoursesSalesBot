from dataclasses import dataclass
from hashlib import sha256
from secrets import token_urlsafe

from app.repositories.token_repository import TokenRepository


@dataclass(frozen=True)
class CreatedToken:
    token_id: int
    raw_token: str
    token_preview: str


class TokenService:
    TOKEN_BYTES = 32

    def __init__(self, token_repository: TokenRepository):
        self.token_repository = token_repository

    async def create_token(self, created_by_tg_id: int) -> CreatedToken:
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
            )

            return CreatedToken(
                token_id=token.id,
                raw_token=raw_token,
                token_preview=token_preview,
            )

        raise RuntimeError("Failed to generate unique token")

    @staticmethod
    def hash_token(token: str) -> str:
        return sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def make_preview(token: str) -> str:
        return f"{token[:6]}...{token[-4:]}"