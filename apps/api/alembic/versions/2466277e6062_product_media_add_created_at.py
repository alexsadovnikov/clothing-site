"""product_media_add_created_at

Revision ID: 2466277e6062
Revises: fb60132c0152
Create Date: 2026-01-14 19:26:57.592499

Add created_at column to product_media table.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "2466277e6062"
down_revision: Union[str, None] = "fb60132c0152"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("product_media", sa.Column("created_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("product_media", "created_at")
