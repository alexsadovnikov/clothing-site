"""uuid_cleanup_step

Revision ID: 5c67d5ac037e
Revises: 390e5cfa9a80
Create Date: 2026-01-14

Промежуточная миграция-заглушка для восстановления цепочки Alembic.
Если в истории проекта была реальная миграция 5c67d5ac037e, но файл потеряли —
эта заглушка возвращает целостность графа ревизий.
"""

from alembic import op
import sqlalchemy as sa

revision = "5c67d5ac037e"
down_revision = "390e5cfa9a80"
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
