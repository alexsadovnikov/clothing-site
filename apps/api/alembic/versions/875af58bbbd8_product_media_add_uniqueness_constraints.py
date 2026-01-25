"""product_media: add uniqueness constraints

Revision ID: 875af58bbbd8
Revises: 6041612e34d2
Create Date: 2026-01-25

Purpose:
- Prevent exact duplicates: (product_id, media_id, kind)
- Ensure a single 'primary' per product_id (partial unique index)
"""
from alembic import op
import sqlalchemy as sa

revision = "875af58bbbd8"
down_revision = "6041612e34d2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) Unique exact link: same media cannot be attached twice with same kind
    op.create_index(
        "uq_product_media_product_media_kind",
        "product_media",
        ["product_id", "media_id", "kind"],
        unique=True,
    )

    # 2) Only one 'primary' per product (PostgreSQL partial unique index)
    op.create_index(
        "uq_product_media_single_primary",
        "product_media",
        ["product_id"],
        unique=True,
        postgresql_where=sa.text("kind = 'primary'"),
    )


def downgrade() -> None:
    op.drop_index("uq_product_media_single_primary", table_name="product_media")
    op.drop_index("uq_product_media_product_media_kind", table_name="product_media")
