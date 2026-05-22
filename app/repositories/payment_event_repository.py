from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import PaymentEventLog


class PaymentEventRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        event_type: str,
        status: str,
        payment_id: str | None = None,
        course_ids: list[str] | None = None,
        telegram_id: int | None = None,
        token_id: int | None = None,
        message: str | None = None,
    ) -> PaymentEventLog:
        event = PaymentEventLog(
            payment_id=payment_id,
            event_type=event_type,
            status=status,
            course_ids=",".join(course_ids) if course_ids else None,
            telegram_id=telegram_id,
            token_id=token_id,
            message=message,
        )
        self.session.add(event)
        await self.session.flush()
        return event
