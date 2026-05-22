from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import AccessToken


class TokenRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def exists_by_hash(self, token_hash: str) -> bool:
        stmt = select(AccessToken.id).where(
            AccessToken.token_hash == token_hash
        )

        token_id = await self.session.scalar(stmt)

        return token_id is not None

    async def create(
        self,
        token_hash: str,
        token_preview: str,
        created_by_tg_id: int,
    ) -> AccessToken:
        token = AccessToken(
            token_hash=token_hash,
            token_preview=token_preview,
            created_by_tg_id=created_by_tg_id,
        )

        self.session.add(token)
        await self.session.flush()

        return token