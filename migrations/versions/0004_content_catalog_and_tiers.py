from alembic import op
import sqlalchemy as sa

revision = "0004_content_catalog_and_tiers"
down_revision = "0003_add_youtube_course_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # access_tokens: course-based -> tier-based.
    op.alter_column("access_tokens", "course_id", existing_type=sa.String(length=64), nullable=True)
    op.add_column("access_tokens", sa.Column("tier", sa.String(length=16), nullable=True))
    op.add_column("access_tokens", sa.Column("duration_days", sa.Integer(), nullable=True))
    op.create_index("ix_access_tokens_tier", "access_tokens", ["tier"])

    # Catalog: groups / subgroups of videos.
    op.create_table(
        "content_groups",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(length=128), nullable=False),
        sa.Column("parent_id", sa.Integer(), sa.ForeignKey("content_groups.id", ondelete="CASCADE"), nullable=True),
        sa.Column("min_tier", sa.String(length=16), server_default=sa.text("'lite'"), nullable=False),
        sa.Column("position", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_content_groups_parent_id", "content_groups", ["parent_id"])

    op.create_table(
        "videos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("group_id", sa.Integer(), sa.ForeignKey("content_groups.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(length=128), nullable=False),
        sa.Column("youtube_url", sa.String(length=512), nullable=False),
        sa.Column("thumbnail_url", sa.String(length=512), nullable=True),
        sa.Column("min_tier", sa.String(length=16), server_default=sa.text("'lite'"), nullable=False),
        sa.Column("position", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_videos_group_id", "videos", ["group_id"])

    # Tier grants per user, each with its own expiry.
    op.create_table(
        "user_tier_accesses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("tier", sa.String(length=16), nullable=False),
        sa.Column("token_id", sa.Integer(), sa.ForeignKey("access_tokens.id", ondelete="SET NULL"), nullable=True),
        sa.Column("payment_id", sa.String(length=128), nullable=True),
        sa.Column("granted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_user_tier_accesses_telegram_id", "user_tier_accesses", ["telegram_id"])
    op.create_index("ix_user_tier_accesses_payment_id", "user_tier_accesses", ["payment_id"])


def downgrade() -> None:
    op.drop_table("user_tier_accesses")
    op.drop_table("videos")
    op.drop_index("ix_content_groups_parent_id", table_name="content_groups")
    op.drop_table("content_groups")
    op.drop_index("ix_access_tokens_tier", table_name="access_tokens")
    op.drop_column("access_tokens", "duration_days")
    op.drop_column("access_tokens", "tier")
    op.alter_column("access_tokens", "course_id", existing_type=sa.String(length=64), nullable=False)
