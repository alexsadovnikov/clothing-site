"""media: align storage fields (noop placeholder)

Revision ID: c09909978730
Revises: 20260122_media_storage_fields
Create Date: 2026-01-24
"""

revision = "c09909978730"
down_revision = "20260122_media_storage_fields"
branch_labels = None
depends_on = None


def upgrade():
    # DB уже на этой версии (alembic_version=c09909978730).
    # Файл нужен только чтобы Alembic мог построить граф ревизий.
    pass


def downgrade():
    pass
