"""product_media: actually add media_id fk index

Revision ID: 8c0af0d9b7a1
Revises: 4cedda3463e1
Create Date: 2026-01-25

Changes:
- Ensure product_media.media_id exists (varchar, nullable)
- Best-effort backfill media_id from media via (bucket, object_key)
- Ensure index on media_id
- Ensure FK media_id -> media.id (ON DELETE SET NULL)
"""
from alembic import op
import sqlalchemy as sa

revision = "8c0af0d9b7a1"
down_revision = "4cedda3463e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) add column (idempotent)
    op.execute(sa.text("""
        ALTER TABLE public.product_media
        ADD COLUMN IF NOT EXISTS media_id varchar;
    """))

    # 2) backfill (best-effort)
    op.execute(sa.text("""
        UPDATE public.product_media pm
        SET media_id = m.id
        FROM public.media m
        WHERE pm.media_id IS NULL
          AND m.bucket = pm.bucket
          AND m.object_key = pm.object_key;
    """))

    # 3) index (idempotent)
    op.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS ix_product_media_media_id
        ON public.product_media (media_id);
    """))

    # 4) FK (idempotent via python check; no DO blocks)
    conn = op.get_bind()
    fk_exists = conn.execute(
        sa.text("SELECT 1 FROM pg_constraint WHERE conname = :name"),
        {"name": "product_media_media_id_fkey"},
    ).scalar()

    if not fk_exists:
        op.create_foreign_key(
            "product_media_media_id_fkey",
            "product_media",
            "media",
            ["media_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    # reverse in safe order
    op.drop_constraint("product_media_media_id_fkey", "product_media", type_="foreignkey")
    op.execute(sa.text("DROP INDEX IF EXISTS public.ix_product_media_media_id;"))
    op.execute(sa.text("ALTER TABLE public.product_media DROP COLUMN IF EXISTS media_id;"))
