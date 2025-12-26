from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import (
    Column,
    String,
    Boolean,
    Integer,
    DateTime,
    ForeignKey,
    JSON,
    Text,
    Index,
    UniqueConstraint,
)


class Base(DeclarativeBase):
    pass


# ---------------- Users ----------------

class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True)

    email = Column(String, nullable=False)
    password_hash = Column(String, nullable=False)

    # soft-delete / отключение аккаунта
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=True)
    deleted_at = Column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint("email", name="uq_users_email"),
        Index("ix_users_email", "email"),
        Index("ix_users_is_active", "is_active"),
        Index("ix_users_deleted_at", "deleted_at"),
    )


# ---------------- Catalog ----------------

class Category(Base):
    __tablename__ = "categories"

    id = Column(String, primary_key=True)
    parent_id = Column(String, ForeignKey("categories.id"), nullable=True)

    name = Column(String, nullable=False)
    slug = Column(String, nullable=False)
    path = Column(String, nullable=False)

    sort_order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    ai_aliases = Column(JSON, default=dict)

    __table_args__ = (
        Index("ix_categories_parent_id", "parent_id"),
        Index("ix_categories_path", "path"),
        Index("ix_categories_slug", "slug"),
    )


# ---------------- Media ----------------

class Media(Base):
    __tablename__ = "media"

    id = Column(String, primary_key=True)

    owner_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)

    bucket = Column(String, nullable=False)
    object_key = Column(String, nullable=False)
    content_type = Column(String, nullable=False)

    created_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_media_owner_created", "owner_id", "created_at"),
    )


# ---------------- Products ----------------
# (по смыслу это "вещи" в гардеробе)

class Product(Base):
    __tablename__ = "products"

    id = Column(String, primary_key=True)

    owner_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)

    status = Column(String, nullable=False)  # draft/published/archived
    title = Column(String, nullable=True)
    description = Column(Text, nullable=True)

    category_id = Column(String, ForeignKey("categories.id"), nullable=True)

    attributes = Column(JSON, default=dict)
    tags = Column(JSON, default=list)

    created_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_products_owner_status", "owner_id", "status"),
        Index("ix_products_category_id", "category_id"),
    )


class ProductMedia(Base):
    __tablename__ = "product_media"

    id = Column(String, primary_key=True)

    product_id = Column(String, ForeignKey("products.id"), nullable=False)

    bucket = Column(String, nullable=False)
    object_key = Column(String, nullable=False)

    kind = Column(String, nullable=False)  # original/processed
    content_type = Column(String, nullable=True)

    __table_args__ = (
        Index("ix_product_media_product_id", "product_id"),
    )


# ---------------- Looks (Outfits) ----------------
# Аутфиты/образы пользователя

class Look(Base):
    __tablename__ = "looks"

    id = Column(String, primary_key=True)

    owner_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)

    title = Column(String, nullable=True)
    occasion = Column(String, nullable=True)  # work/date/travel/party/etc
    season = Column(String, nullable=True)    # winter/summer/demi/all

    created_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_looks_owner_created", "owner_id", "created_at"),
        Index("ix_looks_owner_updated", "owner_id", "updated_at"),
    )


class LookItem(Base):
    __tablename__ = "look_items"

    id = Column(String, primary_key=True)

    look_id = Column(String, ForeignKey("looks.id"), nullable=False)
    product_id = Column(String, ForeignKey("products.id"), nullable=False)

    created_at = Column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint("look_id", "product_id", name="uq_look_items_look_product"),
        Index("ix_look_items_look_id", "look_id"),
        Index("ix_look_items_product_id", "product_id"),
    )


# ---------------- Wear log ----------------
# История носки (для аналитики: "давно не носил", "топ вещей", и т.д.)

class WearLog(Base):
    __tablename__ = "wear_log"

    id = Column(String, primary_key=True)

    owner_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    product_id = Column(String, ForeignKey("products.id"), nullable=False)

    worn_at = Column(DateTime, nullable=False)
    context = Column(String, nullable=True)  # work/date/travel/etc (опционально)
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_wear_log_owner_worn_at", "owner_id", "worn_at"),
        Index("ix_wear_log_product_worn_at", "product_id", "worn_at"),
    )


# ---------------- AI Jobs ----------------

class AIJob(Base):
    __tablename__ = "ai_jobs"

    id = Column(String, primary_key=True)

    owner_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)

    status = Column(String, nullable=False)  # queued/processing/done/error

    media_id = Column(String, ForeignKey("media.id"), nullable=False)

    hint = Column(JSON, default=dict)
    result_json = Column(JSON, nullable=True)
    error = Column(Text, nullable=True)

    model_version = Column(String, nullable=True)

    draft_product_id = Column(String, ForeignKey("products.id"), nullable=True)

    created_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_ai_jobs_owner_created", "owner_id", "created_at"),
        Index("ix_ai_jobs_media_id", "media_id"),
        Index("ix_ai_jobs_draft_product_id", "draft_product_id"),
    )