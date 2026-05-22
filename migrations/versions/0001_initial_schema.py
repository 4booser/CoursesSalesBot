from alembic import op
import sqlalchemy as sa

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "courses",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("title", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("invite_link", sa.String(length=512), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "access_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("token_preview", sa.String(length=16), nullable=False),
        sa.Column("course_id", sa.String(length=64), nullable=False),
        sa.Column("payment_id", sa.String(length=128), nullable=True),
        sa.Column("created_by_tg_id", sa.BigInteger(), nullable=False),
        sa.Column("is_used", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("used_by_tg_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_access_tokens_token_hash", "access_tokens", ["token_hash"], unique=True)
    op.create_index("ix_access_tokens_payment_id", "access_tokens", ["payment_id"], unique=True)
    op.create_index("ix_access_tokens_course_id", "access_tokens", ["course_id"])
    op.create_table(
        "token_courses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("token_id", sa.Integer(), sa.ForeignKey("access_tokens.id", ondelete="CASCADE"), nullable=False),
        sa.Column("course_id", sa.String(length=64), sa.ForeignKey("courses.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("token_id", "course_id"),
    )
    op.create_index("ix_token_courses_token_id", "token_courses", ["token_id"])
    op.create_index("ix_token_courses_course_id", "token_courses", ["course_id"])
    op.create_table(
        "user_course_accesses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("course_id", sa.String(length=64), sa.ForeignKey("courses.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("token_id", sa.Integer(), sa.ForeignKey("access_tokens.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("telegram_id", "course_id"),
    )
    op.create_index("ix_user_course_accesses_telegram_id", "user_course_accesses", ["telegram_id"])
    op.create_index("ix_user_course_accesses_course_id", "user_course_accesses", ["course_id"])
    op.create_table(
        "payment_event_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("payment_id", sa.String(length=128), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("course_ids", sa.Text(), nullable=True),
        sa.Column("telegram_id", sa.BigInteger(), nullable=True),
        sa.Column("token_id", sa.BigInteger(), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("payment_event_logs")
    op.drop_table("user_course_accesses")
    op.drop_table("token_courses")
    op.drop_table("access_tokens")
    op.drop_table("courses")
