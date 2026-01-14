"""media_add_size_bytes_checksum

Revision ID: fb60132c0152
Revises: 644f2950188d
Create Date: 2026-01-14

Add columns for media metadata used by /v1/media/upload:
- size_bytes
- checksum_sha256
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "fb60132c0152"
down_revision: Union[str, None] = "644f2950188d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("media", sa.Column("size_bytes", sa.BigInteger(), nullable=True))
    op.add_column("media", sa.Column("checksum_sha256", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("media", "checksum_sha256")
    op.drop_column("media", "size_bytes")
