from alembic import op
import sqlalchemy as sa

revision = "0002_add_course_telegram_chat_id"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "courses",
        sa.Column("telegram_chat_id", sa.BigInteger(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("courses", "telegram_chat_id")
