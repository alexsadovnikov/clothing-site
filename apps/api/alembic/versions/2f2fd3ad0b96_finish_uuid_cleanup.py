"""finish_uuid_cleanup

Revision ID: 2f2fd3ad0b96
Revises: 5c67d5ac037e
Create Date: 2026-01-14 11:21:33.417048

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2f2fd3ad0b96'
down_revision: Union[str, None] = '5c67d5ac037e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
