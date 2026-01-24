"""products: defaults and not null for created_at/updated_at

Revision ID: f83761822ca6
Revises: d65a6e8b7856
Create Date: 2026-01-24
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "f83761822ca6"
down_revision = "d65a6e8b7856"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) backfill NULLs (safe/idempotent)
    op.execute(sa.text("UPDATE products SET created_at = now() WHERE created_at IS NULL;"))
    op.execute(sa.text("UPDATE products SET updated_at = created_at WHERE updated_at IS NULL;"))

    # 2) set defaults
    op.alter_column("products", "created_at", server_default=sa.text("now()"))
    op.alter_column("products", "updated_at", server_default=sa.text("now()"))

    # 3) enforce NOT NULL
    op.alter_column("products", "created_at", nullable=False)
    op.alter_column("products", "updated_at", nullable=False)


def downgrade() -> None:
    # revert NOT NULL + defaults (do not delete data)
    op.alter_column("products", "updated_at", nullable=True, server_default=None)
    op.alter_column("products", "created_at", nullable=True, server_default=None)
