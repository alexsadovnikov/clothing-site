"""fix: product_media add media_id fk

Revision ID: e0146a8efff7
Revises: 9f8c92415fc1
Create Date: 2026-01-25 08:19:57.159765

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e0146a8efff7'
down_revision: Union[str, None] = '9f8c92415fc1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
