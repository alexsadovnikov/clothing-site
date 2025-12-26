"""create looks and wear log tables

Revision ID: 390e5cfa9a80
Revises: e2a717f7292d
Create Date: 2025-12-26

"""
from alembic import op
import sqlalchemy as sa

revision = "390e5cfa9a80"
down_revision = "e2a717f7292d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "looks",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("owner_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.String(), nullable=True),
        sa.Column("occasion", sa.String(), nullable=True),
        sa.Column("season", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_looks_owner_id", "looks", ["owner_id"])
    op.create_index("ix_looks_owner_created", "looks", ["owner_id", "created_at"])
    op.create_index("ix_looks_owner_updated", "looks", ["owner_id", "updated_at"])

    op.create_table(
        "look_items",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("look_id", sa.String(), sa.ForeignKey("looks.id"), nullable=False),
        sa.Column("product_id", sa.String(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("look_id", "product_id", name="uq_look_items_look_product"),
    )
    op.create_index("ix_look_items_look_id", "look_items", ["look_id"])
    op.create_index("ix_look_items_product_id", "look_items", ["product_id"])

    op.create_table(
        "wear_log",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("owner_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("product_id", sa.String(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("worn_at", sa.DateTime(), nullable=False),
        sa.Column("context", sa.String(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_wear_log_owner_id", "wear_log", ["owner_id"])
    op.create_index("ix_wear_log_owner_worn_at", "wear_log", ["owner_id", "worn_at"])
    op.create_index("ix_wear_log_product_worn_at", "wear_log", ["product_id", "worn_at"])


def downgrade() -> None:
    op.drop_index("ix_wear_log_product_worn_at", table_name="wear_log")
    op.drop_index("ix_wear_log_owner_worn_at", table_name="wear_log")
    op.drop_index("ix_wear_log_owner_id", table_name="wear_log")
    op.drop_table("wear_log")

    op.drop_index("ix_look_items_product_id", table_name="look_items")
    op.drop_index("ix_look_items_look_id", table_name="look_items")
    op.drop_table("look_items")

    op.drop_index("ix_looks_owner_updated", table_name="looks")
    op.drop_index("ix_looks_owner_created", table_name="looks")
    op.drop_index("ix_looks_owner_id", table_name="looks")
    op.drop_table("looks")
