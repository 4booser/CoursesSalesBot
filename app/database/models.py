from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Course(Base):
    __tablename__ = "courses"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    invite_link: Mapped[str | None] = mapped_column(String(512), nullable=True)
    thumbnail_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    youtube_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    telegram_chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("true"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class AccessToken(Base):
    __tablename__ = "access_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        index=True,
        nullable=False,
    )
    token_preview: Mapped[str] = mapped_column(String(16), nullable=False)

    # Legacy course-based field (kept nullable for backward compatibility).
    course_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)

    # Tier-based purchase: token grants this subscription tier for `duration_days`.
    tier: Mapped[str | None] = mapped_column(String(16), index=True, nullable=True)
    duration_days: Mapped[int | None] = mapped_column(Integer, nullable=True)

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


class TokenCourse(Base):
    __tablename__ = "token_courses"
    __table_args__ = (UniqueConstraint("token_id", "course_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    token_id: Mapped[int] = mapped_column(
        ForeignKey("access_tokens.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    course_id: Mapped[str] = mapped_column(
        ForeignKey("courses.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class UserCourseAccess(Base):
    __tablename__ = "user_course_accesses"
    __table_args__ = (UniqueConstraint("telegram_id", "course_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    course_id: Mapped[str] = mapped_column(
        ForeignKey("courses.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    token_id: Mapped[int] = mapped_column(
        ForeignKey("access_tokens.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class ContentGroup(Base):
    """A group or subgroup of videos in the in-bot catalog.

    Top-level groups have ``parent_id is None``. A subgroup points to its parent
    group via ``parent_id``. Only two levels are used in the UI (group → subgroup),
    but the self-reference allows nesting if ever needed.
    """

    __tablename__ = "content_groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(128), nullable=False)
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("content_groups.id", ondelete="CASCADE"),
        index=True,
        nullable=True,
    )
    # Minimum tier required to see this group (lite|pro|vip).
    min_tier: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'lite'"))
    position: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    children: Mapped[list["ContentGroup"]] = relationship(
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    videos: Mapped[list["Video"]] = relationship(
        back_populates="group",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    attachments: Mapped[list["Attachment"]] = relationship(
        foreign_keys="Attachment.group_id",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Video(Base):
    """A single video (private/unlisted YouTube link) inside a group."""

    __tablename__ = "videos"

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(
        ForeignKey("content_groups.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(128), nullable=False)
    youtube_url: Mapped[str] = mapped_column(String(512), nullable=False)
    thumbnail_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # Minimum tier required to watch this video (lite|pro|vip).
    min_tier: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'lite'"))
    position: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    group: Mapped["ContentGroup"] = relationship(back_populates="videos")
    attachments: Mapped[list["Attachment"]] = relationship(
        foreign_keys="Attachment.video_id",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Attachment(Base):
    """A file attached to a group or a video, delivered by Telegram ``file_id``.

    The owner uploads any file in the admin panel; the bot stores the Telegram
    ``file_id`` (persistent for this bot) plus its metadata, and later resends it
    to the user by that id — no external storage needed. Each attachment belongs
    to exactly one parent: either a ``ContentGroup`` (``group_id``) or a ``Video``
    (``video_id``), enforced by a check constraint. Tier-gated like videos.
    """

    __tablename__ = "attachments"
    __table_args__ = (
        CheckConstraint(
            "(group_id IS NOT NULL) <> (video_id IS NOT NULL)",
            name="ck_attachment_single_parent",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int | None] = mapped_column(
        ForeignKey("content_groups.id", ondelete="CASCADE"),
        index=True,
        nullable=True,
    )
    video_id: Mapped[int | None] = mapped_column(
        ForeignKey("videos.id", ondelete="CASCADE"),
        index=True,
        nullable=True,
    )
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    # One of: document | photo | video | audio | voice | animation.
    # Determines which Telegram send_* method delivers the file.
    media_type: Mapped[str] = mapped_column(String(16), nullable=False)
    file_id: Mapped[str] = mapped_column(String(512), nullable=False)
    file_unique_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    file_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    file_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    # Minimum tier required to download this file (lite|pro|vip).
    min_tier: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'lite'"))
    position: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class UserTierAccess(Base):
    """A tier grant for a user, with its own expiry.

    A user may have several rows over time (re-purchases / upgrades). The effective
    access is the highest-rank tier among rows whose ``expires_at`` is in the future.
    """

    __tablename__ = "user_tier_accesses"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    tier: Mapped[str] = mapped_column(String(16), nullable=False)
    token_id: Mapped[int | None] = mapped_column(
        ForeignKey("access_tokens.id", ondelete="SET NULL"),
        nullable=True,
    )
    payment_id: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TierFlag(Base):
    """Per-tier admin switch. When ``is_frozen`` is true, users whose effective
    tier is this one temporarily lose catalog access (their grant stays intact).
    One row per tier; a missing row means "not frozen".
    """

    __tablename__ = "tier_flags"

    tier: Mapped[str] = mapped_column(String(16), primary_key=True)
    is_frozen: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class PaymentEventLog(Base):
    __tablename__ = "payment_event_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    payment_id: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    course_ids: Mapped[str | None] = mapped_column(Text, nullable=True)
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    token_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
