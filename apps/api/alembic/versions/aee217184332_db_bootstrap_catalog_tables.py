"""db: bootstrap catalog tables

Revision ID: aee217184332
Revises: 733ceb074da3
Create Date: 2026-01-24
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text

# revision identifiers, used by Alembic.
revision: str = "aee217184332"
down_revision: str | None = "733ceb074da3"
branch_labels = None
depends_on = None


def _table_exists(insp, name: str) -> bool:
    return name in insp.get_table_names()


def _columns(insp, table: str) -> set[str]:
    return {c["name"] for c in insp.get_columns(table)}


def _index_exists(bind, index_name: str) -> bool:
    q = text("select 1 from pg_indexes where schemaname='public' and indexname=:n limit 1")
    return bind.execute(q, {"n": index_name}).scalar() is not None


def _constraint_exists(bind, constraint_name: str) -> bool:
    q = text("select 1 from pg_constraint where conname=:n limit 1")
    return bind.execute(q, {"n": constraint_name}).scalar() is not None


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)

    # 1) categories
    if not _table_exists(insp, "categories"):
        op.create_table(
            "categories",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("parent_id", sa.String(), nullable=True),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("slug", sa.String(), nullable=False),
            sa.Column("path", sa.String(), nullable=False),
            sa.Column("sort_order", sa.Integer(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=True),
            sa.Column("ai_aliases", sa.JSON(), nullable=True),
            sa.ForeignKeyConstraint(["parent_id"], ["categories.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        bind.execute(text("CREATE INDEX IF NOT EXISTS ix_categories_parent_id ON categories(parent_id)"))
        bind.execute(text("CREATE INDEX IF NOT EXISTS ix_categories_path ON categories(path)"))
        bind.execute(text("CREATE INDEX IF NOT EXISTS ix_categories_slug ON categories(slug)"))
        insp = inspect(bind)

    # 2) products
    if not _table_exists(insp, "products"):
        op.create_table(
            "products",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("owner_id", sa.String(), nullable=False),
            sa.Column("status", sa.String(), nullable=False),
            sa.Column("title", sa.String(), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("category_id", sa.String(), nullable=True),
            sa.Column("attributes", sa.JSON(), nullable=True),
            sa.Column("tags", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
            sa.ForeignKeyConstraint(["category_id"], ["categories.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        bind.execute(text("CREATE INDEX IF NOT EXISTS ix_products_category_id ON products(category_id)"))
        bind.execute(text("CREATE INDEX IF NOT EXISTS ix_products_owner_id ON products(owner_id)"))
        bind.execute(text("CREATE INDEX IF NOT EXISTS ix_products_owner_status ON products(owner_id, status)"))
        insp = inspect(bind)

    # 3) product_media
    if not _table_exists(insp, "product_media"):
        op.create_table(
            "product_media",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("product_id", sa.String(), nullable=False),
            sa.Column("bucket", sa.String(), nullable=False),
            sa.Column("object_key", sa.String(), nullable=False),
            sa.Column("kind", sa.String(), nullable=False),
            sa.Column("content_type", sa.String(), nullable=True),
            sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        bind.execute(text("CREATE INDEX IF NOT EXISTS ix_product_media_product_id ON product_media(product_id)"))
        insp = inspect(bind)

    # 4) ai_jobs — расширяем безопасно (только add column), не ломая текущую таблицу
    if _table_exists(insp, "ai_jobs"):
        cols = _columns(insp, "ai_jobs")

        def add_col(name: str, col: sa.Column):
            if name not in cols:
                op.add_column("ai_jobs", col)

        add_col("hint", sa.Column("hint", sa.JSON(), nullable=True))
        add_col("result_json", sa.Column("result_json", sa.JSON(), nullable=True))
        add_col("error", sa.Column("error", sa.Text(), nullable=True))
        add_col("model_version", sa.Column("model_version", sa.String(), nullable=True))
        add_col("draft_product_id", sa.Column("draft_product_id", sa.String(), nullable=True))
        add_col("updated_at", sa.Column("updated_at", sa.DateTime(), nullable=True))

        insp = inspect(bind)
        if _table_exists(insp, "products") and ("draft_product_id" in _columns(insp, "ai_jobs")):
            if not _constraint_exists(bind, "ai_jobs_draft_product_id_fkey"):
                bind.execute(text(
                    "ALTER TABLE ai_jobs "
                    "ADD CONSTRAINT ai_jobs_draft_product_id_fkey "
                    "FOREIGN KEY (draft_product_id) REFERENCES products(id)"
                ))
            if not _index_exists(bind, "ix_ai_jobs_draft_product_id"):
                bind.execute(text("CREATE INDEX IF NOT EXISTS ix_ai_jobs_draft_product_id ON ai_jobs(draft_product_id)"))


def downgrade() -> None:
    # Bootstrap-миграцию безопаснее не откатывать (чтобы не потерять данные).
    pass
