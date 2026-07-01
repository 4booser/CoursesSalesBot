from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import TierFlag


class TierFlagRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def frozen_tiers(self) -> set[str]:
        stmt = select(TierFlag.tier).where(TierFlag.is_frozen.is_(True))
        result = await self.session.scalars(stmt)
        return set(result.all())

    async def is_frozen(self, tier: str) -> bool:
        flag = await self.session.get(TierFlag, tier)
        return bool(flag and flag.is_frozen)

    async def set_frozen(self, tier: str, frozen: bool) -> None:
        flag = await self.session.get(TierFlag, tier)
        if flag is None:
            self.session.add(TierFlag(tier=tier, is_frozen=frozen))
        else:
            flag.is_frozen = frozen
        await self.session.flush()
