"""drop_backup_tables

Revision ID: 644f2950188d
Revises: 2f2fd3ad0b96
Create Date: 2026-01-14

Миграция для удаления *_backup таблиц.
Безопасна: DROP TABLE IF EXISTS.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa  # noqa: F401


# revision identifiers, used by Alembic.
revision: str = "644f2950188d"
down_revision: Union[str, None] = "2f2fd3ad0b96"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        DROP TABLE IF EXISTS
          ai_jobs_backup,
          look_items_backup,
          media_backup,
          product_media_backup,
          products_backup,
          wear_log_backup
        CASCADE;
        """
    )


def downgrade() -> None:
    # backup-таблицы не восстанавливаем
    pass
