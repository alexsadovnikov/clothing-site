"""product_media: fix FK media_id on delete restrict

Revision ID: 6112817e203b
Revises: 8c0af0d9b7a1
Create Date: 2026-01-25

Purpose:
- Resolve conflict: product_media.media_id is NOT NULL but FK is ON DELETE SET NULL
- Change FK to ON DELETE RESTRICT/NO ACTION
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "6112817e203b"
down_revision = "8c0af0d9b7a1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop old FK (SET NULL)
    op.drop_constraint(
        "product_media_media_id_fkey",
        "product_media",
        type_="foreignkey",
    )

    # Recreate FK with RESTRICT (Postgres may display as NO ACTION)
    op.create_foreign_key(
        "product_media_media_id_fkey",
        source_table="product_media",
        referent_table="media",
        local_cols=["media_id"],
        remote_cols=["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    # Revert FK to SET NULL (note: incompatible with NOT NULL; downgrade is schema rollback)
    op.drop_constraint(
        "product_media_media_id_fkey",
        "product_media",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "product_media_media_id_fkey",
        source_table="product_media",
        referent_table="media",
        local_cols=["media_id"],
        remote_cols=["id"],
        ondelete="SET NULL",
    )
