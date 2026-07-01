from alembic import op
import sqlalchemy as sa

revision = "0005_add_tier_flags"
down_revision = "0004_content_catalog_and_tiers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tier_flags",
        sa.Column("tier", sa.String(length=16), primary_key=True),
        sa.Column("is_frozen", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    # Seed one row per real tier so the admin toggle menu is fully populated.
    op.bulk_insert(
        sa.table(
            "tier_flags",
            sa.column("tier", sa.String),
            sa.column("is_frozen", sa.Boolean),
        ),
        [
            {"tier": "lite", "is_frozen": False},
            {"tier": "pro", "is_frozen": False},
            {"tier": "vip", "is_frozen": False},
        ],
    )


def downgrade() -> None:
    op.drop_table("tier_flags")
