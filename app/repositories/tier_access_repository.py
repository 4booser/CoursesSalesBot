from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import UserTierAccess


class TierAccessRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        telegram_id: int,
        tier: str,
        expires_at: datetime,
        token_id: int | None,
        payment_id: str | None,
    ) -> UserTierAccess:
        access = UserTierAccess(
            telegram_id=telegram_id,
            tier=tier,
            expires_at=expires_at,
            token_id=token_id,
            payment_id=payment_id,
        )
        self.session.add(access)
        await self.session.flush()
        return access

    async def list_active(self, telegram_id: int, now: datetime) -> list[UserTierAccess]:
        """All non-expired grants for a user, newest first."""
        stmt = (
            select(UserTierAccess)
            .where(
                UserTierAccess.telegram_id == telegram_id,
                UserTierAccess.expires_at > now,
            )
            .order_by(UserTierAccess.expires_at.desc())
        )
        result = await self.session.scalars(stmt)
        return list(result.all())

    async def expire_active(self, telegram_id: int, now: datetime) -> int:
        """Force-expire every active grant for a user; returns rows affected.

        Revoke has no dedicated flag: gating reads ``expires_at > now``, so pulling
        expiry back to ``now`` cuts access off immediately.
        """
        stmt = (
            update(UserTierAccess)
            .where(
                UserTierAccess.telegram_id == telegram_id,
                UserTierAccess.expires_at > now,
            )
            .values(expires_at=now)
        )
        result = await self.session.execute(stmt)
        return result.rowcount or 0
