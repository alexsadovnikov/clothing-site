"""db: create catalog tables (fix)

Creates missing catalog tables if they do not exist:
- categories
- products
- product_media

Also extends ai_jobs table safely with optional columns/constraints.

Idempotent by design (safe on partially-initialized DBs).
No destructive operations (no drops).
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text


revision: str = "d65a6e8b7856"
down_revision: str | None = "aee217184332"
branch_labels = None
depends_on = None


def _table_exists(insp, name: str) -> bool:
    return name in insp.get_table_names()


def _columns(insp, table: str) -> set[str]:
    return {c["name"] for c in insp.get_columns(table)}


def _index_exists(bind, index_name: str) -> bool:
    q = text(
        "select 1 from pg_indexes "
        "where schemaname='public' and indexname=:n "
        "limit 1"
    )
    return bind.execute(q, {"n": index_name}).scalar() is not None


def _constraint_exists(bind, constraint_name: str) -> bool:
    q = text("select 1 from pg_constraint where conname=:n limit 1")
    return bind.execute(q, {"n": constraint_name}).scalar() is not None


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)

    # ----------------------------
    # categories
    # ----------------------------
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
            sa.PrimaryKeyConstraint("id", name="categories_pkey"),
            sa.ForeignKeyConstraint(
                ["parent_id"],
                ["categories.id"],
                name="categories_parent_id_fkey",
            ),
        )
        op.create_index("ix_categories_parent_id", "categories", ["parent_id"], unique=False)
        op.create_index("ix_categories_path", "categories", ["path"], unique=False)
        op.create_index("ix_categories_slug", "categories", ["slug"], unique=False)
    else:
        # best-effort: add missing columns + indexes + parent FK
        cols = _columns(insp, "categories")
        missing = []
        if "parent_id" not in cols:
            missing.append(sa.Column("parent_id", sa.String(), nullable=True))
        if "name" not in cols:
            missing.append(sa.Column("name", sa.String(), nullable=False, server_default=""))
        if "slug" not in cols:
            missing.append(sa.Column("slug", sa.String(), nullable=False, server_default=""))
        if "path" not in cols:
            missing.append(sa.Column("path", sa.String(), nullable=False, server_default=""))
        if "sort_order" not in cols:
            missing.append(sa.Column("sort_order", sa.Integer(), nullable=True))
        if "is_active" not in cols:
            missing.append(sa.Column("is_active", sa.Boolean(), nullable=True))
        if "ai_aliases" not in cols:
            missing.append(sa.Column("ai_aliases", sa.JSON(), nullable=True))

        if missing:
            with op.batch_alter_table("categories") as b:
                for col in missing:
                    b.add_column(col)

        # FK (only if parent_id column exists)
        insp = inspect(bind)
        cols = _columns(insp, "categories")
        if "parent_id" in cols and not _constraint_exists(bind, "categories_parent_id_fkey"):
            # May fail if existing rows violate; this is expected in broken DBs.
            # Prefer to raise to surface inconsistency early.
            op.create_foreign_key(
                "categories_parent_id_fkey",
                "categories",
                "categories",
                ["parent_id"],
                ["id"],
            )

        if not _index_exists(bind, "ix_categories_parent_id"):
            op.create_index("ix_categories_parent_id", "categories", ["parent_id"], unique=False)
        if not _index_exists(bind, "ix_categories_path"):
            op.create_index("ix_categories_path", "categories", ["path"], unique=False)
        if not _index_exists(bind, "ix_categories_slug"):
            op.create_index("ix_categories_slug", "categories", ["slug"], unique=False)

    # ----------------------------
    # products
    # ----------------------------
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
            sa.PrimaryKeyConstraint("id", name="products_pkey"),
            sa.ForeignKeyConstraint(["owner_id"], ["users.id"], name="products_owner_id_fkey"),
            sa.ForeignKeyConstraint(["category_id"], ["categories.id"], name="products_category_id_fkey"),
        )
        op.create_index("ix_products_category_id", "products", ["category_id"], unique=False)
        op.create_index("ix_products_owner_id", "products", ["owner_id"], unique=False)
        op.create_index("ix_products_owner_status", "products", ["owner_id", "status"], unique=False)
    else:
        cols = _columns(insp, "products")
        missing = []
        if "owner_id" not in cols:
            missing.append(sa.Column("owner_id", sa.String(), nullable=False, server_default=""))
        if "status" not in cols:
            missing.append(sa.Column("status", sa.String(), nullable=False, server_default="draft"))
        if "title" not in cols:
            missing.append(sa.Column("title", sa.String(), nullable=True))
        if "description" not in cols:
            missing.append(sa.Column("description", sa.Text(), nullable=True))
        if "category_id" not in cols:
            missing.append(sa.Column("category_id", sa.String(), nullable=True))
        if "attributes" not in cols:
            missing.append(sa.Column("attributes", sa.JSON(), nullable=True))
        if "tags" not in cols:
            missing.append(sa.Column("tags", sa.JSON(), nullable=True))
        if "created_at" not in cols:
            missing.append(sa.Column("created_at", sa.DateTime(), nullable=True))
        if "updated_at" not in cols:
            missing.append(sa.Column("updated_at", sa.DateTime(), nullable=True))

        if missing:
            with op.batch_alter_table("products") as b:
                for col in missing:
                    b.add_column(col)

        insp = inspect(bind)
        cols = _columns(insp, "products")

        # FKs (best-effort; require referenced tables)
        if "owner_id" in cols and _table_exists(insp, "users") and not _constraint_exists(bind, "products_owner_id_fkey"):
            op.create_foreign_key(
                "products_owner_id_fkey",
                "products",
                "users",
                ["owner_id"],
                ["id"],
            )
        if "category_id" in cols and _table_exists(insp, "categories") and not _constraint_exists(bind, "products_category_id_fkey"):
            op.create_foreign_key(
                "products_category_id_fkey",
                "products",
                "categories",
                ["category_id"],
                ["id"],
            )

        if not _index_exists(bind, "ix_products_category_id"):
            op.create_index("ix_products_category_id", "products", ["category_id"], unique=False)
        if not _index_exists(bind, "ix_products_owner_id"):
            op.create_index("ix_products_owner_id", "products", ["owner_id"], unique=False)
        if not _index_exists(bind, "ix_products_owner_status"):
            op.create_index("ix_products_owner_status", "products", ["owner_id", "status"], unique=False)

    # ----------------------------
    # product_media
    # ----------------------------
    if not _table_exists(insp, "product_media"):
        op.create_table(
            "product_media",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("product_id", sa.String(), nullable=False),
            sa.Column("bucket", sa.String(), nullable=False),
            sa.Column("object_key", sa.String(), nullable=False),
            sa.Column("kind", sa.String(), nullable=False),
            sa.Column("content_type", sa.String(), nullable=True),
            sa.PrimaryKeyConstraint("id", name="product_media_pkey"),
            sa.ForeignKeyConstraint(["product_id"], ["products.id"], name="product_media_product_id_fkey"),
        )
        op.create_index("ix_product_media_product_id", "product_media", ["product_id"], unique=False)
    else:
        cols = _columns(insp, "product_media")
        missing = []
        if "product_id" not in cols:
            missing.append(sa.Column("product_id", sa.String(), nullable=False, server_default=""))
        if "bucket" not in cols:
            missing.append(sa.Column("bucket", sa.String(), nullable=False, server_default="products"))
        if "object_key" not in cols:
            missing.append(sa.Column("object_key", sa.String(), nullable=False, server_default=""))
        if "kind" not in cols:
            missing.append(sa.Column("kind", sa.String(), nullable=False, server_default="image"))
        if "content_type" not in cols:
            missing.append(sa.Column("content_type", sa.String(), nullable=True))

        if missing:
            with op.batch_alter_table("product_media") as b:
                for col in missing:
                    b.add_column(col)

        insp = inspect(bind)
        cols = _columns(insp, "product_media")
        if "product_id" in cols and _table_exists(insp, "products") and not _constraint_exists(bind, "product_media_product_id_fkey"):
            op.create_foreign_key(
                "product_media_product_id_fkey",
                "product_media",
                "products",
                ["product_id"],
                ["id"],
            )

        if not _index_exists(bind, "ix_product_media_product_id"):
            op.create_index("ix_product_media_product_id", "product_media", ["product_id"], unique=False)

    # ----------------------------
    # ai_jobs extension (safe)
    # ----------------------------
    if _table_exists(insp, "ai_jobs"):
        cols = _columns(insp, "ai_jobs")

        # Add columns (best-effort)
        add_cols: list[sa.Column] = []
        if "hint" not in cols:
            add_cols.append(sa.Column("hint", sa.JSON(), nullable=True))
        if "result_json" not in cols:
            add_cols.append(sa.Column("result_json", sa.JSON(), nullable=True))
        if "error" not in cols:
            add_cols.append(sa.Column("error", sa.Text(), nullable=True))
        if "model_version" not in cols:
            add_cols.append(sa.Column("model_version", sa.String(), nullable=True))
        if "draft_product_id" not in cols:
            add_cols.append(sa.Column("draft_product_id", sa.String(), nullable=True))
        if "updated_at" not in cols:
            add_cols.append(sa.Column("updated_at", sa.DateTime(), nullable=True))

        if add_cols:
            with op.batch_alter_table("ai_jobs") as b:
                for col in add_cols:
                    b.add_column(col)

        insp = inspect(bind)
        cols = _columns(insp, "ai_jobs")

        # FK to products (only if products exists and column exists)
        if "draft_product_id" in cols and _table_exists(insp, "products") and not _constraint_exists(bind, "ai_jobs_draft_product_id_fkey"):
            op.create_foreign_key(
                "ai_jobs_draft_product_id_fkey",
                "ai_jobs",
                "products",
                ["draft_product_id"],
                ["id"],
            )

        # Index on draft_product_id
        if "draft_product_id" in cols and not _index_exists(bind, "ix_ai_jobs_draft_product_id"):
            op.create_index("ix_ai_jobs_draft_product_id", "ai_jobs", ["draft_product_id"], unique=False)


def downgrade() -> None:
    # Non-destructive migration; keep downgrade as a no-op to avoid accidental data loss.
    pass