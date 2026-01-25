"""product_media: drop legacy bucket/object_key/content_type

Revision ID: 6041612e34d2
Revises: 6112817e203b
Create Date: 2026-01-25

Purpose:
- product_media now references media via media_id (NOT NULL + FK)
- legacy columns bucket/object_key/content_type are redundant and block clean inserts
"""
from alembic import op
import sqlalchemy as sa

revision = "6041612e34d2"
down_revision = "6112817e203b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop legacy columns (idempotent)
    op.execute(sa.text("""
        ALTER TABLE public.product_media
            DROP COLUMN IF EXISTS bucket,
            DROP COLUMN IF EXISTS object_key,
            DROP COLUMN IF EXISTS content_type;
    """))


def downgrade() -> None:
    # Restore legacy columns as nullable (rollback only)
    op.add_column("product_media", sa.Column("bucket", sa.String(), nullable=True))
    op.add_column("product_media", sa.Column("object_key", sa.String(), nullable=True))
    op.add_column("product_media", sa.Column("content_type", sa.String(), nullable=True))
