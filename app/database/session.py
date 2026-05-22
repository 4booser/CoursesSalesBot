from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings
from app.database.models import Base


engine = create_async_engine(
    url=settings.DATABASE_URL,
    echo=False,
)

session_maker = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def create_tables() -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        await sync_dev_schema(connection)


async def sync_dev_schema(connection) -> None:
    """
    Temporary development schema sync.

    SQLAlchemy create_all() creates missing tables, but does not alter
    existing tables when models change. Keep this only until Alembic
    migrations are configured.
    """
    await connection.execute(
        text(
            "ALTER TABLE access_tokens "
            "ADD COLUMN IF NOT EXISTS payment_id VARCHAR(128)"
        )
    )
    await connection.execute(
        text(
            "CREATE UNIQUE INDEX IF NOT EXISTS "
            "ix_access_tokens_payment_id_unique "
            "ON access_tokens (payment_id) "
            "WHERE payment_id IS NOT NULL"
        )
    )
    await connection.execute(
        text(
            "CREATE UNIQUE INDEX IF NOT EXISTS "
            "ix_user_course_accesses_telegram_id_course_id_unique "
            "ON user_course_accesses (telegram_id, course_id)"
        )
    )
