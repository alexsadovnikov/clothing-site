"""product_media: add media_id column fk and index

Revision ID: 4cedda3463e1
Revises: e0146a8efff7
Create Date: 2026-01-25

"""
from alembic import op
import sqlalchemy as sa

revision = "4cedda3463e1"
down_revision = ("c09909978730", "f83761822ca6")
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("""
        ALTER TABLE public.product_media
        ADD COLUMN IF NOT EXISTS media_id varchar;
    """))

    op.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS ix_product_media_media_id
        ON public.product_media (media_id);
    """))

    op.execute(sa.text("""
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'product_media_media_id_fkey'
    ) THEN
        ALTER TABLE public.product_media
        ADD CONSTRAINT product_media_media_id_fkey
        FOREIGN KEY (media_id) REFERENCES public.media(id)
        ON DELETE SET NULL;
    END IF;
END $$;
    """))

    op.execute(sa.text("""
        UPDATE public.product_media pm
        SET media_id = m.id
        FROM public.media m
        WHERE pm.media_id IS NULL
          AND m.bucket = pm.bucket
          AND m.object_key = pm.object_key;
    """))


def downgrade() -> None:
    op.execute(sa.text("""
        ALTER TABLE public.product_media
        DROP CONSTRAINT IF EXISTS product_media_media_id_fkey;
    """))
    op.execute(sa.text("""
        DROP INDEX IF EXISTS public.ix_product_media_media_id;
    """))
    op.execute(sa.text("""
        ALTER TABLE public.product_media
        DROP COLUMN IF EXISTS media_id;
    """))
