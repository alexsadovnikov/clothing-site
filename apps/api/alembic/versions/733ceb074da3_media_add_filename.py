"""media: add filename

Revision ID: 733ceb074da3
Revises: c09909978730
Create Date: 2026-01-24
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "733ceb074da3"
down_revision: Union[str, None] = "c09909978730"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("media", sa.Column("filename", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("media", "filename")
