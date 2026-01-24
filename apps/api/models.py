from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    JSON,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base, relationship, synonym

# ============================================================
# BASE — ЕДИНСТВЕННЫЙ SOURCE OF TRUTH ДЛЯ ALEMBIC/ORM
# ============================================================

Base = declarative_base()

# ============================================================
# CATEGORIES (см. e2a717f7292d_init_schema.py)
# ============================================================


class Category(Base):
    __tablename__ = "categories"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    parent_id = Column(String, ForeignKey("categories.id"), nullable=True, index=True)

    name = Column(String, nullable=False)
    slug = Column(String, nullable=False, index=True)
    path = Column(String, nullable=False, index=True)

    sort_order = Column(Integer, nullable=True)
    is_active = Column(Boolean, nullable=True)
    ai_aliases = Column(JSON, nullable=True)

    parent = relationship("Category", remote_side=[id], backref="children")


# ============================================================
# USERS (см. e2a717f7292d_init_schema.py)
# ============================================================


class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("email", name="uq_users_email"),)

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String, nullable=False, index=True)

    password_hash = Column(String, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=True)
    deleted_at = Column(DateTime, nullable=True)

    media = relationship("Media", back_populates="user", cascade="all, delete-orphan", passive_deletes=True)
    products = relationship("Product", back_populates="user", cascade="all, delete-orphan", passive_deletes=True)
    jobs = relationship("AIJob", back_populates="user", cascade="all, delete-orphan", passive_deletes=True)


# ============================================================
# MEDIA (init_schema + твои новые миграции: filename, size_bytes)
# ============================================================


class Media(Base):
    __tablename__ = "media"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))

    # в БД это owner_id (важно не ломать)
    owner_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    bucket = Column(String, nullable=False)
    object_key = Column(String, nullable=False)

    # по текущей БД у тебя content_type/size_bytes/created_at могут быть nullable
    content_type = Column(String, nullable=True)
    size_bytes = Column(Integer, nullable=True)
    created_at = Column(DateTime, nullable=True)

    # добавлено миграцией 733ceb074da3 (nullable=True по факту твоей БД)
    filename = Column(String, nullable=True)

    user = relationship("User", back_populates="media")
    jobs = relationship("AIJob", back_populates="media", cascade="all, delete-orphan", passive_deletes=True)


# ============================================================
# PRODUCTS (см. e2a717f7292d_init_schema.py)
# ============================================================


class Product(Base):
    __tablename__ = "products"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    owner_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    status = Column(String, nullable=False)

    title = Column(String, nullable=True)
    description = Column(Text, nullable=True)

    category_id = Column(String, ForeignKey("categories.id"), nullable=True)

    attributes = Column(JSON, nullable=True)
    tags = Column(JSON, nullable=True)

    created_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="products")
    category = relationship("Category")
    media = relationship("ProductMedia", back_populates="product", cascade="all, delete-orphan", passive_deletes=True)
    jobs = relationship("AIJob", back_populates="draft_product")


# ============================================================
# AI JOBS (см. e2a717f7292d_init_schema.py)
# ============================================================


class AIJob(Base):
    __tablename__ = "ai_jobs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))

    # в БД это owner_id — оставляем как есть
    owner_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    status = Column(String, nullable=False)

    media_id = Column(String, ForeignKey("media.id", ondelete="CASCADE"), nullable=False, index=True)

    hint = Column(JSON, nullable=True)
    result_json = Column(JSON, nullable=True)

    error = Column(Text, nullable=True)
    model_version = Column(String, nullable=True)

    draft_product_id = Column(String, ForeignKey("products.id"), nullable=True)

    created_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=True)

    # для обратной совместимости кода, где могли использовать user_id
    user_id = synonym("owner_id")

    user = relationship("User", back_populates="jobs")
    media = relationship("Media", back_populates="jobs")
    draft_product = relationship("Product", back_populates="jobs")


# ============================================================
# PRODUCT_MEDIA (см. e2a717f7292d_init_schema.py)
# ============================================================


class ProductMedia(Base):
    __tablename__ = "product_media"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    product_id = Column(String, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)

    bucket = Column(String, nullable=False)
    object_key = Column(String, nullable=False)
    kind = Column(String, nullable=False)

    content_type = Column(String, nullable=True)

    product = relationship("Product", back_populates="media")
