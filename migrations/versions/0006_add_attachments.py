from alembic import op
import sqlalchemy as sa

revision = "0006_add_attachments"
down_revision = "0005_add_tier_flags"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "attachments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "group_id",
            sa.Integer(),
            sa.ForeignKey("content_groups.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "video_id",
            sa.Integer(),
            sa.ForeignKey("videos.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("media_type", sa.String(length=16), nullable=False),
        sa.Column("file_id", sa.String(length=512), nullable=False),
        sa.Column("file_unique_id", sa.String(length=128), nullable=True),
        sa.Column("file_name", sa.String(length=256), nullable=True),
        sa.Column("mime_type", sa.String(length=128), nullable=True),
        sa.Column("file_size", sa.BigInteger(), nullable=True),
        sa.Column("min_tier", sa.String(length=16), server_default=sa.text("'lite'"), nullable=False),
        sa.Column("position", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "(group_id IS NOT NULL) <> (video_id IS NOT NULL)",
            name="ck_attachment_single_parent",
        ),
    )
    op.create_index("ix_attachments_group_id", "attachments", ["group_id"])
    op.create_index("ix_attachments_video_id", "attachments", ["video_id"])


def downgrade() -> None:
    op.drop_index("ix_attachments_video_id", table_name="attachments")
    op.drop_index("ix_attachments_group_id", table_name="attachments")
    op.drop_table("attachments")
