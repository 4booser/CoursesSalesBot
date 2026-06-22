from alembic import op
import sqlalchemy as sa

revision = "0003_add_youtube_course_metadata"
down_revision = "0002_add_course_telegram_chat_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("courses", sa.Column("thumbnail_url", sa.String(length=512), nullable=True))
    op.add_column("courses", sa.Column("youtube_url", sa.String(length=512), nullable=True))


def downgrade() -> None:
    op.drop_column("courses", "youtube_url")
    op.drop_column("courses", "thumbnail_url")
