from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, String, UniqueConstraint, func, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class AccessToken(Base):
    __tablename__ = "access_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)

    token_hash: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        index=True,
        nullable=False,
    )

    token_preview: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
    )

    course_id: Mapped[str] = mapped_column(
        String(64),
        index=True,
        nullable=False,
    )

    payment_id: Mapped[str | None] = mapped_column(
        String(128),
        unique=True,
        index=True,
        nullable=True,
    )

    created_by_tg_id: Mapped[int] = mapped_column(
        BigInteger,
        index=True,
        nullable=False,
        default=0,
    )

    is_used: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
    )

    used_by_tg_id: Mapped[int | None] = mapped_column(
        BigInteger,
        index=True,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class UserCourseAccess(Base):
    __tablename__ = "user_course_accesses"
    __table_args__ = (
        UniqueConstraint("telegram_id", "course_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    telegram_id: Mapped[int] = mapped_column(
        BigInteger,
        index=True,
        nullable=False,
    )

    course_id: Mapped[str] = mapped_column(
        String(64),
        index=True,
        nullable=False,
    )

    token_id: Mapped[int] = mapped_column(nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
